"""End-to-end run with a fake network layer and real ffmpeg (skipped without it)."""

import itertools
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
        v.update(id=vid, channel="Test Channel", live_status="not_live", channel_id="UCtest",
                 uploader_url="https://www.youtube.com/@test")
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
    answers = iter(["none"])  # decline cookies for the members-only video
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert run() == 0
    folder = fake / "output" / "Test Channel"
    m = ys.Manifest(folder / "manifest.csv")
    status = {k: r["status"] for k, r in m.rows.items()}
    assert status == {"capt0000001": "transcript", "nocap000002": "wav", "spanish0003": "skipped-non-english",
                      "members0004": "needs-signin", "short000005": "skipped-short"}

    transcript = next((folder / "transcripts").iterdir())
    text = transcript.read_text(encoding="utf-8")
    assert transcript.name == "Has Captions [capt0000001] 2024-01-02.md"
    assert text.startswith("# Has Captions\n") and "- **URL:** <https://www.youtube.com/watch?v=capt0000001>" in text and text.rstrip().endswith("hello everyone this is a test")

    wavs = sorted(p.name for p in (folder / "needs-transcription").iterdir())
    assert wavs == ["No Captions Long [nocap000002] 2024-01-03 part 01 of 02.wav",
                    "No Captions Long [nocap000002] 2024-01-03 part 02 of 02.wav"]
    part1 = folder / "needs-transcription" / wavs[0]
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels,codec_name",
                            "-of", "json", str(part1)], capture_output=True, text=True)
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream == {"codec_name": "pcm_s16le", "sample_rate": "16000", "channels": 1}
    assert 72 <= ys.probe_duration(part1) <= 76  # cut inside the silence
    assert not list((folder / ".work" / "audio").iterdir())

    links = (folder / "links.txt").read_text(encoding="utf-8").splitlines()
    assert links[0] == "https://www.youtube.com/watch?v=capt0000001"
    assert all(line.startswith("https://www.youtube.com/watch?v=") for line in links)
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
    merged = (folder / "transcripts" / "No Captions Long [nocap000002] 2024-01-03.md").read_text(encoding="utf-8")
    assert merged.endswith("First part.\n\nMore.\n\nSecond part.\n")
    assert "- **Transcript:** your transcription app" in merged
    assert not list((folder / "needs-transcription").glob("*.wav"))
    assert not (folder / "gemini-notebook").exists()  # bundling is a separate step now
    assert not (folder / "claude-parts").exists()
    assert ys.main(["gemini", str(folder)]) == 0
    assert len(list((folder / "gemini-notebook").iterdir())) == 2

    # Update with cookies retries the members-only video
    answers = iter([])
    assert run("--update", "--cookies-from-browser", "firefox") == 0
    m = ys.Manifest(folder / "manifest.csv")
    assert m.get("members0004")["status"] == "wav"
    assert len(list((folder / "needs-transcription").glob("*members0004*.wav"))) == 2
    assert m.get("capt0000001")["status"] == "transcript"


