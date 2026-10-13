"""Drive the real window with a fake network layer. Skipped without Tkinter or a display."""

import os
import time

import pytest

tk = pytest.importorskip("tkinter")

import yt_slurp as ys  # noqa: E402

from test_pipeline import FakeNet  # noqa: E402


def make_root():
    try:
        return tk.Tk()
    except tk.TclError:
        pytest.skip("no display")


@pytest.fixture
def app(monkeypatch, tmp_path):
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("no display")
    import yt_slurp_gui as gui
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(ys, "Net", FakeNet)
    monkeypatch.setattr(ys, "preflight", lambda: None)
    monkeypatch.setattr(gui, "open_path", lambda p: None)
    monkeypatch.setattr(gui.ChoiceDialog, "__init__",
                        lambda self, parent, q, opts: setattr(self, "result", "none"))
    gui.save_settings({**gui.DEFAULT_SETTINGS, "welcomed": True, "output": str(tmp_path / "out"),
                       "min_minutes": 2, "chunk_minutes": 1.5})
    root = make_root()
    instance = gui.InstanceLock()
    assert instance.acquire()
    a = gui.App(root, instance)
    yield a
    ys.set_ui(ys.ConsoleUI())
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


def test_slurp_shows_items_and_auto_merges(app):
    app.url_var.set("https://www.youtube.com/@test")
    app.slurp()
    pump(app, lambda: str(app.slurp_btn.cget("state")) == "normal")
    assert app.stage_label.cget("text") == "Finished."
    kinds = [it["kind"] for it in app.items]
    assert kinds.count("transcript") == 1 and kinds.count("wav") == 2 and kinds.count("link") >= 3
    assert len(app.tree.get_children()) == 1  # showing transcripts
    app.tree.selection_set(app.tree.get_children()[0])
    app.root.update()
    assert "Title: Has Captions" in app.preview_text.get("1.0", "end")
    app.show_var.set("wav")
    app.change_show()
    assert len(app.tree.get_children()) == 2
    assert "waiting for Whisper 1" in app.count_label.cget("text")

    # Save the Whisper text; the window merges it on its own.
    folder = app.current_folder
    for it in [i for i in app.items if i["kind"] == "wav"]:
        (folder / ys.DIR_WHISPER / it["path"].name.replace(".wav", ".txt")).write_text("Spoken words.",
                                                                                         encoding="utf-8")
    app.auto_merge()
    pump(app, lambda: str(app.slurp_btn.cget("state")) == "normal" and any(i["kind"] == "transcript" and "No Captions" in i["path"].name
                                                for i in app.items))
    assert ys.Manifest(folder / "manifest.csv").get("nocap000002")["status"] == "merged"


def test_build_argv_maps_settings():
    import yt_slurp_gui as gui
    s = {**gui.DEFAULT_SETTINGS, "ask_types": False, "types": ["videos", "streams"], "test_run": True,
         "limit": 3, "timestamps": True}
    argv = gui.build_argv(s, url="https://www.youtube.com/@x")
    assert argv[0] == "https://www.youtube.com/@x"
    assert argv[argv.index("--types") + 1] == "videos,streams"
    assert argv[argv.index("--limit") + 1] == "3" and "--timestamps" in argv
    assert gui.build_argv(gui.DEFAULT_SETTINGS, list_file="urls.txt")[:2] == ["--file", "urls.txt"]
    assert "--types" not in gui.build_argv(gui.DEFAULT_SETTINGS, url="u")


def test_instance_lock_blocks_second_window(tmp_path, monkeypatch):
    import yt_slurp_gui as gui
    monkeypatch.setenv("APPDATA", str(tmp_path))
    first = gui.InstanceLock()
    assert first.acquire()
    (tmp_path / gui.APP_NAME / "gui.lock").write_text(str(os.getppid()), encoding="utf-8")  # a live process
    second = gui.InstanceLock()
    assert not second.acquire()
    assert first.raise_wanted()
