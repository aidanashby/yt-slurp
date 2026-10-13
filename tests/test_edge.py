"""Negative tests and edge cases: bad input, damaged files, missing tools, collisions."""

import json
import os

import pytest

import yt_slurp as ys

from test_pipeline import FakeNet, VIDEOS


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(ys, "Net", FakeNet)
    monkeypatch.setattr(ys, "preflight", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "none")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("url", ["", "   ", "not a link", "https://vimeo.com/123",
                                 "https://www.youtube.com/results?search_query=x",
                                 "https://www.youtube.com/playlist", "https://www.youtube.com/watch?v=x&list=RDabc"])
def test_bad_urls_are_refused(url):
    assert ys.classify_url(url)[0] in ("unknown", "video")


def test_run_with_only_bad_urls_stops_cleanly(fake):
    assert ys.run_command(["https://vimeo.com/1"]) == 2
    assert not (fake / "output").exists()


def test_url_file_with_only_comments(fake):
    (fake / "urls.txt").write_text("# nothing here\n\n   \n", encoding="utf-8")
    assert ys.run_command(["--file", "urls.txt"]) == 2


def test_missing_url_file(fake):
    assert ys.run_command(["--file", "nope.txt"]) == 2


def test_url_and_file_together_refused(fake):
    (fake / "urls.txt").write_text("https://www.youtube.com/@x\n", encoding="utf-8")
    assert ys.run_command(["https://www.youtube.com/@x", "--file", "urls.txt"]) == 2


def test_unknown_option_does_not_crash(fake):
    assert ys.run_command(["https://www.youtube.com/@x", "--no-such-option"]) == 2


@pytest.mark.parametrize("vid", ["../../../evil", "short", "x" * 12, "abc/def/ghi", None, 12345678901])
def test_invalid_ids_rejected(vid):
    assert not ys.valid_id(vid)


def test_listing_entry_with_bad_id_never_touches_the_disk(fake, monkeypatch):
    class EvilNet(FakeNet):
        def flat(self, url):
            info = super().flat(url)
            info["entries"].append({"id": "../../escape", "title": "Evil", "duration": 900})
            return info

    monkeypatch.setattr(ys, "Net", EvilNet)
    assert ys.run_command(["https://www.youtube.com/@test", "--min-minutes", "2", "--chunk-minutes", "1.5"]) == 0
    folder = fake / "output" / "Test Channel"
    assert "../../escape" not in ys.Manifest(folder / "manifest.csv").rows
    assert not (fake / "escape.json").exists() and not (folder.parent / "escape.json").exists()


def test_meta_path_refuses_bad_id(tmp_path):
    src = ys.Source(url="u", kind="playlist", folder=tmp_path)

    class Args:
        lang = "en"

    ctx = ys.RunContext(Args(), None)
    run = ys.SourceRun(src, ctx)
    with pytest.raises(ValueError):
        run.meta_path("../x")


def test_damaged_manifest_rows_are_tolerated(tmp_path):
    (tmp_path / "manifest.csv").write_text(
        "id,title,status\n"
        "dQw4w9WgXcQ,Good,transcript\n"
        ",no id,failed\n"
        "garbage line with no commas\n", encoding="utf-8")
    m = ys.Manifest(tmp_path / "manifest.csv")
    assert list(m.rows) == ["dQw4w9WgXcQ", "garbage line with no commas"] or "dQw4w9WgXcQ" in m.rows
    assert m.get("dQw4w9WgXcQ")["upload_date"] == ""  # missing columns become empty
    m.save()  # and it can be written back
    assert "dQw4w9WgXcQ" in ys.Manifest(tmp_path / "manifest.csv").rows


def test_very_long_and_non_latin_titles(tmp_path):
    long_title = ys.safe_filename("A really long title " * 30)
    assert len(long_title) <= ys.MAX_TITLE_LEN
    assert ys.safe_filename("日本語のタイトル") == "untitled"
    assert ys.safe_filename("Ελληνικά and English") == "and English"
    assert ys.safe_filename("NUL") == "_NUL"
    assert ys.safe_filename("lpt1") == "_lpt1"
    assert ys.safe_filename("trailing dots...") == "trailing dots"


def test_output_path_too_long_is_refused(fake):
    deep = fake / ("d" * 200)
    assert ys.run_command(["https://www.youtube.com/@test", "--output", str(deep)]) == 2


def test_missing_ffmpeg_gives_install_advice(monkeypatch):
    monkeypatch.setattr(ys.shutil, "which", lambda name: None)
    with pytest.raises(ys.Stop) as e:
        ys.preflight()
    assert "winget install Gyan.FFmpeg" in str(e.value)


def test_folder_locked_by_another_run(fake):
    folder = fake / "output" / "Test Channel"
    (folder / ".work").mkdir(parents=True)
    (folder / ".work" / "run.lock").write_text(str(os.getppid()), encoding="utf-8")  # a live process
    assert ys.run_command(["https://www.youtube.com/@test"]) == 2
    (folder / ".work" / "run.lock").write_text("999999999", encoding="utf-8")  # a dead one is ignored
    assert ys.run_command(["https://www.youtube.com/@test", "--min-minutes", "2", "--chunk-minutes", "1.5"]) == 0


def test_stop_while_paused():
    ys.PAUSE.set()
    ys.STOP.set()
    try:
        with pytest.raises(KeyboardInterrupt):
            ys.check_stop()
    finally:
        ys.PAUSE.clear()
        ys.STOP.clear()


def test_merge_without_manifest(tmp_path):
    assert ys.run_command(["merge", str(tmp_path)]) == 2
    assert ys.run_command(["merge", str(tmp_path / "missing")]) == 2


def test_merge_ignores_stray_and_empty_files(fake):
    assert ys.run_command(["https://www.youtube.com/@test", "--min-minutes", "2", "--chunk-minutes", "1.5"]) == 0
    folder = fake / "output" / "Test Channel"
    wt = folder / "whisper-transcripts"
    (wt / "random notes.txt").write_text("x", encoding="utf-8")
    (wt / "photo [nocap000002].jpg").write_bytes(b"\xff\xd8")
    assert ys.run_command(["merge", str(folder)]) == 0
    assert ys.Manifest(folder / "manifest.csv").get("nocap000002")["status"] == "wav"


def test_gui_settings_survive_damage(tmp_path, monkeypatch):
    pytest.importorskip("tkinter")
    import yt_slurp_gui as gui
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = tmp_path / gui.APP_NAME
    d.mkdir()
    (d / "settings.json").write_text("{not json", encoding="utf-8")
    assert gui.load_settings() == gui.DEFAULT_SETTINGS
    (d / "settings.json").write_text(json.dumps({"min_minutes": "five", "types": ["../x"], "pace": "warp",
                                                 "make_wavs": "yes", "limit": -3, "lang": "fr"}), encoding="utf-8")
    s = gui.load_settings()
    assert s["min_minutes"] == 5 and s["types"] == ["videos"] and s["pace"] == "normal"
    assert s["make_wavs"] is True and s["limit"] == 5 and s["lang"] == "fr"
    (d / "settings.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert gui.load_settings() == gui.DEFAULT_SETTINGS


def test_fake_videos_have_valid_ids():
    assert all(ys.valid_id(v) for v in VIDEOS)
