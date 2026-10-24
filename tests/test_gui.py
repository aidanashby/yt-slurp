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
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
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
    pump(app, lambda: idle(app) and not getattr(app, "_redraw_job", None))
    assert app.stage == "Finished."


def test_first_run_setup_shows_a_progress_window(app, monkeypatch):
    import threading
    import yt_slurp_gui as gui
    release = threading.Event()

    def fake_install(name, progress=None, step=None):
        progress(21_000_000, 115_000_000)
        release.wait(10)
        step(f"Unpacking {name}")

    monkeypatch.setattr(gui.setup, "missing_tools", lambda: ["ffmpeg"])
    monkeypatch.setattr(gui.setup, "install_tool", fake_install)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    # The window runs its own tool check just after opening; calling it here as well would start two setups
    pump(app, lambda: app.setup_window is not None)
    win = app.setup_window
    pump(app, lambda: "21 of 115 MB" in win.detail.cget("text"))
    assert win.top.winfo_viewable()
    assert win.step.cget("text") == "Downloading ffmpeg (1 of 1)"
    release.set()
    pump(app, lambda: app.setup_window is None)
    assert app.stage == "Ready."


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
    assert [c.label for c in app.chips.values()] == ["Links", "Transcripts", "WAVs", "Skipped"]
    kinds_in_order = [app.items[int(i)]["kind"] for i in app.tree.get_children()]
    assert kinds_in_order == sorted(kinds_in_order, key=["link", "transcript", "wav", "skipped"].index)
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
    assert app.preview_text.get("1.0", "end").startswith("Has Captions")  # rendered heading
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


def test_new_items_do_not_move_a_scrolled_list(app):
    from pathlib import Path
    folder = Path("/tmp/fake-folder")
    app.current_folder = folder
    for i in range(60):
        app.add_item("link", folder, None, f"https://x/{i}", f"Video {i:02d}")
    app.redraw()
    app.root.update()
    app.tree.yview_moveto(0.5)
    app.root.update()
    where = app.tree.yview()[0]
    for i in range(5):  # more results arrive, grouped and sorted into the list
        app.add_item("transcript", folder, Path(f"/tmp/T{i} [abcdefghij{i}] 2024-01-01.md"), "", f"T{i}")
    pump(app, lambda: not getattr(app, "_redraw_job", None), timeout=5)
    assert abs(app.tree.yview()[0] - where) < 0.01  # stayed where the user scrolled


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


def test_make_gemini_notebook_files_is_a_separate_step(app):
    run_fake(app)
    folder = app.current_folder
    assert not (folder / ys.DIR_GEMINI).exists()
    app.make_gemini()
    pump(app, lambda: idle(app))
    assert any((folder / ys.DIR_GEMINI).glob("*.md"))


def test_md_segments_render_the_basics():
    import yt_slurp_gui as gui
    runs = gui.md_segments("# Title\n\n- **Channel:** C\\_D\n---\nSome **bold**, *italic* and <https://x.y>")
    text = "".join(t for t, _ in runs)
    assert text.startswith("Title\n\n•  Channel: C_D\n")
    assert ("Title", ("h1",)) in runs
    assert ("Channel:", ("bullet", "bold")) in runs
    assert ("bold", ("bold",)) in runs and ("italic", ("italic",)) in runs
    assert ("https://x.y", ("link",)) in runs
    assert any("hr" in tags for _, tags in runs)


def test_edit_save_replace_undo(app, monkeypatch):
    run_fake(app)
    iid = next(i for i in app.tree.get_children() if app.tree.item(i, "text") == "■  Has Captions")
    app.tree.selection_set(iid)
    app.root.update()
    path = app.edit_item["path"]
    # Viewing: rich text, Save greyed out and reading "Saved".
    assert not app.editing and app.save_btn.text == "Saved" and not app.save_btn.enabled
    # Clicking the pane switches to the Markdown source.
    app.start_editing()
    assert app.editing and app.editor_text().startswith("# Has Captions")
    app.editor.insert("end", "\nAn **added** line.")
    app.editor.event_generate("<<Modified>>")
    app.root.update()
    assert app.save_btn.text == "Save" and app.save_btn.enabled
    # Find and replace.
    app.text_search.var.set("hello")
    app.replace_box.var.set("goodbye")
    app.replace_all()
    assert "goodbye everyone" in app.editor_text()
    app.undo()
    assert "hello everyone" in app.editor_text()
    app.redo()
    assert "goodbye everyone" in app.editor_text()
    # Save.
    app.save_file()
    assert "goodbye everyone" in path.read_text(encoding="utf-8")
    assert app.save_btn.text == "Saved" and not app.save_btn.enabled
    # Leaving the pane shows the rendered view, with the bold made bold.
    app.show_view(app.editor_text())
    assert not app.editing
    assert "added" in app.preview_text.get("1.0", "end") and "**" not in app.preview_text.get("1.0", "end")


