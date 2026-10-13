"""yt-slurp window: paste a link, click Slurp, watch transcripts, WAVs or links appear.

Started by yt-slurp.bat (or "yt-slurp gui"). The pipeline itself lives in
yt_slurp.py; this module supplies a UI object for it and runs it on a worker
thread so the window stays responsive.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import wave
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import yt_slurp as ys

APP_NAME = "yt-slurp"
REPO_DIR = Path(__file__).resolve().parent
AUTO_MERGE_EVERY_MS = 5000
POLL_MS = 100

LANGUAGES = [
    ("en", "English"), ("es", "Spanish"), ("fr", "French"), ("de", "German"), ("it", "Italian"),
    ("pt", "Portuguese"), ("nl", "Dutch"), ("pl", "Polish"), ("ar", "Arabic"), ("he", "Hebrew"),
    ("el", "Greek"), ("ru", "Russian"), ("uk", "Ukrainian"), ("hi", "Hindi"), ("zh", "Chinese"),
    ("ja", "Japanese"), ("ko", "Korean"),
]
SHOW_OPTIONS = [("transcript", "Transcripts"), ("wav", "WAV files"), ("link", "Links")]
KIND_LABEL = {"transcript": "Transcript", "wav": "WAV", "link": "Link"}


# =============================================================================
# Settings
# =============================================================================

def settings_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


DEFAULT_SETTINGS = {
    "ask_types": True,
    "types": ["videos"],
    "min_minutes": 5,
    "lang": "en",
    "timestamps": False,
    "links_only": False,
    "test_run": False,
    "limit": 5,
    "include_non_english": False,
    "chunk_minutes": 60,
    "batch_files": 10,
    "output": str(REPO_DIR / "output"),
    "whisper_path": "",
    "whisper_title": "Whisper",
    "show": "transcript",
    "chunk_words": ys.DEFAULT_CHUNK_WORDS,
    "max_sources": ys.DEFAULT_MAX_SOURCES,
    "max_source_words": ys.DEFAULT_MAX_SOURCE_WORDS,
    "welcomed": False,
}


def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    try:
        data.update(json.loads((settings_dir() / "settings.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return data


def save_settings(data: dict) -> None:
    folder = settings_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "settings.json.tmp"
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, folder / "settings.json")


def build_argv(settings: dict, url: str = "", list_file: str = "") -> list[str]:
    """Turn the window's settings into yt-slurp command-line arguments."""
    argv = ["--file", list_file] if list_file else [url]
    argv += ["--output", settings["output"],
             "--min-minutes", str(settings["min_minutes"]),
             "--lang", settings["lang"],
             "--chunk-minutes", str(settings["chunk_minutes"]),
             "--batch-files", str(settings["batch_files"]),
             "--chunk-words", str(settings["chunk_words"]),
             "--max-sources", str(settings["max_sources"]),
             "--max-source-words", str(settings["max_source_words"])]
    if not settings["ask_types"] and settings["types"]:
        argv += ["--types", ",".join(settings["types"])]
    if settings["timestamps"]:
        argv.append("--timestamps")
    if settings["links_only"]:
        argv.append("--links-only")
    if settings["test_run"]:
        argv += ["--limit", str(settings["limit"])]
    if settings["include_non_english"]:
        argv.append("--include-non-english")
    return argv


# =============================================================================
# Single instance
# =============================================================================