def test_links_only_and_fresh_keeps_whisper(fake, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "none")
    assert run("--links-only") == 0
    folder = fake / "output" / "Test Channel"
    assert (folder / "links.txt").exists() and not (folder / "transcripts").exists()
    assert ys.Manifest(folder / "manifest.csv").get("capt0000001")["status"] == "pending"
    (folder / "whisper-transcripts").mkdir()
    (folder / "whisper-transcripts" / "keep.txt").write_text("x", encoding="utf-8")
    answers = iter(["yes", "none"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert run("--fresh") == 0
    assert (folder / "whisper-transcripts" / "keep.txt").exists()
    assert ys.Manifest(folder / "manifest.csv").get("capt0000001")["status"] == "transcript"


def test_mixed_links_each_go_to_their_own_place(fake, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "none")
    assert run("https://youtu.be/capt0000001", "https://www.youtube.com/@test/featured", "https://vimeo.com/1") == 0
    out = fake / "output"
    assert [d.name for d in out.iterdir()] == ["Test Channel"]  # the video shares its channel's folder
    names = [p.name for p in (out / "Test Channel" / "transcripts").iterdir()]
    assert len(names) == 1  # and is done once
    assert (out / "Test Channel" / "links.txt").exists()


OTHER = "capt0000009"


@pytest.fixture
def two_channels(fake, monkeypatch):
    class Net2(FakeNet):
        def video_info(self, vid):
            if vid != OTHER:
                return super().video_info(vid)
            return {**VIDEOS["capt0000001"], "id": OTHER, "title": "Other", "channel": "Second", "channel_id": "UC2",
                    "live_status": "not_live", "uploader_url": "https://www.youtube.com/@second"}
    monkeypatch.setattr(ys, "Net", Net2)
    monkeypatch.setattr("builtins.input", lambda prompt="": "none")
    return fake / "output"


def test_separate_folders_by_channel(two_channels):
    urls = [ys.watch_url(v) for v in (OTHER, "capt0000001", "short000005")]
    assert ys.main([*urls, "--no-wavs", "--separate"]) == 0
    assert sorted(d.name for d in two_channels.iterdir()) == ["Second", "Test Channel"]
    assert not list(two_channels.rglob("links.txt"))


def test_several_links_share_a_folder_in_any_order(two_channels, monkeypatch):
    links = ["https://www.youtube.com/@test", ys.watch_url(OTHER), ys.watch_url("short000005")]
    opts = ["--min-minutes", "2", "--no-wavs"]
    assert ys.main([*links, *opts]) == 0
    folder, = two_channels.iterdir()
    assert folder.name == "Second and Test Channel"
    folder = folder.rename(folder.with_name("My research"))
    asked = []

    def answer(mode):
        def choose(q, options):
            if "slurped together before" in q:
                asked.append(q)
                return mode
            return "none"
        monkeypatch.setattr(ys.UI, "choose", choose)
    answer("update")
    kept = {p: p.stat().st_mtime_ns for p in (folder / "transcripts").iterdir()}
    assert ys.main([*reversed(links), *opts]) == 0  # same folder though renamed
    assert len(asked) == 1 and "My research" in asked[0]
    assert {p: p.stat().st_mtime_ns for p in (folder / "transcripts").iterdir()} == kept
    answer("fresh")
    (folder / "old.txt").write_text("x")
    monkeypatch.setattr(ys.UI, "confirm_delete", lambda m: True)
    assert ys.main([*links, *opts]) == 0
    assert len(asked) == 2 and not (folder / "old.txt").exists()
    assert list(two_channels.iterdir()) == [folder]
    assert len(list((folder / "transcripts").iterdir())) == 2
    assert ys.Manifest(folder / "manifest.csv").get("short000005")["status"] == "no-captions"  # not skipped-short
    assert (folder / "links.txt").exists()
    assert ys.main([*links[:2], *opts]) == 0  # a different set of links is a different folder
    assert len(list(two_channels.iterdir())) == 2


def test_several_links_for_one_channel_use_its_folder(two_channels):
    assert ys.main([ys.watch_url("capt0000001"), ys.watch_url("short000005"), "--no-wavs"]) == 0
    assert [d.name for d in two_channels.iterdir()] == ["Test Channel"]


def test_combined_name():
    assert ys.combined_name(["b", "A", "b"]) == "A and b"
    assert ys.combined_name(["c", "b", "a"]) == "a, b and c"
    assert ys.combined_name([f"Channel number {i}" for i in range(9)]) == \
        "Channel number 0, Channel number 1 and more"
    for names in (["x" * 200, "y"], [f"Name {i}" for i in range(200)]):
        name = ys.combined_name(names)
        assert len(name) <= ys.MAX_COMBINED_NAME_LEN and name.endswith(" and more")


def test_whole_channel_from_a_video(two_channels):
    assert ys.main([ys.watch_url("capt0000001"), "--whole-channel", "--no-wavs"]) == 0
    assert len(ys.Manifest(two_channels / "Test Channel" / "manifest.csv").rows) == len(VIDEOS)


def test_channel_after_one_of_its_videos(two_channels):
    assert ys.main([ys.watch_url("capt0000001")]) == 0
    assert run("--no-wavs") == 0  # no "start again?" question for one video
    m = ys.Manifest(two_channels / "Test Channel" / "manifest.csv")
    assert len(m.rows) == len(VIDEOS) and m.get("capt0000001")["status"] == "transcript"


def test_no_wavs_records_no_captions_and_pace(fake, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "none")
    assert run("--no-wavs", "--pace", "slow") == 0
    assert ys.DELAY_RANGE_S == ys.PACES["slow"]
    m = ys.Manifest(fake / "output" / "Test Channel" / "manifest.csv")
    assert m.get("nocap000002")["status"] == "no-captions"
    assert not (fake / "output" / "Test Channel" / "needs-transcription").exists()
    # Turning WAVs back on picks it up.
    assert run("--update") == 0
    assert ys.Manifest(fake / "output" / "Test Channel" / "manifest.csv").get("nocap000002")["status"] == "wav"
    ys.DELAY_RANGE_S = ys.PACES["normal"]


def test_outputs_rewritten_each_round(fake, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "none")
    monkeypatch.setattr(ys, "ROUND_SIZE", 2)
    seen = []
    real = ys.write_links

    def spy(folder, manifest):
        seen.append(len(manifest.rows))
        return real(folder, manifest)

    monkeypatch.setattr(ys, "write_links", spy)
    assert run() == 0
    assert len(seen) >= 3  # rewritten after each round, not only at the end


def test_migrate_names_from_older_versions(tmp_path):
    needs = tmp_path / "needs-transcription" / "batch 01"
    needs.mkdir(parents=True)
    (needs / "2024-01-03 Talk [nocap000002] part 01 of 02.wav").write_bytes(b"x")
    (tmp_path / "transcripts").mkdir()
    (tmp_path / "transcripts" / "2024-01-02 Other [capt0000001].txt").write_text(
        "Title: Other\nChannel: C\nDate: 2024-01-02\nDuration: 1:00\nURL: https://www.youtube.com/watch?v=capt0000001\n"
        "Transcript: YouTube captions\n\nHello *there*.", encoding="utf-8")
    ys.migrate_names(tmp_path)
    assert (tmp_path / "needs-transcription" / "Talk [nocap000002] 2024-01-03 part 01 of 02.wav").exists()
    assert not (tmp_path / "needs-transcription" / "batch 01").exists()
    md = tmp_path / "transcripts" / "Other [capt0000001] 2024-01-02.md"
    assert md.exists() and not md.with_suffix(".txt").exists()
    text = md.read_text(encoding="utf-8")
    assert text.startswith("# Other\n") and "- **Channel:** C" in text and text.rstrip().endswith("Hello \\*there\\*.")


def test_gemini_command_needs_transcripts(fake):
    (fake / "empty").mkdir()
    assert ys.main(["gemini", str(fake / "empty")]) == 2


def test_warning_lists_channels_and_can_leave_some_out(two_channels, monkeypatch):
    seen = []
    monkeypatch.setattr(ys.UI, "confirm_many", lambda groups, *a: (
        seen.append([(g.name, len(g.todo)) for g in groups]), ({"Second"}, None))[1])
    for extra in ([], ["--separate"]):
        assert run(ys.watch_url(OTHER), "--no-wavs", "--warn-over", "2", *extra) == 0
    assert seen == [[("Test Channel", 4), ("Second", 1)]] * 2  # longest first
    assert not [p for p in two_channels.rglob("*.md") if OTHER in p.name]


@pytest.mark.parametrize("answer,code", [("none", 2), ("yes", 0)])
def test_warns_before_many_videos(fake, monkeypatch, answer, code):
    asked = []
    monkeypatch.setattr(ys.UI, "choose", lambda q, o: (asked.append(q), answer if "videos to get" in q else "none")[1])
    assert run("--no-wavs", "--warn-over", "3") == code
    assert "4 videos" in asked[0]  # the short one is not counted
    assert (fake / "output" / "Test Channel").exists() == (code == 0)
    asked.clear()
    assert run("--no-wavs", "--warn-over", "4", "--update") == 0
    assert not [q for q in asked if "videos to get" in q]


# ----- nothing is lost by mistake -----

@pytest.mark.parametrize("extra", [[], ["https://youtu.be/capt0000009"]])
def test_cancelling_after_start_again_keeps_everything(two_channels, monkeypatch, extra):
    assert run("--no-wavs", *extra) == 0
    before = sorted(p for p in two_channels.rglob("*") if p.is_file())
    monkeypatch.setattr(ys.UI, "confirm_delete", lambda m: True)
    monkeypatch.setattr(ys.UI, "confirm_many", lambda *a: None)
    assert run("--no-wavs", "--fresh", "--warn-over", "1", *extra) == 2
    assert sorted(p for p in two_channels.rglob("*") if p.is_file()) == before
    assert run("--no-wavs", "--fresh", *extra) == 0  # and confirming does start again
    assert list(two_channels.rglob("*.md"))


def test_start_again_is_refused_when_a_link_cannot_be_read(two_channels, monkeypatch):
    links = ["https://www.youtube.com/@test", ys.watch_url(OTHER)]
    assert ys.main([*links, "--no-wavs"]) == 0
    kept = sorted(two_channels.rglob("*.md"))
    base = ys.Net

    class Down(base):
        def video_info(self, vid):
            if vid == OTHER:
                raise RuntimeError("HTTP Error 404")
            return super().video_info(vid)
    monkeypatch.setattr(ys, "Net", Down)
    monkeypatch.setattr(ys.UI, "confirm_delete", lambda m: True)
    assert ys.main([*links, "--no-wavs", "--fresh"]) == 2
    assert sorted(two_channels.rglob("*.md")) == kept


def test_folders_are_never_shared_by_different_sources(tmp_path):
    for name in ("x" * 60, "word " * 12, "\u4f60\u597d"):
        seen = set()
        for n in range(4):
            src = ys.Source(url=f"https://u/{n}", kind="playlist", name=name, source_id="PL" + str(n) * 32 if n else "")
            folder = ys.choose_folder(src, tmp_path, set())
            assert folder not in seen
            seen.add(folder)
            folder.mkdir(exist_ok=True)
            (folder / "run.json").write_text(json.dumps({"url": src.url, "source_id": src.source_id}))
            assert ys.choose_folder(src, tmp_path, set()) == folder  # and found again


@pytest.mark.parametrize("text", ["[]", "null", "5", '"s"', '{"url": 5}', "{", pytest.param("[" * 100000, id="nested")])
def test_damaged_run_json_is_ignored(tmp_path, text):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "run.json").write_text(text)
    assert ys.load_run(tmp_path / "d") == {}
    assert ys.folder_for_links(tmp_path, "x") is None


def test_whole_channel_does_every_videos_channel(two_channels):
    found = ys.resolve_videos(["capt0000001", OTHER, "short000005"], ys.Net(), whole_channel=True)
    assert [s.url for s in found] == ["https://www.youtube.com/@test", "https://www.youtube.com/@second"]


# ----- keeping to some of each channel -----

@pytest.fixture
def ranked(fake, monkeypatch):
    vids = {f"rankedvid{i:02d}": dict(title=f"V{i}", upload_date="20240101", duration=600, language="en",
                                      automatic_captions={"en-orig": [{"ext": "vtt", "url": "c"}]}) for i in range(8)}
    monkeypatch.setattr("test_pipeline.VIDEOS", vids)

    class Net(FakeNet):
        def video_info(self, vid):
            return {**vids[vid], "id": vid, "channel": "Test Channel", "live_status": "not_live", "channel_id": "UCtest",
                    "uploader_url": "https://www.youtube.com/@test"}

        def flat(self, url):
            if not url.endswith("/videos"):
                raise RuntimeError("no such tab")
            return {"channel": "Test Channel", "channel_id": "UCtest", "entries": [
                {"id": k, "title": v["title"], "duration": 600, "view_count": i * 10}
                for i, (k, v) in enumerate(vids.items())]}
    monkeypatch.setattr(ys, "Net", Net)
    return fake / "output" / "Test Channel"


def done(folder):
    return sorted(r["title"] for r in ys.Manifest(folder / "manifest.csv").rows.values() if r["status"] == "transcript")


def test_newest_and_most_viewed_are_remembered(ranked, monkeypatch):
    monkeypatch.setattr(ys.UI, "confirm_many", lambda groups, speed, limit, keep: (set(), (2, 1)))
    assert run("--warn-over", "5") == 0
    assert done(ranked) == ["V0", "V1", "V7"]
    assert len((ranked / "links.txt").read_text().split()) == 3  # the rest are not listed
    assert run("--warn-over", "5", "--update") == 0  # keeps to it, so nothing new and no question
    assert done(ranked) == ["V0", "V1", "V7"]
    asked = []
    monkeypatch.setattr(ys.UI, "choose", lambda q, o: (asked.append([k for k, _ in o]), "all")[1])
    assert run() == 0
    assert asked == [["update", "all", "fresh"]] and len(done(ranked)) == 8


def test_command_line_limits_and_speed_record(ranked, monkeypatch):
    ticks = itertools.count()
    monkeypatch.setattr(ys.time, "perf_counter", lambda: float(next(ticks)))  # a second each time it is read
    assert run("--newest", "3", "--most-viewed", "4") == 0
    assert done(ranked) == ["V0", "V1", "V2", "V4", "V5", "V6", "V7"]
    (seconds, n), = ys.read_speeds()["normal"]
    assert (seconds, n) == (14, 7)  # details and transcript for each


def test_negative_limits_are_refused(ranked):
    assert run("--newest", "-3") == 2 and run("--most-viewed", "-1") == 2
    assert not ranked.exists()


def test_limits_apply_to_each_channel_of_a_combined_run(ranked):
    src = ys.Source(url="k", kind="combined", name="c", folder=ranked, keep=(1, 1), entries=[
        {"id": f"{c}{i:010d}", "_from": c, "_type": "video", "view_count": i, "duration": 600}
        for c in "ab" for i in range(5)])
    args = ys.build_run_parser().parse_args(["u"])
    ys.normalise_make_options(args)
    picked = {e["id"] for e in ys.SourceRun(src, ys.RunContext(args, None)).todo_entries()}
    assert picked == {f"{c}{i:010d}" for c in "ab" for i in (0, 4)}
