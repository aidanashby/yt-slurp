"""Drive the real window with a fake network layer. Skipped without Tkinter or a display."""

import os
import time

import pytest

tk = pytest.importorskip("tkinter")

import yt_slurp as ys  # noqa: E402

from test_pipeline import FakeNet  # noqa: E402


@pytest.fixture
def app(monkeypatch, tmp_path):
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("no display")
    import yt_slurp_gui as gui
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(ys, "Net", FakeNet)
    monkeypatch.setattr(ys, "preflight", lambda: None)
    monkeypatch.setattr(gui, "open_path", lambda p: None)
    monkeypatch.setattr(gui.setup, "missing_tools", lambda: [])
    monkeypatch.setattr(gui.setup, "check_for_update", lambda current: None)
    monkeypatch.setattr(gui.ChoiceDialog, "__init__",
                        lambda self, parent, q, opts: setattr(self, "result", "none"))
    gui.save_settings({**gui.DEFAULT_SETTINGS, "welcomed": True, "output": str(tmp_path / "out"),
                       "min_minutes": 2, "chunk_minutes": 1.5})
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    instance = gui.InstanceLock()
    assert instance.acquire()
    a = gui.App(root, instance)
    yield a
    ys.set_ui(ys.ConsoleUI())
    ys.PAUSE.clear()
    instance.release()
    root.destroy()