class InstanceLock:
    """One window at a time. A second launch asks the first to come to the front."""

    def __init__(self):
        self.lock = settings_dir() / "gui.lock"
        self.raise_request = settings_dir() / "raise.request"

    def acquire(self) -> bool:
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            other = int(self.lock.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            other = 0
        if other and other != os.getpid() and ys.pid_alive(other):
            self.raise_request.write_text(str(time.time()), encoding="utf-8")
            return False
        self.lock.write_text(str(os.getpid()), encoding="utf-8")
        return True

    def raise_wanted(self) -> bool:
        if self.raise_request.exists():
            self.raise_request.unlink(missing_ok=True)
            return True
        return False

    def release(self) -> None:
        try:
            if self.lock.read_text(encoding="utf-8").strip() == str(os.getpid()):
                self.lock.unlink()
        except OSError:
            pass


# =============================================================================
# Windows helpers
# =============================================================================

def open_path(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        messagebox.showinfo(APP_NAME, f"{path} does not exist yet.")
        return
    if os.name == "nt":
        os.startfile(str(path))  # noqa: S606 (opens with the usual program)
    else:
        subprocess.Popen(["xdg-open", str(path)])


def find_window(title_part: str):
    """Handle of a visible top-level window whose title contains title_part (Windows only)."""
    if os.name != "nt" or not title_part:
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []
    own = os.getpid()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != own and title_part.lower() in buf.value.lower():
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def bring_to_front(hwnd) -> None:
    import ctypes
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)


def wav_info(path: Path) -> str:
    try:
        with wave.open(str(path), "rb") as w:
            secs = w.getnframes() / float(w.getframerate())
            rate, ch = w.getframerate(), w.getnchannels()
    except (OSError, wave.Error, ZeroDivisionError):
        return f"{path.name}\n\n(could not read the WAV header)"
    size_mb = path.stat().st_size / 1_000_000
    batch = path.parent.name if path.parent.name.startswith("batch") else "no batch folder"
    return (f"{path.name}\n\nLength: {ys.fmt_duration(secs)}\nFormat: {rate} Hz, "
            f"{'mono' if ch == 1 else f'{ch} channels'}, 16-bit\nSize: {size_mb:.1f} MB\n"
            f"Folder: {batch}\n\nDrag it into the Whisper app, then save the text into "
            f"{ys.DIR_WHISPER}.")


# =============================================================================
# The UI object the pipeline talks to (runs on the worker thread)
# =============================================================================

class GuiUI:
    gui = True  # makes yt_slurp word its advice for the window, not the command line

    def __init__(self, app: "App"):
        self.app = app

    def _post(self, *msg):
        self.app.events.put(msg)

    def _ask(self, kind, *data):
        reply = {"event": threading.Event(), "value": None}
        self._post("ask", kind, data, reply)
        reply["event"].wait()
        return reply["value"]

    def say(self, msg: str = "") -> None:
        self._post("log", msg)

    def progress(self, stage: str, done: int, total: int) -> None:
        self._post("progress", stage, done, total)

    def counts(self, folder, counts) -> None:
        self._post("counts", Path(folder), dict(counts))

    def item(self, kind, folder, path=None, text="") -> None:
        self._post("item", kind, Path(folder), Path(path) if path else None, text)

    def choose(self, question, options):
        return self._ask("choose", question, options)

    def confirm_delete(self, message) -> bool:
        return bool(self._ask("confirm_delete", message))

    def choose_types(self, found):
        return self._ask("types", found)


# =============================================================================
# The window
# =============================================================================

class App:
    def __init__(self, root: tk.Tk, instance: InstanceLock):
        self.root = root
        self.instance = instance
        self.settings = load_settings()
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.items: list[dict] = []
        self.current_folder: Path | None = None
        self.list_file = ""
        self.smoke_waiting = False
        ys.set_ui(GuiUI(self))

        root.title("yt-slurp")
        root.geometry("1250x820")
        root.minsize(980, 640)
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 6))
        style.configure("Head.TLabel", font=("Segoe UI", 10, "bold"))

        self.build_menu()
        self.build_top()
        self.build_middle()
        self.build_bottom()
        self.refresh_sources()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(POLL_MS, self.poll)
        root.after(AUTO_MERGE_EVERY_MS, self.auto_merge)
        if not self.settings["welcomed"]:
            root.after(300, self.welcome)

    # ----- layout -----

    def build_menu(self):
        bar = tk.Menu(self.root)
        tools = tk.Menu(bar, tearoff=False)
        tools.add_command(label="Check the Whisper app keeps filenames", command=self.smoke_test)
        tools.add_command(label="Merge Whisper text now", command=self.merge_now)
        tools.add_command(label="Open the manifest in Excel", command=self.open_manifest)
        tools.add_separator()
        tools.add_command(label="Run the self-test", command=self.self_test)
        bar.add_cascade(label="Tools", menu=tools)
        helpm = tk.Menu(bar, tearoff=False)
        helpm.add_command(label="How to use yt-slurp", command=self.welcome)
        bar.add_cascade(label="Help", menu=helpm)
        self.root.config(menu=bar)

    def build_top(self):
        top = ttk.Frame(self.root, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Channel or playlist link:", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(top, textvariable=self.url_var, font=("Segoe UI", 11))
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=6)
        self.url_entry.bind("<Return>", lambda e: self.slurp())
        self.slurp_btn = ttk.Button(top, text="Slurp", style="Big.TButton", command=self.slurp)
        self.slurp_btn.grid(row=0, column=2, padx=(6, 0))
        self.stop_btn = ttk.Button(top, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.grid(row=0, column=3, padx=(6, 0))

        ttk.Button(top, text="Use a list of links from a file...", command=self.pick_list).grid(
            row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        self.list_label = ttk.Label(top, text="", foreground="#555")
        self.list_label.grid(row=1, column=1, sticky="e", padx=6, pady=(6, 0))
        ttk.Label(top, text="Or pick one you've done before:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.source_var = tk.StringVar()
        self.source_box = ttk.Combobox(top, textvariable=self.source_var, state="readonly")
        self.source_box.grid(row=2, column=1, sticky="ew", padx=6, pady=(6, 0))
        self.source_box.bind("<<ComboboxSelected>>", self.pick_source)
        top.columnconfigure(1, weight=1)

    def build_middle(self):
        panes = ttk.PanedWindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=4)
        panes.add(self.build_settings(panes), weight=0)

        out = ttk.Frame(panes)
        panes.add(out, weight=1)
        head = ttk.Frame(out)
        head.pack(fill="x")
        ttk.Label(head, text="Show:", style="Head.TLabel").pack(side="left")
        self.show_var = tk.StringVar(value=self.settings["show"])
        for key, label in SHOW_OPTIONS:
            ttk.Radiobutton(head, text=label, value=key, variable=self.show_var,
                            command=self.change_show).pack(side="left", padx=6)
        self.count_label = ttk.Label(head, text="", foreground="#333")
        self.count_label.pack(side="right")

        split = ttk.PanedWindow(out, orient="horizontal")
        split.pack(fill="both", expand=True, pady=(4, 0))
        listf = ttk.Frame(split)
        self.tree = ttk.Treeview(listf, columns=("time", "name"), show="headings", selectmode="browse")
        self.tree.heading("time", text="Time")
        self.tree.heading("name", text="Name")
        self.tree.column("time", width=70, stretch=False)
        self.tree.column("name", width=420)
        sb = ttk.Scrollbar(listf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.preview)
        self.tree.bind("<Double-1>", self.open_selected)
        split.add(listf, weight=1)

        prevf = ttk.Frame(split)
        self.preview_text = tk.Text(prevf, wrap="word", font=("Segoe UI", 10), padx=8, pady=6,
                                    state="disabled", relief="flat", background="#fbfbfb")
        psb = ttk.Scrollbar(prevf, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=psb.set)
        self.preview_text.pack(side="left", fill="both", expand=True)
        psb.pack(side="right", fill="y")
        split.add(prevf, weight=1)

    def build_settings(self, parent):
        outer = ttk.Frame(parent, width=370)
        canvas = tk.Canvas(outer, width=360, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas, padding=(0, 0, 8, 0))
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units")
                        if str(e.widget).startswith(str(canvas)) else None)

        s = self.settings
        self.vars: dict[str, tk.Variable] = {}

        def section(text):
            ttk.Label(frame, text=text, style="Head.TLabel").pack(anchor="w", pady=(10, 2))

        def check(key, text, command=None):
            v = tk.BooleanVar(value=s[key])
            self.vars[key] = v
            ttk.Checkbutton(frame, text=text, variable=v, command=command or self.store).pack(anchor="w")
            return v

        def number(key, before, after, lo, hi):
            row = ttk.Frame(frame)
            row.pack(anchor="w", pady=1)
            ttk.Label(row, text=before).pack(side="left")
            v = tk.StringVar(value=str(s[key]))
            self.vars[key] = v
            sp = ttk.Spinbox(row, from_=lo, to=hi, width=7, textvariable=v, command=self.store)
            sp.pack(side="left", padx=4)
            sp.bind("<FocusOut>", lambda e: self.store())
            ttk.Label(row, text=after).pack(side="left")

        section("Which videos")
        check("ask_types", "Ask me each time", command=self.toggle_types)
        self.type_checks = []
        chosen = set(s["types"])
        self.type_vars = {}
        for key, label in (("videos", "Normal videos"), ("shorts", "Shorts"), ("streams", "Live streams")):
            v = tk.BooleanVar(value=key in chosen)
            self.type_vars[key] = v
            cb = ttk.Checkbutton(frame, text=label, variable=v, command=self.store)
            cb.pack(anchor="w", padx=(20, 0))
            self.type_checks.append(cb)
        number("min_minutes", "Skip videos shorter than", "minutes", 0, 600)
        check("test_run", "Test run: only do the first few videos")
        number("limit", "How many in a test run:", "", 1, 1000)

        section("Transcripts")
        row = ttk.Frame(frame)
        row.pack(anchor="w", pady=1)
        ttk.Label(row, text="Caption language:").pack(side="left")
        self.lang_var = tk.StringVar(value=dict(LANGUAGES).get(s["lang"], s["lang"]))
        lb = ttk.Combobox(row, textvariable=self.lang_var, width=14, values=[n for _, n in LANGUAGES])
        lb.pack(side="left", padx=4)
        lb.bind("<<ComboboxSelected>>", lambda e: self.store())
        lb.bind("<FocusOut>", lambda e: self.store())
        check("timestamps", "Add the time at the start of each paragraph")
        check("links_only", "Only make the list of links")

        section("Videos without captions")
        check("include_non_english", "Make WAVs for videos not in English")
        number("chunk_minutes", "Split long audio into parts of", "minutes", 0, 600)
        number("batch_files", "Put", "WAV files in each batch folder", 0, 500)

        section("Where things go")
        self.output_var = tk.StringVar(value=s["output"])
        ttk.Label(frame, textvariable=self.output_var, wraplength=330, foreground="#333").pack(anchor="w")
        ttk.Button(frame, text="Change results folder...", command=self.pick_output).pack(anchor="w", pady=2)

        section("Whisper app")
        self.whisper_var = tk.StringVar(value=s["whisper_path"] or "Not set yet")
        ttk.Label(frame, textvariable=self.whisper_var, wraplength=330, foreground="#333").pack(anchor="w")
        ttk.Button(frame, text="Choose the Whisper app...", command=self.pick_whisper).pack(anchor="w", pady=2)
        row = ttk.Frame(frame)
        row.pack(anchor="w", pady=1)
        ttk.Label(row, text="Its window title contains:").pack(side="left")
        v = tk.StringVar(value=s["whisper_title"])
        self.vars["whisper_title"] = v
        e = ttk.Entry(row, textvariable=v, width=14)
        e.pack(side="left", padx=4)
        e.bind("<FocusOut>", lambda ev: self.store())

        self.adv_shown = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Show advanced settings", variable=self.adv_shown,
                        command=self.toggle_advanced).pack(anchor="w", pady=(12, 0))
        self.adv = ttk.Frame(frame)
        for key, before, after, hi in (("chunk_words", "Words per Claude file:", "", 2_000_000),
                                       ("max_sources", "Gemini Notebook sources:", "", 1000),
                                       ("max_source_words", "Words per Gemini source:", "", 500_000)):
            r = ttk.Frame(self.adv)
            r.pack(anchor="w", pady=1)
            ttk.Label(r, text=before).pack(side="left")
            vv = tk.StringVar(value=str(s[key]))
            self.vars[key] = vv
            sp = ttk.Spinbox(r, from_=1, to=hi, width=9, textvariable=vv, command=self.store)
            sp.pack(side="left", padx=4)
            sp.bind("<FocusOut>", lambda ev: self.store())
        self.toggle_types(save=False)
        return outer

    def build_bottom(self):
        bottom = ttk.Frame(self.root, padding=(10, 4, 10, 10))
        bottom.pack(fill="x")
        prog = ttk.Frame(bottom)
        prog.pack(fill="x")
        self.stage_label = ttk.Label(prog, text="Ready.")
        self.stage_label.pack(side="left")
        self.bar = ttk.Progressbar(prog, mode="determinate", length=320)
        self.bar.pack(side="right")

        logf = ttk.Frame(bottom)
        logf.pack(fill="x", pady=4)
        self.log = tk.Text(logf, height=7, wrap="word", font=("Consolas", 9), state="disabled",
                           relief="flat", background="#f3f3f3")
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="x", expand=True)
        lsb.pack(side="right", fill="y")

        btns = ttk.Frame(bottom)
        btns.pack(fill="x")
        for text, cmd in (("Open results folder", self.open_results),
                          ("Open WAV folder", self.open_wavs),
                          ("Launch Whisper app", self.launch_whisper),
                          ("Open Claude files", lambda: self.open_sub(ys.DIR_CLAUDE)),
                          ("Open Gemini files", lambda: self.open_sub(ys.DIR_GEMINI))):
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 6))

    # ----- settings -----

    def store(self):
        s = self.settings
        for key, var in self.vars.items():
            val = var.get()
            if key in ("min_minutes", "chunk_minutes"):
                try:
                    val = float(val)
                    val = int(val) if val == int(val) else val
                except ValueError:
                    val = DEFAULT_SETTINGS[key]
            elif key in ("limit", "batch_files", "chunk_words", "max_sources", "max_source_words"):
                try:
                    val = max(0, int(float(val)))
                except ValueError:
                    val = DEFAULT_SETTINGS[key]
            s[key] = val
        s["types"] = [k for k, v in self.type_vars.items() if v.get()]
        name = self.lang_var.get().strip()
        s["lang"] = next((c for c, n in LANGUAGES if n.lower() == name.lower()), name.lower() or "en")
        save_settings(s)

    def toggle_types(self, save=True):
        state = "disabled" if self.vars["ask_types"].get() else "normal"
        for cb in self.type_checks:
            cb.configure(state=state)
        if save:
            self.store()

    def toggle_advanced(self):
        if self.adv_shown.get():
            self.adv.pack(anchor="w", padx=(20, 0))
        else:
            self.adv.pack_forget()

    def pick_output(self):
        d = filedialog.askdirectory(title="Where should yt-slurp save results?",
                                    initialdir=self.settings["output"])
        if d:
            self.settings["output"] = d
            self.output_var.set(d)
            self.store()
            self.refresh_sources()

    def pick_whisper(self):
        f = filedialog.askopenfilename(
            title="Choose the Whisper app (its .exe, .bat, .py or shortcut)",
            filetypes=[("Programs and scripts", "*.exe *.bat *.cmd *.py *.pyw *.lnk"), ("All files", "*.*")])
        if f:
            self.settings["whisper_path"] = f
            self.whisper_var.set(f)
            self.store()

    def pick_list(self):
        f = filedialog.askopenfilename(title="Choose a text file with one link per line",
                                       filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f:
            self.list_file = f
            self.url_var.set("")
            self.list_label.configure(text=f"Using links from {Path(f).name}  (type a link to use that instead)")

    # ----- previous sources -----

    def sources(self) -> list[tuple[str, Path, dict]]:
        out = Path(self.settings["output"])
        found = []
        if out.is_dir():
            for d in sorted(out.iterdir()):
                run = ys.load_run(d) if d.is_dir() else {}
                if run.get("url") or (d / "manifest.csv").exists():
                    found.append((run.get("name") or d.name, d, run))
        return found

    def refresh_sources(self):
        self._sources = self.sources()
        self.source_box.configure(values=[name for name, _, _ in self._sources])

    def pick_source(self, _=None):
        idx = self.source_box.current()
        if idx < 0:
            return
        name, folder, run = self._sources[idx]
        if run.get("url"):
            self.url_var.set(run["url"])
            self.list_file = ""
            self.list_label.configure(text="")
        self.show_folder(folder)

    def show_folder(self, folder: Path):
        """List what already exists in a folder."""
        self.current_folder = folder
        self.items = []
        for p in sorted((folder / ys.DIR_TRANSCRIPTS).glob("*.txt")) if (folder / ys.DIR_TRANSCRIPTS).is_dir() else []:
            self.items.append({"kind": "transcript", "path": p, "text": "", "time": ""})
        needs = folder / ys.DIR_NEEDS
        if needs.is_dir():
            for p in sorted(needs.rglob("*.wav")):
                self.items.append({"kind": "wav", "path": p, "text": "", "time": ""})
        links = folder / "links.txt"
        if links.exists():
            for line in ys.read_text(links).splitlines():
                self.items.append({"kind": "link", "path": links, "text": line, "time": ""})
        self.redraw()
        man = folder / "manifest.csv"
        if man.exists():
            self.show_counts(ys.Manifest(man).counts())

    # ----- output panel -----

    def change_show(self):
        self.settings["show"] = self.show_var.get()
        save_settings(self.settings)
        self.redraw()

    def redraw(self):
        self.tree.delete(*self.tree.get_children())
        for i, it in enumerate(self.items):
            if it["kind"] == self.show_var.get():
                self.insert_row(i, it)
        self.set_preview("")

    def insert_row(self, i, it):
        name = it["text"] if it["kind"] == "link" else it["path"].name
        self.tree.insert("", "end", iid=str(i), values=(it["time"], name))
        self.tree.see(str(i))

    def add_item(self, kind, folder, path, text):
        if self.current_folder != folder:
            self.current_folder = folder
            self.items = []
            self.redraw()
        it = {"kind": kind, "path": path, "text": text, "time": time.strftime("%H:%M:%S")}
        self.items.append(it)
        if kind == self.show_var.get():
            self.insert_row(len(self.items) - 1, it)

    def selected(self):
        sel = self.tree.selection()
        return self.items[int(sel[0])] if sel else None

    def preview(self, _=None):
        it = self.selected()
        if not it:
            return
        if it["kind"] == "transcript":
            try:
                self.set_preview(ys.read_text(it["path"]))
            except OSError:
                self.set_preview("(file no longer there)")
        elif it["kind"] == "wav":
            self.set_preview(wav_info(it["path"]) if it["path"].exists() else "(file no longer there)")
        else:
            parts = it["text"].split(" | ")
            self.set_preview("\n".join(parts))

    def set_preview(self, text):
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def open_selected(self, _=None):
        it = self.selected()
        if not it:
            return
        if it["kind"] == "transcript":
            open_path(it["path"])
        elif it["kind"] == "wav":
            open_path(it["path"].parent)
        else:
            import webbrowser
            webbrowser.open(it["text"].split(" | ")[-1])

    def show_counts(self, counts):
        names = (("transcript", "transcripts"), ("merged", "merged"), ("wav", "waiting for Whisper"),
                 ("pending", "to do"), ("needs-signin", "need sign-in"), ("failed", "failed"))
        parts = [f"{label} {counts[k]}" for k, label in names if counts.get(k)]
        skipped = sum(v for k, v in counts.items() if k.startswith("skipped"))
        if skipped:
            parts.append(f"skipped {skipped}")
        self.count_label.configure(text=", ".join(parts))

    # ----- log and progress -----

    def write_log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ----- running -----

    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start(self, argv, label, after=None):
        if self.busy():
            messagebox.showinfo(APP_NAME, "yt-slurp is already working. Wait for it to finish, or click Stop.")
            return
        self.slurp_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.stage_label.configure(text=label)
        self.bar.configure(mode="indeterminate")
        self.bar.start(15)

        def work():
            code = ys.run_command(argv)
            self.events.put(("done", code, after))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def slurp(self):
        self.store()
        url = self.url_var.get().strip()
        if url:
            self.list_file = ""
            self.list_label.configure(text="")
        if not url and not self.list_file:
            messagebox.showinfo(APP_NAME, "Paste a YouTube channel or playlist link first.")
            self.url_entry.focus_set()
            return
        if url:
            kind, _, note = ys.classify_url(url)
            if kind == "video":
                messagebox.showinfo(APP_NAME, "That is a link to a single video. yt-slurp works on whole "
                                              "channels and playlists. To do one video, add it to a playlist "
                                              "of its own (it can be unlisted) and paste the playlist link.")
                return
            if kind == "unknown":
                messagebox.showinfo(APP_NAME, f"That link doesn't look right: {note}.")
                return
        self.items = []
        self.current_folder = None
        self.redraw()
        self.write_log("")
        self.start(build_argv(self.settings, url, self.list_file), "Starting...")

    def stop(self):
        ys.STOP.set()
        self.stop_btn.configure(state="disabled")
        self.stage_label.configure(text="Stopping after the current step...")

    def finished(self, code, after):
        self.bar.stop()
        self.bar.configure(mode="determinate", value=0)
        self.slurp_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.stage_label.configure(text={0: "Finished.", 130: "Stopped. Click Slurp again to carry on."}
                                   .get(code, "Stopped with a problem. See the messages below."))
        self.refresh_sources()
        if after:
            after(code)

    # ----- events from the worker -----

    def poll(self):
        try:
            while True:
                msg = self.events.get_nowait()
                self.handle(msg)
        except queue.Empty:
            pass
        if self.instance.raise_wanted():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        self.root.after(POLL_MS, self.poll)

    def handle(self, msg):
        kind = msg[0]
        if kind == "log":
            self.write_log(msg[1])
        elif kind == "progress":
            _, stage, done, total = msg
            self.bar.stop()
            self.bar.configure(mode="determinate", maximum=max(total, 1), value=done)
            self.stage_label.configure(text=f"{stage}: {done} of {total}")
        elif kind == "counts":
            _, folder, counts = msg
            if self.current_folder in (None, folder):
                self.current_folder = folder
                self.show_counts(counts)
        elif kind == "item":
            _, ikind, folder, path, text = msg
            self.add_item(ikind, folder, path, text)
            if self.smoke_waiting and ikind == "transcript" and folder.name == "smoke-test":
                self.smoke_waiting = False
                messagebox.showinfo(APP_NAME, "Test passed. The Whisper app kept the filenames, and the "
                                              "two parts were merged into one transcript.")
        elif kind == "ask":
            _, akind, data, reply = msg
            try:
                reply["value"] = self.answer(akind, data)
            finally:
                reply["event"].set()
        elif kind == "done":
            self.finished(msg[1], msg[2])

    def answer(self, akind, data):
        if akind == "choose":
            question, options = data
            return ChoiceDialog(self.root, question, options).result
        if akind == "confirm_delete":
            return messagebox.askyesno(APP_NAME, data[0] + "\n\nDelete them?", icon="warning", default="no")
        if akind == "types":
            return TypesDialog(self.root, data[0]).result
        return None

    # ----- automatic merge -----

    def auto_merge(self):
        try:
            if not self.busy():
                for _, folder, _ in self.sources():
                    if ys.mergeable_ids(folder):
                        self.write_log(f"\nWhisper text found for {folder.name}. Merging...")
                        self.start(["merge", str(folder)] + self.combined_args(), "Merging Whisper text...")
                        break
        except Exception as e:  # never let a background check kill the window
            self.write_log(f"(Automatic merge check failed: {e})")
        self.root.after(AUTO_MERGE_EVERY_MS, self.auto_merge)

    def combined_args(self):
        s = self.settings
        return ["--chunk-words", str(s["chunk_words"]), "--max-sources", str(s["max_sources"]),
                "--max-source-words", str(s["max_source_words"])]

    def merge_now(self):
        folder = self.current_folder or self.ask_folder()
        if folder:
            self.start(["merge", str(folder)] + self.combined_args(), "Merging Whisper text...")

    def ask_folder(self):
        d = filedialog.askdirectory(title="Choose the channel or playlist folder", initialdir=self.settings["output"])
        return Path(d) if d else None

    # ----- buttons -----

    def folder_or_ask(self):
        if self.current_folder:
            return self.current_folder
        messagebox.showinfo(APP_NAME, "Slurp something first, or pick one you've done before at the top.")
        return None

    def open_results(self):
        open_path(self.current_folder or Path(self.settings["output"]))

    def open_sub(self, sub):
        folder = self.folder_or_ask()
        if folder:
            open_path(folder / sub)

    def open_wavs(self):
        folder = self.folder_or_ask()
        if not folder:
            return
        man = folder / "manifest.csv"
        waiting = []
        if man.exists():
            waiting = sorted({int(r["batch"]) for r in ys.Manifest(man).rows.values()
                              if r["status"] == "wav" and r["batch"].isdigit()})
        target = folder / ys.DIR_NEEDS
        if waiting:
            target = target / ys.batch_dir_name(waiting[0])
        elif man.exists() and not any(r["status"] == "wav" for r in ys.Manifest(man).rows.values()):
            messagebox.showinfo(APP_NAME, "No WAV files are waiting for the Whisper app in this folder.")
            return
        open_path(target)

    def launch_whisper(self):
        s = self.settings
        hwnd = find_window(s["whisper_title"])
        if hwnd:
            bring_to_front(hwnd)
            return
        if not s["whisper_path"] or not Path(s["whisper_path"]).exists():
            messagebox.showinfo(APP_NAME, "Show yt-slurp where the Whisper app is. Choose its .exe, .bat, "
                                          ".py file or shortcut.")
            self.pick_whisper()
            if not s["whisper_path"]:
                return
        path = Path(s["whisper_path"])
        if os.name == "nt":
            os.startfile(str(path), cwd=str(path.parent))
        else:
            subprocess.Popen([str(path)], cwd=str(path.parent))

    def open_manifest(self):
        folder = self.folder_or_ask()
        if folder:
            open_path(folder / "manifest.csv")

    # ----- tools -----

    def smoke_test(self):
        folder = Path(self.settings["output"]) / "smoke-test"
        if (folder / "manifest.csv").exists():
            if not messagebox.askyesno(APP_NAME, "A smoke test already exists. Make fresh test files?"):
                return
            import shutil
            shutil.rmtree(folder, ignore_errors=True)

        def after(code):
            if code != 0:
                return
            self.show_folder(folder)
            self.smoke_waiting = True
            open_path(folder / ys.DIR_NEEDS / ys.batch_dir_name(1))
            messagebox.showinfo(
                APP_NAME,
                "Two short test WAVs are ready, and their folder is open.\n\n"
                "1. Click Launch Whisper app, and drag both WAVs into it.\n"
                "2. When they finish, click Save as .txt for each one.\n"
                f"3. Save them into:\n{folder / ys.DIR_WHISPER}\n"
                "   Keep the suggested name. Check it still has the [AbC-d_123xY] part.\n\n"
                "yt-slurp merges them by itself and tells you when the test has passed. If nothing "
                "happens a few seconds after you save both, the filenames were changed: tell Claude "
                "exactly how the saved names differ.")

        self.start(["smoke-wav", str(folder)], "Making the test WAVs...", after)

    def self_test(self):
        if self.busy():
            messagebox.showinfo(APP_NAME, "Wait for the current job to finish first.")
            return
        self.write_log("\nRunning the self-test...")
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(REPO_DIR), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", **ys.NO_WINDOW)
        last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        self.write_log(r.stdout[-3000:])
        if r.returncode == 0:
            messagebox.showinfo(APP_NAME, f"Self-test passed: {last}")
        else:
            messagebox.showwarning(APP_NAME, f"Self-test failed: {last}\n\nThe details are in the messages below.")

    def welcome(self):
        messagebox.showinfo(
            "How to use yt-slurp",
            "1. Paste a YouTube channel or playlist link at the top, and click Slurp.\n\n"
            "2. Questions pop up when yt-slurp needs an answer, for example which kinds of video to include.\n\n"
            "3. Results appear on the right as they are made. Choose Transcripts, WAV files or Links above "
            "the list. Click one to read it; double-click to open it.\n\n"
            "4. Videos without captions become WAV files. Click Open WAV folder and Launch Whisper app, "
            "drag the WAVs in, and save each transcript into the whisper-transcripts folder. yt-slurp "
            "merges them by itself.\n\n"
            "5. The files for Claude and Gemini Notebook are under Open Claude files and Open Gemini files.\n\n"
            "Before your first real batch, use Tools, then Check the Whisper app keeps filenames.")
        self.settings["welcomed"] = True
        save_settings(self.settings)

    def on_close(self):
        if self.busy():
            if not messagebox.askyesno(APP_NAME, "yt-slurp is still working. Stop it and close? "
                                                 "Progress so far is saved."):
                return
            ys.STOP.set()
            self.worker.join(timeout=10)
        self.store()
        self.instance.release()
        self.root.destroy()


# =============================================================================
# Dialogs
# =============================================================================

class ChoiceDialog:
    """A question with one button per answer. Closing it picks the cautious
    answer: keep what exists, or don't use a browser."""

    def __init__(self, parent, question, options):
        self.result = next((k for k, _ in options if k in ("update", "none")), options[-1][0])
        top = self.top = tk.Toplevel(parent)
        top.title(APP_NAME)
        top.transient(parent)
        top.resizable(False, False)
        frame = ttk.Frame(top, padding=16)
        frame.pack(fill="both")
        ttk.Label(frame, text=question, wraplength=420, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))
        for key, label in options:
            ttk.Button(frame, text=label, command=lambda k=key: self.pick(k)).pack(fill="x", pady=2)
        top.protocol("WM_DELETE_WINDOW", top.destroy)
        top.grab_set()
        top.lift()
        parent.wait_window(top)

    def pick(self, key):
        self.result = key
        self.top.destroy()


