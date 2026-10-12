"""End-to-end run with a fake network layer and real ffmpeg (skipped without it)."""

import json
import shutil
import subprocess

import pytest

import yt_slurp as ys

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")

AUTO_VTT = """WEBVTT

00:00:00.000 --> 00:00:02.000
hello everyone

00:00:02.000 --> 00:00:04.000
hello everyone
this is a test
"""

VIDEOS = {
    "capt0000001": dict(title="Has Captions", upload_date="20240102", duration=600, language="en",
                        automatic_captions={"en-orig": [{"ext": "vtt", "url": "cap1"}]}),
    "nocap000002": dict(title="No Captiöns – Long", upload_date="20240103", duration=150, language=None),
    "spanish0003": dict(title="Hola", upload_date="20240104", duration=400, language="es",
                        automatic_captions={"en": [{"ext": "vtt", "url": "translated"}]}),
    "members0004": dict(title="Members", upload_date="20240105", duration=900),
    "short000005": dict(title="Short one", upload_date="20240106", duration=60),
}


class FakeNet:
    def __init__(self, browser=None):
        self.browser = browser
        self.logger = ys.YdlLogger()

    def close(self):
        pass

    def check_cookies(self):
        pass

    def flat(self, url):
        if url.endswith("/videos"):
            return {"channel": "Test Channel", "channel_id": "UCtest",
                    "entries": [{"id": k, "title": v["title"], "duration": v["duration"]}
                                for k, v in VIDEOS.items()]}
        raise RuntimeError("ERROR: [youtube:tab] This channel does not have a shorts tab")

    def video_info(self, vid):
        if vid == "members0004" and not self.browser:
            raise RuntimeError("ERROR: [youtube] members0004: Join this channel to get access to members-only content")
        v = dict(VIDEOS[vid])
        v.update(id=vid, channel="Test Channel", live_status="not_live")
        return v

    def fetch_text(self, url):
        return AUTO_VTT

    def download_audio(self, vid, dest):
        dest.mkdir(parents=True, exist_ok=True)
        out = dest / f"{vid}.m4a"
        # 150 s: tone, with a silence from 72 to 76 s near the 75 s boundary
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "sine=f=300:d=150,volume=enable='between(t,72,76)':volume=0",
                        "-c:a", "aac", str(out)], check=True)
        return out


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(ys, "Net", FakeNet)
    monkeypatch.setattr(ys, "preflight", lambda: None)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*argv):
    return ys.main(["https://www.youtube.com/@test", "--chunk-minutes", "1.5", "--min-minutes", "2", *argv])


def test_full_pipeline(fake, monkeypatch):
    answers = iter(["n"])  # decline cookies for the members-only video
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert run() == 0
    folder = fake / "output" / "Test Channel"
    m = ys.Manifest(folder / "manifest.csv")
    status = {k: r["status"] for k, r in m.rows.items()}
    assert status == {"capt0000001": "transcript", "nocap000002": "wav", "spanish0003": "skipped-non-english",
                      "members0004": "needs-signin", "short000005": "skipped-short"}

    transcript = next((folder / "transcripts").iterdir())
    text = transcript.read_text(encoding="utf-8")
    assert transcript.name == "2024-01-02 Has Captions [capt0000001].txt"
    assert "Title: Has Captions" in text and text.rstrip().endswith("hello everyone this is a test")

    wavs = sorted(p.name for p in (folder / "needs-transcription" / "batch 01").iterdir())
    assert wavs == ["2024-01-03 No Captions Long [nocap000002] part 01 of 02.wav",
                    "2024-01-03 No Captions Long [nocap000002] part 02 of 02.wav"]
    part1 = folder / "needs-transcription" / "batch 01" / wavs[0]
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels,codec_name",
                            "-of", "json", str(part1)], capture_output=True, text=True)
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream == {"codec_name": "pcm_s16le", "sample_rate": "16000", "channels": 1}
    assert 72 <= ys.probe_duration(part1) <= 76  # cut inside the silence
    assert not list((folder / ".work" / "audio").iterdir())

    links = (folder / "links.txt").read_text(encoding="utf-8").splitlines()
    assert links[0].startswith("2024-01-02 | 10:00 | Has Captions | https://www.youtube.com/watch?v=capt0000001")
    assert "nocap000002 | 2 |" in (folder / "needs-transcription.txt").read_text(encoding="utf-8")

    # Whisper output saved by hand, then merge
    wt = folder / "whisper-transcripts"
    (wt / wavs[0].replace(".wav", ".txt")).write_text("First part.\n\nMore.", encoding="utf-8")
    assert ys.main(["merge", str(folder)]) == 0
    assert ys.Manifest(folder / "manifest.csv").get("nocap000002")["status"] == "wav"  # part 02 missing
    (wt / wavs[1].replace(".wav", ".txt")).write_text("Second part.", encoding="utf-8")
    (wt / "stray.txt").write_text("x", encoding="utf-8")
    assert ys.main(["merge", str(folder), "--delete-wavs"]) == 0
    assert ys.Manifest(folder / "manifest.csv").get("nocap000002")["status"] == "merged"
    merged = (folder / "transcripts" / "2024-01-03 No Captions Long [nocap000002].txt").read_text(encoding="utf-8")
    assert merged.endswith("First part.\n\nMore.\n\nSecond part.\n")
    assert "Transcript: Whisper" in merged
    assert not list((folder / "needs-transcription" / "batch 01").iterdir())
    assert len(list((folder / "gemini-notebook").iterdir())) == 2

    # Update with cookies retries the members-only video
    answers = iter([])
    assert run("--update", "--cookies-from-browser", "firefox") == 0
    m = ys.Manifest(folder / "manifest.csv")
    assert m.get("members0004")["status"] == "wav"
    assert m.get("members0004")["batch"] == "2"  # new batch, existing never reused
    assert m.get("capt0000001")["status"] == "transcript"


def test_links_only_and_fresh_keeps_whisper(fake, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert run("--links-only") == 0
    folder = fake / "output" / "Test Channel"
    assert (folder / "links.txt").exists() and not (folder / "transcripts").exists()
    assert ys.Manifest(folder / "manifest.csv").get("capt0000001")["status"] == "pending"
    (folder / "whisper-transcripts").mkdir()
    (folder / "whisper-transcripts" / "keep.txt").write_text("x", encoding="utf-8")
    answers = iter(["yes", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert run("--fresh") == 0
    assert (folder / "whisper-transcripts" / "keep.txt").exists()
    assert ys.Manifest(folder / "manifest.csv").get("capt0000001")["status"] == "transcript"


def test_single_video_rejected(fake):
    assert ys.main(["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]) == 2