def test_unsaved_changes_prompt_when_switching(app, monkeypatch):
    import yt_slurp_gui as gui
    run_fake(app)
    iid = next(i for i in app.tree.get_children() if app.tree.item(i, "text") == "■  Has Captions")
    app.tree.selection_set(iid)
    app.root.update()
    app.start_editing()
    app.editor.insert("end", " more")
    asked = []
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *a, **k: asked.append(1) or False)
    other = next(i for i in app.tree.get_children() if i != iid)
    app.tree.selection_set(other)
    app.root.update()
    assert asked and app.edit_item is None or app.edit_item is not app.items[int(iid)]


def test_tools_shown_depend_on_selection(app):
    run_fake(app)
    def pick(pred):
        iid = next(i for i in app.tree.get_children() if pred(app.items[int(i)]))
        app.tree.selection_set(iid)
        app.root.update()
    pick(lambda it: it["kind"] == "transcript")
    assert app.save_btn in app.edit_bar.shown and app.delete_btn in app.edit_bar.shown
    pick(lambda it: it["kind"] == "link")
    assert app.edit_bar.shown == [app.delete_btn]
    pick(lambda it: it["kind"] == "skipped")
    assert app.edit_bar.shown == [app.delete_btn]


def test_multi_select_replace_and_delete(app, monkeypatch):
    import yt_slurp_gui as gui
    run_fake(app)
    folder = app.current_folder
    # Two transcripts: write a second one so there is something to replace across.
    t1 = next(it for it in app.items if it["kind"] == "transcript")
    t2 = t1["path"].with_name("Copy [copy0000001] 2024-01-02.md")
    t2.write_text(t1["path"].read_text(encoding="utf-8"), encoding="utf-8")
    app.show_folder(folder)
    app.root.update()
    iids = [i for i in app.tree.get_children() if app.items[int(i)]["kind"] in ("transcript", "link")]
    app.tree.selection_set(iids)
    app.root.update()
    assert app.multi and app.replace_all_btn in app.edit_bar.shown
    summary = app.preview_text.get("1.0", "end")
    assert "Can be edited (2)" in summary and "Can't be edited" in summary
    app.text_search.var.set("hello")
    app.run_search()
    assert app.match_label.cget("text") == "2 in 2 files"
    app.replace_box.var.set("goodbye")
    app.replace_all()
    assert app.save_btn.text == "Save"
    app.save_file()
    assert "goodbye" in t1["path"].read_text(encoding="utf-8") and "goodbye" in t2.read_text(encoding="utf-8")
    # Delete a link: its line leaves links.txt and stays gone.
    link = next(i for i in app.tree.get_children() if app.items[int(i)]["kind"] == "link")
    url = app.items[int(link)]["text"]
    app.tree.selection_set(link)
    app.root.update()
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    app.delete_selected()
    assert url not in (folder / "links.txt").read_text(encoding="utf-8")
    assert all(it.get("text") != url for it in app.items)
    # Delete a transcript.
    tr = next(i for i in app.tree.get_children() if app.items[int(i)]["kind"] == "transcript")
    path = app.items[int(tr)]["path"]
    app.tree.selection_set(tr)
    app.root.update()
    app.delete_selected()
    assert not path.exists()


def test_button_grows_to_fit_longer_text(app):
    import yt_slurp_gui as gui
    btn = gui.RoundButton(app.root, "Update", None)
    btn.set_text("Update to 10.20.30")
    need = gui.tkfont.Font(font=btn.font).measure("Update to 10.20.30")
    assert btn.w >= need + 10 and int(btn.cget("width")) == btn.w
    btn.set_text("Up")
    assert int(btn.cget("width")) == btn.w  # shrinking text keeps the width
    btn.destroy()