class TypesDialog:
    """Tick boxes for which kinds of video to include, with counts per channel."""

    def __init__(self, parent, found):
        self.result = set()
        totals = {}
        for _, counts in found:
            for t, n in counts.items():
                totals[t] = totals.get(t, 0) + n
        top = self.top = tk.Toplevel(parent)
        top.title(APP_NAME)
        top.transient(parent)
        top.resizable(False, False)
        frame = ttk.Frame(top, padding=16)
        frame.pack(fill="both")
        ttk.Label(frame, text="Which kinds of video should yt-slurp include?",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        if len(found) > 1:
            for name, counts in found:
                ttk.Label(frame, text=f"{name}: " + ", ".join(f"{n} {t}" for t, n in counts.items()),
                          foreground="#555").pack(anchor="w")
        self.vars = {}
        labels = {"videos": "Normal videos", "shorts": "Shorts", "streams": "Live streams"}
        for t in ys.TYPES:
            if t in totals:
                v = tk.BooleanVar(value=(t == "videos"))
                self.vars[t] = v
                ttk.Checkbutton(frame, text=f"{labels[t]} ({totals[t]})", variable=v).pack(anchor="w", pady=2)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="All of them", command=self.all).pack(side="left")
        ttk.Button(row, text="Carry on", command=self.ok).pack(side="right")
        top.protocol("WM_DELETE_WINDOW", self.ok)
        top.grab_set()
        parent.wait_window(top)

    def all(self):
        self.result = set(self.vars)
        self.top.destroy()

    def ok(self):
        self.result = {t for t, v in self.vars.items() if v.get()}
        self.top.destroy()


# =============================================================================
# Start
# =============================================================================

def main() -> int:
    instance = InstanceLock()
    if not instance.acquire():
        return 0  # the open window has been asked to come to the front
    root = tk.Tk()
    root.report_callback_exception = report_crash
    try:
        App(root, instance)
        root.mainloop()
    except Exception:
        report_crash(*sys.exc_info())
        return 1
    finally:
        instance.release()
    return 0


def report_crash(exc_type, exc, tb) -> None:
    """pythonw has no console, so write errors to a log and show them."""
    import traceback
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log = settings_dir() / "error.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{text}")
    except OSError:
        pass
    try:
        messagebox.showerror(APP_NAME, f"Something went wrong:\n\n{exc}\n\nThe details are in {log}. "
                                       "Send that file to Claude.")
    except tk.TclError:
        pass


if __name__ == "__main__":
    sys.exit(main())