def pump(app, until, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        app.root.update()
        if until():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


def idle(app):
    return app.slurp_btn.enabled


def names(app):
    return [app.tree.item(i, "text") for i in app.tree.get_children()]


def run_fake(app):
    app.url_var.set("https://www.youtube.com/@test")
    app.slurp()
    pump(app, lambda: idle(app))
    assert app.stage == "Finished."


def test_slurp_shows_everything_together_and_auto_merges(app):
    run_fake(app)
    kinds = [it["kind"] for it in app.items]
    assert kinds.count("transcript") == 1 and kinds.count("wav") == 2
    assert kinds.count("link") == 3 and kinds.count("skipped") == 2
    shown = names(app)
    assert len(shown) == 8  # every kind shows by default
    assert "\u25a0  Has Captions" in shown  # exact title first
    assert "\u266a  No Captiöns – Long, part 01 of 02" in shown
    assert "\u2298  Short one (shorter than 2 minutes)" in shown
    assert "\u2298  Hola (not in English, no captions)" in shown
    assert app.tree.column("#0", "width") > 0 and app.tree["columns"] == ""

    # Chips filter by kind; they are in alphabetical order.
    assert [c.label for c in app.chips.values()] == ["Links", "Skipped", "Transcripts", "WAVs"]
    for kind in ("link", "skipped", "wav"):
        app.chips[kind].toggle()
    assert names(app) == ["\u25a0  Has Captions"]
    for kind in ("link", "skipped", "wav"):
        app.chips[kind].toggle()

    # Name filter.
    app.name_filter.var.set("captiöns")
    assert len(names(app)) == 3  # its link and both WAV parts
    app.name_filter.var.set("")
    assert len(names(app)) == 8

    # Preview and in-file search.
    iid = next(i for i in app.tree.get_children() if app.tree.item(i, "text") == "\u25a0  Has Captions")
    app.tree.selection_set(iid)
    app.root.update()
    assert "Title: Has Captions" in app.preview_text.get("1.0", "end")
    app.text_search.var.set("test")
    app.run_search()  # normally runs 150 ms after typing stops
    assert len(app.matches) == 2 and app.match_label.cget("text") == "1 of 2"  # header and body
    app.text_search.var.set("e")
    app.run_search()
    n = len(app.matches)
    assert n > 3
    app.step_match(-1)
    assert app.match_label.cget("text") == f"{n} of {n}"
    assert app.preview_text.tag_ranges("current")

    # Links file holds only URLs.
    folder = app.current_folder
    assert all(line.startswith("https://") for line in (folder / "links.txt").read_text().splitlines())

    # Save the Whisper text; the window merges it on its own.
    for it in [i for i in app.items if i["kind"] == "wav"]:
        (folder / ys.DIR_WHISPER / it["path"].name.replace(".wav", ".txt")).write_text("Spoken words.",
                                                                                         encoding="utf-8")
    app.auto_merge()
    pump(app, lambda: idle(app) and sum(i["kind"] == "transcript" for i in app.items) == 2)
    assert ys.Manifest(folder / "manifest.csv").get("nocap000002")["status"] == "merged"


def test_new_items_do_not_move_a_scrolled_or_selected_list(app):
    from pathlib import Path
    folder = Path("/tmp/fake-folder")
    app.current_folder = folder
    for i in range(60):  # items arrive one poll at a time, as in a real run
        app.add_item("link", folder, None, f"https://x/{i}", f"Video {i:02d}")
        app.root.update()
    assert app.tree.yview()[1] >= 0.999  # followed while at the bottom
    app.tree.yview_moveto(0)
    app.root.update()
    app.add_item("link", folder, None, "https://x/new", "Video new")
    app.root.update()
    assert app.tree.yview()[0] == 0  # stayed where the user scrolled


def test_pause_and_resume(app):
    app.url_var.set("https://www.youtube.com/@test")
    app.slurp()
    app.toggle_pause()
    assert ys.PAUSE.is_set() and app.pause_btn.text == "Resume"
    time.sleep(0.5)
    app.root.update()
    assert app.busy()  # waiting, not finished
    app.toggle_pause()
    assert not ys.PAUSE.is_set() and app.pause_btn.text == "Pause"
    pump(app, lambda: idle(app))
    assert app.stage == "Finished."


def test_settings_dialog_saves(app):
    import yt_slurp_gui as gui
    dlg = gui.SettingsDialog(app)
    dlg.vars["make_links"].set(False)
    dlg.pace_var.set("slow")
    dlg.save()
    assert app.settings["make_links"] is False and app.settings["pace"] == "slow"
    assert gui.load_settings()["pace"] == "slow"


def test_build_argv_maps_settings():
    import yt_slurp_gui as gui
    s = {**gui.DEFAULT_SETTINGS, "ask_types": False, "types": ["videos", "streams"], "test_run": True,
         "limit": 3, "timestamps": True, "make_wavs": False, "pace": "very-slow"}
    argv = gui.build_argv(s, url="https://www.youtube.com/@x")
    assert argv[0] == "https://www.youtube.com/@x"
    assert argv[argv.index("--types") + 1] == "videos,streams"
    assert argv[argv.index("--limit") + 1] == "3" and "--timestamps" in argv
    assert "--no-wavs" in argv and "--no-links" not in argv
    assert argv[argv.index("--pace") + 1] == "very-slow"
    assert gui.build_argv(gui.DEFAULT_SETTINGS, list_file="urls.txt")[:2] == ["--file", "urls.txt"]
    assert "--types" not in gui.build_argv(gui.DEFAULT_SETTINGS, url="u")
    only = gui.build_argv(gui.DEFAULT_SETTINGS, url="u", only_type="shorts")
    assert only[only.index("--types") + 1] == "shorts"


def test_find_matches():
    import yt_slurp_gui as gui
    assert gui.find_matches("Bread and BREAD", "bread") == [0, 10]
    assert gui.find_matches("x", "") == []


def test_display_name_puts_extras_last():
    from pathlib import Path
    import yt_slurp_gui as gui
    wav = {"kind": "wav", "title": "Talk: Part One?", "text": "",
           "path": Path("Talk Part One [dQw4w9WgXcQ] 2024-01-01 part 02 of 03.wav")}
    assert gui.display_name(wav) == "Talk: Part One?, part 02 of 03"
    assert gui.display_name({"kind": "skipped", "title": "T", "text": "private or deleted"}) == \
        "T (private or deleted)"


def test_instance_lock_blocks_second_window(tmp_path, monkeypatch):
    import yt_slurp_gui as gui
    monkeypatch.setenv("APPDATA", str(tmp_path))
    first = gui.InstanceLock()
    assert first.acquire()
    (tmp_path / gui.APP_NAME / "gui.lock").write_text(str(os.getppid()), encoding="utf-8")  # a live process
    second = gui.InstanceLock()
    assert not second.acquire()
    assert first.raise_wanted()


def test_text_index_matches_tk():
    import yt_slurp_gui as gui
    text = "ab\ncde\n\nfg"
    starts = gui.line_starts(text)
    assert [gui.text_index(starts, o) for o in (0, 2, 3, 5, 7, 8, 9)] == \
        ["1.0", "1.2", "2.0", "2.2", "3.0", "4.0", "4.1"]


def test_slurp_again_with_a_result_selected(app):
    """The crash from the field: select a result, then Slurp again."""
    run_fake(app)
    app.tree.selection_set(app.tree.get_children()[-1])
    app.root.update()
    app.settings["min_minutes"] = 1
    run_fake(app)
    assert len(app.items) > 0


def test_selected_survives_a_stale_row(app):
    run_fake(app)
    app.tree.selection_set(app.tree.get_children()[-1])
    app.items = []  # the list changed underneath the selection
    assert app.selected() is None


def test_update_button_appears_only_when_newer(app):
    app.show_update(None, quiet=True)
    assert not app.update_btn.winfo_ismapped()
    app.show_update({"version": "9.9.9", "url": "u", "page": "p", "notes": ""}, quiet=True)
    app.root.update()
    assert app.update_btn.winfo_ismapped() and app.update_btn.text == "Update to 9.9.9"


def test_progress_bar_still_while_waiting(app):
    app.start(["--help"], "Starting...")
    assert str(app.bar.cget("mode")) == "determinate"
    pump(app, lambda: idle(app))


def test_both_panes_show_a_scrollbar(app):
    app.root.geometry("1000x700")
    app.set_preview("line\n" * 500)
    app.root.update()
    bars = [w for w in (app.preview_text.master.winfo_children() + app.tree.master.winfo_children())
            if w.winfo_class() == "TScrollbar"]
    assert len(bars) == 2
    assert all(b.winfo_ismapped() and b.winfo_width() >= 5 for b in bars)
