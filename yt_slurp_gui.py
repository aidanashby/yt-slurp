"""yt-slurp window: paste a link, click Slurp, watch results appear.

Started by yt-slurp.bat (or "yt-slurp gui"). The pipeline lives in yt_slurp.py;
this module gives it a UI object and runs it on a worker thread so the window
stays responsive.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import wave
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

try:  # plays WAV files on Windows; the Play button is hidden elsewhere
    import winsound
except ImportError:
    winsound = None

import yt_slurp as ys
import yt_slurp_setup as setup

APP_NAME = "yt-slurp"
REPO_DIR = Path(__file__).resolve().parent
RES_DIR = setup.resource_dir()  # icon files; inside the .exe when bundled


def default_output() -> Path:
    """Next to the code when run from source; in Documents for the .exe,
    which may live anywhere (even Downloads)."""
    if setup.frozen():
        return Path.home() / "Documents" / "yt-slurp"
    return REPO_DIR / "output"

AUTO_MERGE_EVERY_MS = 5000
POLL_MS = 100
REDRAW_DELAY_MS = 250
EDIT_UNDO_STEPS = 10
UPDATE_CHECK_DELAY_MS = 3000
SEARCH_DELAY_MS = 150
MAX_HIGHLIGHTS = 2000

# Colours, after the Whisper Transcriber app.
BG = "#ececec"
CARD = "#ffffff"
BORDER = "#d4d4d4"
TEXT = "#2b2b2b"
# Every text and button colour pair meets WCAG AA (4.5:1) on its background.
MUTED = "#5f5f5f"
GREEN, GREEN_DARK = "#2e7d32", "#1b5e20"
SLATE, SLATE_DARK = "#5b6f7a", "#4a5c66"
BLUE, BLUE_DARK = "#1565c0", "#0d47a1"
RED, RED_DARK = "#c62828", "#b71c1c"
FOCUS = "#111111"
MENU_BG, MENU_HOVER = "#f7f7f7", "#e3e3e3"
DISABLED = "#b9c3c8"
BORDER_FINE = "#c4c4c4"
SHADOW, SHADOW_SOFT = "#d9d9d9", "#e4e4e4"
MATCH_BG, CURRENT_BG = "#fff59d", "#ffb74d"
FONT = "Segoe UI"

# Output kinds: label, colour, symbol. Each kind has a symbol as well as a
# colour, so nothing depends on colour alone. Chips are in alphabetical order.
KINDS = {
    "link": ("Links", "#546e7a", "\u2197"),
    "skipped": ("Skipped", "#8a5300", "\u2298"),
    "transcript": ("Transcripts", "#2e7d32", "\u25a0"),
    "wav": ("WAVs", "#1565c0", "\u266a"),
}


KIND_ORDER = ["link", "transcript", "wav", "skipped"]  # chips and list grouping


def sort_key(item: dict) -> tuple:
    """Group the list by kind (in chip order), then by name."""
    return (KIND_ORDER.index(item["kind"]), display_name(item).lower())


def row_text(item: dict) -> str:
    return f"{KINDS[item['kind']][2]}  {display_name(item)}"

LANGUAGES = [
    ("en", "English"), ("es", "Spanish"), ("fr", "French"), ("de", "German"), ("it", "Italian"),
    ("pt", "Portuguese"), ("nl", "Dutch"), ("pl", "Polish"), ("ar", "Arabic"), ("he", "Hebrew"),
    ("el", "Greek"), ("ru", "Russian"), ("uk", "Ukrainian"), ("hi", "Hindi"), ("zh", "Chinese"),
    ("ja", "Japanese"), ("ko", "Korean"),
]
PACE_LABELS = [("normal", "Normal (2 to 5 seconds between requests)"),
               ("slow", "Slow (5 to 10 seconds)"),
               ("very-slow", "Very slow (10 to 20 seconds)")]
TYPE_LABELS = {"videos": "Normal videos", "shorts": "Shorts", "streams": "Live streams"}


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
    "make_transcripts": True,
    "make_wavs": True,
    "make_links": True,
    "test_run": False,
    "limit": 5,
    "include_non_english": False,
    "chunk_minutes": 60,
    "pace": "normal",
    "output": str(default_output()),
    "whisper_path": "",
    "whisper_title": "",
    "max_sources": ys.DEFAULT_MAX_SOURCES,
    "max_source_words": ys.DEFAULT_MAX_SOURCE_WORDS,
    "welcomed": False,
    "check_updates": True,
}


def load_settings() -> dict:
    """Saved settings, checked key by key: anything missing, unknown or of the
    wrong type falls back to the default, so a damaged file can't stop the app."""
    data = dict(DEFAULT_SETTINGS)
    try:
        saved = json.loads((settings_dir() / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data
    if not isinstance(saved, dict):
        return data
    for key, default in DEFAULT_SETTINGS.items():
        val = saved.get(key, default)
        if isinstance(default, bool):
            ok = isinstance(val, bool)
        elif isinstance(default, (int, float)):
            ok = isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 0
        elif isinstance(default, list):
            ok = isinstance(val, list) and all(v in ys.TYPES for v in val)
        else:
            ok = isinstance(val, str)
        if ok:
            data[key] = val
    if data["pace"] not in ys.PACES:
        data["pace"] = DEFAULT_SETTINGS["pace"]
    return data


def save_settings(data: dict) -> None:
    folder = settings_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "settings.json.tmp"
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, folder / "settings.json")


def build_argv(settings: dict, url: str = "", list_file: str = "", only_type: str | None = None) -> list[str]:
    """Turn the window's settings into yt-slurp command-line arguments.
    only_type comes from the Slurp button's menu (just one kind of video)."""
    argv = ["--file", list_file] if list_file else [url]
    argv += ["--output", settings["output"],
             "--min-minutes", str(settings["min_minutes"]),
             "--lang", settings["lang"],
             "--chunk-minutes", str(settings["chunk_minutes"]),
             "--pace", settings["pace"],
             ]
    if only_type:
        argv += ["--types", only_type]
    elif not settings["ask_types"] and settings["types"]:
        argv += ["--types", ",".join(settings["types"])]
    for key, flag in (("make_transcripts", "--no-transcripts"), ("make_wavs", "--no-wavs"),
                      ("make_links", "--no-links")):
        if not settings[key]:
            argv.append(flag)
    if settings["timestamps"]:
        argv.append("--timestamps")
    if settings["test_run"]:
        argv += ["--limit", str(settings["limit"])]
    if settings["include_non_english"]:
        argv.append("--include-non-english")
    return argv


# =============================================================================
# Output items
# =============================================================================

def display_name(item: dict) -> str:
    """The exact YouTube title first; anything else goes at the end."""
    title = item.get("title") or (item["path"].stem if item.get("path") else "")
    if item["kind"] == "wav" and item.get("path"):
        part = ys.part_of(item["path"].name)
        if part:
            return f"{title}, part {part[0]:02d} of {part[1]:02d}"
    if item["kind"] == "skipped" and item.get("text"):
        return f"{title} ({item['text']})"
    return title


def item_key(item: dict) -> tuple:
    if item["kind"] in ("transcript", "wav"):
        return (item["kind"], str(item.get("path")))
    return (item["kind"], item.get("title"), item.get("text") if item["kind"] == "link" else "")


def folder_items(folder: Path) -> list[dict]:
    """Everything an earlier run left in a folder, as output items."""
    man = folder / "manifest.csv"
    manifest = ys.Manifest(man) if man.exists() else None
    run = ys.load_run(folder)

    def vid_of(path: Path) -> str:
        m = ys._ID_RE.search(path.name)
        return m.group(1) if m else ""

    def title_for(path: Path) -> str:
        row = manifest.get(vid_of(path)) if manifest else None
        return row["title"] if row else path.stem

    items = []
    tdir = folder / ys.DIR_TRANSCRIPTS
    for p in (tdir.glob(f"*{ys.TRANSCRIPT_EXT}") if tdir.is_dir() else []):
        items.append({"kind": "transcript", "path": p, "title": title_for(p), "text": "", "vid": vid_of(p)})
    ndir = folder / ys.DIR_NEEDS
    for p in (ndir.rglob("*.wav") if ndir.is_dir() else []):
        items.append({"kind": "wav", "path": p, "title": title_for(p), "text": "", "vid": vid_of(p)})
    if manifest:
        links_on = (folder / "links.txt").exists()
        for r in manifest.rows.values():
            reason = ys.skip_reason(r["status"], run.get("min_minutes", ys.DEFAULT_MIN_MINUTES), r["error"])
            if reason:
                items.append({"kind": "skipped", "path": None, "title": r["title"], "text": reason, "vid": r["id"]})
            elif (links_on and r["status"] not in ("skipped-short", "skipped-private", "deleted")
                  and r["link_removed"] != "1"):
                items.append({"kind": "link", "path": folder / "links.txt", "title": r["title"],
                              "text": ys.watch_url(r["id"]), "vid": r["id"]})
    items.sort(key=sort_key)
    return items


def line_starts(text: str) -> list[int]:
    """Offsets where each line begins, for turning offsets into Tk indices."""
    starts = [0]
    i = text.find("\n")
    while i >= 0:
        starts.append(i + 1)
        i = text.find("\n", i + 1)
    return starts


def text_index(starts: list[int], offset: int) -> str:
    """A character offset as a Tk 'line.column' index, without Tk counting from the start."""
    import bisect
    line = bisect.bisect_right(starts, offset) - 1
    return f"{line + 1}.{offset - starts[line]}"


def find_matches(text: str, needle: str) -> list[int]:
    """Character offsets of every case-insensitive match."""
    if not needle:
        return []
    hay, needle = text.lower(), needle.lower()
    out, i = [], hay.find(needle)
    while i >= 0:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


# =============================================================================
# Markdown rendering (pure: turns Markdown into text runs with style tags)
# =============================================================================

_INLINE_RE = re.compile(
    r"\\(?P<esc>[\\`*_\[\]#>+\-.()!])"
    r"|`(?P<code>[^`]+)`"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|__(?P<bold2>.+?)__"
    r"|(?<![\w*])\*(?P<ital>[^*\s][^*]*?)\*(?!\*)"
    r"|(?<![\w_])_(?P<ital2>[^_\s][^_]*?)_(?![\w_])"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)\s]+)\)"
    r"|<(?P<auto>https?://[^>\s]+)>"
)


def md_inline(text: str, base: tuple = ()) -> list[tuple[str, tuple]]:
    """Inline Markdown (bold, italic, code, links, escapes) to (text, tags) runs."""
    runs, pos = [], 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            runs.append((text[pos:m.start()], base))
        g = m.groupdict()
        if g["esc"] is not None:
            runs.append((g["esc"], base))
        elif g["code"] is not None:
            runs.append((g["code"], base + ("code",)))
        elif g["bold"] is not None or g["bold2"] is not None:
            runs += md_inline(g["bold"] if g["bold"] is not None else g["bold2"], base + ("bold",))
        elif g["ital"] is not None or g["ital2"] is not None:
            runs += md_inline(g["ital"] if g["ital"] is not None else g["ital2"], base + ("italic",))
        elif g["ltext"] is not None:
            runs.append((g["ltext"], base + ("link",)))
        else:
            runs.append((g["auto"], base + ("link",)))
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], base))
    return runs


def md_segments(text: str) -> list[tuple[str, tuple]]:
    """A Markdown document (headings, lists, quotes, rules, paragraphs) as
    (text, tags) runs for a Tk Text widget."""
    out: list[tuple[str, tuple]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            out += md_inline(m.group(2), (f"h{len(m.group(1))}",))
        elif re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            out.append(("\u2500" * 30, ("hr",)))
        elif re.match(r"^[-*+]\s+", stripped):
            out.append(("\u2022  ", ("bullet",)))
            out += md_inline(re.sub(r"^[-*+]\s+", "", stripped), ("bullet",))
        elif stripped.startswith(">"):
            out += md_inline(stripped.lstrip("> "), ("quote",))
        else:
            out += md_inline(line)
        out.append(("\n", ()))
    if out and out[-1] == ("\n", ()):
        out.pop()
    return out


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
        os.startfile(str(path))  # opens with the usual program
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
    return (f"{path.name}\n\nLength: {ys.fmt_duration(secs)}\nFormat: {rate} Hz, "
            f"{'mono' if ch == 1 else f'{ch} channels'}, 16-bit\nSize: {size_mb:.1f} MB\n\n"
            f"Drag it into your transcription app, then save the text into {ys.DIR_WHISPER}. "
            "yt-slurp merges it by itself.")


# =============================================================================
# Drawn widgets
# =============================================================================

def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def add_keyboard(widget, action):
    """Make a drawn widget work from the keyboard: Tab to reach it, a focus ring,
    and Enter or Space to press it."""
    def focus(on):
        widget.focused = on
        widget.redraw()
    widget.bind("<FocusIn>", lambda e: focus(True))
    widget.bind("<FocusOut>", lambda e: focus(False))
    for key in ("<Return>", "<space>", "<KP_Enter>"):
        widget.bind(key, lambda e: (action(), "break")[1])


class FlowBar(tk.Frame):
    """A row of controls that wraps onto more lines when the window is narrow."""

    def __init__(self, parent):
        super().__init__(parent, bg=CARD)
        self.shown: list = []
        self.bind("<Configure>", lambda e: self.layout())

    def show(self, widgets):
        for w in self.winfo_children():
            w.place_forget()
        self.shown = list(widgets)
        self.layout()

    def layout(self):
        width = max(self.winfo_width(), 1)
        x = y = row_h = 0
        gap = 6
        for w in self.shown:
            ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
            if isinstance(w, SearchBox):
                ww = max(150, min(260, width // 3))
            if x and x + ww > width:
                x, y, row_h = 0, y + row_h + gap, 0
            w.place(x=x, y=y, width=ww)
            x += ww + gap
            row_h = max(row_h, wh)
        self.configure(height=max(y + row_h, 1))


class RoundButton(tk.Canvas):
    """A soft-cornered flat button, like the Whisper app's."""

    def __init__(self, parent, text, command, colour=SLATE, hover=SLATE_DARK, fg="white",
                 width=None, height=34, font=(FONT, 10), bg=BG, pad=28):
        self.font, self.pad, self.fixed_width = font, pad, width is not None
        tmp = tk.Label(parent, text=text, font=font)
        w = width or tmp.winfo_reqwidth() + pad
        tmp.destroy()
        super().__init__(parent, width=w, height=height, bg=bg, highlightthickness=0, cursor="hand2",
                         takefocus=1)
        self.text, self.command = text, command
        self.colour, self.hover_colour, self.fg = colour, hover, fg
        self.enabled = True
        self.focused = False
        self.w, self.h = w, height
        self.draw(colour)
        self.bind("<Enter>", lambda e: self.enabled and self.draw(self.hover_colour))
        self.bind("<Leave>", lambda e: self.draw(self.colour if self.enabled else DISABLED))
        self.bind("<Button-1>", self.click)
        add_keyboard(self, self.click)

    def redraw(self):
        self.draw(self.colour if self.enabled else DISABLED)

    def draw(self, fill):
        self.delete("all")
        rounded_rect(self, 1, 1, self.w - 1, self.h - 1, 9, fill=fill, outline=fill)
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=self.fg, font=self.font)
        if self.focused:
            rounded_rect(self, 3, 3, self.w - 3, self.h - 3, 7, fill="", outline="white", width=2)

    def click(self, _=None):
        if self.enabled and self.command:
            self.command()

    def set_text(self, text):
        self.text = text
        if not self.fixed_width:  # grow to fit longer text, never shrink, so buttons don't jump
            need = tkfont.Font(font=self.font).measure(text) + self.pad
            if need > self.w:
                self.w = need
                self.configure(width=need)
        self.draw(self.colour if self.enabled else DISABLED)

    def set_enabled(self, on: bool):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow", takefocus=1 if on else 0)
        self.draw(self.colour if on else DISABLED)


class SplitButton(tk.Canvas):
    """Slurp: the main area runs with the types in settings; the arrow opens a menu."""

    def __init__(self, parent, text, command, menu_command, width=150, height=38):
        super().__init__(parent, width=width, height=height, bg=CARD, highlightthickness=0, cursor="hand2",
                         takefocus=1)
        self.text, self.command, self.menu_command = text, command, menu_command
        self.w, self.h, self.arrow_w = width, height, 34
        self.enabled = True
        self.focused = False
        self.hover = None
        self.draw()
        self.bind("<Motion>", self.motion)
        self.bind("<Leave>", lambda e: self.set_hover(None))
        self.bind("<Button-1>", self.click)
        add_keyboard(self, lambda: self.enabled and self.command())
        self.bind("<Down>", lambda e: self.open_menu())
        self.bind("<Alt-Down>", lambda e: self.open_menu())

    def redraw(self):
        self.draw()

    def open_menu(self):
        if self.enabled:
            self.menu_command(self.winfo_rootx() + self.w - self.arrow_w, self.winfo_rooty() + self.h)

    def zone(self, x):
        return "arrow" if x > self.w - self.arrow_w else "main"

    def motion(self, e):
        self.set_hover(self.zone(e.x))

    def set_hover(self, z):
        if z != self.hover:
            self.hover = z
            self.draw()

    def draw(self):
        self.delete("all")
        base = GREEN if self.enabled else DISABLED
        rounded_rect(self, 1, 1, self.w - 1, self.h - 1, 10, fill=base, outline=base)
        if self.enabled and self.hover:
            x1, x2 = (1, self.w - self.arrow_w) if self.hover == "main" else (self.w - self.arrow_w, self.w - 1)
            self.create_rectangle(x1 + (8 if self.hover == "main" else 0), 2,
                                  x2 - (8 if self.hover == "arrow" else 0), self.h - 2,
                                  fill=GREEN_DARK, outline=GREEN_DARK)
            if self.hover == "main":
                rounded_rect(self, 1, 1, 30, self.h - 1, 10, fill=GREEN_DARK, outline=GREEN_DARK)
            else:
                rounded_rect(self, self.w - 30, 1, self.w - 1, self.h - 1, 10, fill=GREEN_DARK, outline=GREEN_DARK)
        self.create_line(self.w - self.arrow_w, 8, self.w - self.arrow_w, self.h - 8, fill="#ffffff", width=1)
        self.create_text((self.w - self.arrow_w) / 2, self.h / 2, text=self.text, fill="white",
                         font=(FONT, 11, "bold"))
        cx, cy = self.w - self.arrow_w / 2, self.h / 2
        self.create_polygon(cx - 5, cy - 2, cx + 5, cy - 2, cx, cy + 4, fill="white", outline="white")
        if self.focused:
            rounded_rect(self, 3, 3, self.w - 3, self.h - 3, 8, fill="", outline="white", width=2)

    def click(self, e):
        if not self.enabled:
            return
        if self.zone(e.x) == "arrow":
            self.open_menu()
        else:
            self.command()

    def set_enabled(self, on: bool):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow", takefocus=1 if on else 0)
        self.draw()


class Chip(tk.Canvas):
    """A filter chip: coloured dot, label and count. Click to toggle."""

    def __init__(self, parent, kind, on_toggle):
        self.kind = kind
        self.label, self.colour, self.symbol = KINDS[kind]
        self.on = True
        self.count = 0
        self.on_toggle = on_toggle
        super().__init__(parent, height=28, width=10, bg=CARD, highlightthickness=0, cursor="hand2", takefocus=1)
        self.focused = False
        self.bind("<Button-1>", self.toggle)
        add_keyboard(self, self.toggle)
        self.draw()

    def redraw(self):
        self.draw()

    def draw(self):
        self.delete("all")
        text = f"{self.symbol}  {self.label}  {self.count}"
        tmp = tk.Label(self, text=text, font=(FONT, 9))
        w = tmp.winfo_reqwidth() + 22
        tmp.destroy()
        self.configure(width=w)
        fill = self.colour if self.on else CARD
        outline = self.colour if self.on else BORDER
        rounded_rect(self, 1, 2, w - 1, 26, 12, fill=fill, outline=outline)
        self.create_text(11, 14, text=text, anchor="w", fill="white" if self.on else MUTED, font=(FONT, 9))
        if self.focused:
            rounded_rect(self, 1, 2, w - 1, 26, 12, fill="", outline=FOCUS, width=2)

    def toggle(self, _=None):
        self.on = not self.on
        self.draw()
        self.on_toggle()

    def set_count(self, n):
        if n != self.count:
            self.count = n
            self.draw()


class SearchBox(tk.Frame):
    """A flat entry with a placeholder and an optional × to clear it."""

    def __init__(self, parent, placeholder, on_change, clear_button=True, width=30):
        super().__init__(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=BLUE)
        self.placeholder, self.on_change = placeholder, on_change
        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, relief="flat", bd=4, bg=CARD, fg=TEXT,
                              font=(FONT, 10), width=width, insertbackground=TEXT)
        self.entry.pack(side="left", fill="x", expand=True)
        self.hint = tk.Label(self, text=placeholder, bg=CARD, fg=MUTED, font=(FONT, 10))
        self.hint.place(x=6, rely=0.5, anchor="w")
        self.hint.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.clear = None
        if clear_button:
            self.clear = tk.Label(self, text="×", bg=CARD, fg=MUTED, font=(FONT, 12), cursor="hand2")
            self.clear.bind("<Button-1>", lambda e: self.var.set(""))
        self.var.trace_add("write", lambda *a: self.changed())
        self.entry.bind("<Escape>", lambda e: self.var.set(""))

    def changed(self):
        has = bool(self.var.get())
        if has:
            self.hint.place_forget()
        else:
            self.hint.place(x=6, rely=0.5, anchor="w")
        if self.clear is not None:
            if has:
                self.clear.pack(side="right", padx=(0, 6))
            else:
                self.clear.pack_forget()
        self.on_change()

    def get(self):
        return self.var.get()


def card(parent, **kw) -> tk.Frame:
    return tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER, **kw)


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

    def item(self, kind, folder, path=None, text="", title="", vid="") -> None:
        self._post("item", kind, Path(folder), Path(path) if path else None, text, title, vid)

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
        self.keys: set = set()
        self.shown: list[int] = []
        self.current_folder: Path | None = None
        self.list_file = ""
        self.log_lines: list[str] = []
        self.log_window = None
        self.setup_window = None
        self.stage = "Ready."
        self.counts_text = ""
        self.matches: list[int] = []
        self.multi: list[dict] = []
        self.multi_texts: dict = {}
        self.multi_saved: dict = {}
        self.view_item = None
        self.playing = False
        self.closed = False
        self.update_info = None
        self.match_i = -1
        ys.set_ui(GuiUI(self))

        root.title("yt-slurp")
        root.geometry("1220x800")
        root.minsize(940, 600)
        root.configure(bg=BG)
        self.set_icon()
        self.style()
        self.build_menu()
        self.build_top()
        self.build_bottom()
        self.build_middle()
        # Tab order follows stacking order: put the bottom row after the panes.
        self.btn_row.lift()
        self.status_row.lift()
        self.refresh_sources()
        self.update_status()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(POLL_MS, self.poll)
        root.after(AUTO_MERGE_EVERY_MS, self.auto_merge)
        if not self.settings["welcomed"]:
            root.after(300, self.welcome)
        root.after(200, self.check_tools)
        if self.settings.get("check_updates", True):
            root.after(UPDATE_CHECK_DELAY_MS, lambda: self.check_updates(quiet=True))

    # ----- look -----

    def set_icon(self):
        self.icon_img = None
        try:
            self.icon_img = tk.PhotoImage(file=str(RES_DIR / "icon.png"))
            self.root.iconphoto(True, self.icon_img)
            if os.name == "nt":
                self.root.iconbitmap(default=str(RES_DIR / "icon.ico"))
        except tk.TclError:
            pass

    def style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        s.configure("Out.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                    rowheight=26, borderwidth=0, font=(FONT, 10))
        s.layout("Out.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.map("Out.Treeview", background=[("selected", "#e3f2fd")], foreground=[("selected", TEXT)])
        s.layout("Slim.Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        s.configure("Slim.Vertical.TScrollbar", troughcolor=CARD, background="#949494", bordercolor=CARD,
                    lightcolor="#949494", darkcolor="#949494", arrowsize=7, width=7, gripcount=0)
        s.map("Slim.Vertical.TScrollbar", background=[("active", "#6f6f6f")])
        s.configure("TCombobox", fieldbackground=CARD, background=CARD, arrowcolor=SLATE, bordercolor=BORDER,
                    lightcolor=CARD, darkcolor=CARD, padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", CARD)], selectbackground=[("readonly", CARD)],
              selectforeground=[("readonly", TEXT)])
        for w in ("TCheckbutton", "TRadiobutton"):
            s.configure(w, background=CARD, foreground=TEXT, font=(FONT, 10), indicatorbackground=CARD,
                        indicatorforeground=GREEN_DARK, upperbordercolor=BORDER, lowerbordercolor=BORDER)
            s.map(w, background=[("active", CARD)], indicatorbackground=[("disabled", "#f0f0f0")],
                  foreground=[("disabled", MUTED)])
        s.configure("TSpinbox", fieldbackground=CARD, background=CARD, arrowcolor=SLATE, bordercolor=BORDER,
                    lightcolor=CARD, darkcolor=CARD)
        s.configure("TEntry", fieldbackground=CARD, bordercolor=BORDER, lightcolor=CARD, darkcolor=CARD)
        s.configure("Horizontal.TProgressbar", troughcolor="#dcdcdc", background=GREEN, bordercolor=BG,
                    lightcolor=GREEN, darkcolor=GREEN, thickness=6)

    # ----- layout -----

    def build_menu(self):
        """A drawn menu bar, so it can hold the blue Update button (Windows'
        own menu bar cannot be coloured)."""
        bar = self.menu_bar = tk.Frame(self.root, bg=MENU_BG)
        bar.pack(fill="x")
        tools = tk.Menu(self.root, tearoff=False)
        tools.add_command(label="Make Gemini Notebook files", command=self.make_gemini)
        tools.add_command(label="Open the manifest in Excel", command=self.open_manifest)
        tools.add_command(label="Show the full log", command=self.show_log)
        if not setup.frozen():
            tools.add_separator()
            tools.add_command(label="Run the self-test", command=self.self_test)
        helpm = tk.Menu(self.root, tearoff=False)
        helpm.add_command(label="How to use yt-slurp", command=self.welcome)
        helpm.add_command(label="Check for updates", command=lambda: self.check_updates(quiet=False))
        helpm.add_command(label=f"About yt-slurp {ys.__version__}", command=self.about)
        self.menu_item(bar, "Settings", self.open_settings)
        self.menu_item(bar, "Tools", lambda w: tools.tk_popup(w.winfo_rootx(), w.winfo_rooty() + w.winfo_height()),
                       popup=True)
        self.menu_item(bar, "Help", lambda w: helpm.tk_popup(w.winfo_rootx(), w.winfo_rooty() + w.winfo_height()),
                       popup=True)
        self.update_btn = RoundButton(bar, "Update", self.do_update, colour=BLUE, hover=BLUE_DARK, height=24,
                                      font=(FONT, 9, "bold"), bg=MENU_BG)
        tk.Frame(bar, bg=BORDER, height=1).place(relx=0, rely=1, relwidth=1, anchor="sw")

    def menu_item(self, bar, text, command, popup=False):
        lab = tk.Label(bar, text=text, bg=MENU_BG, fg=TEXT, font=(FONT, 10), padx=10, pady=4, cursor="hand2",
                       takefocus=1, highlightthickness=1, highlightbackground=MENU_BG, highlightcolor=FOCUS)
        lab.pack(side="left")
        run = (lambda e=None: command(lab)) if popup else (lambda e=None: command())
        lab.bind("<Button-1>", run)
        for key in ("<Return>", "<space>", "<Down>"):
            lab.bind(key, run)
        lab.bind("<Enter>", lambda e: lab.configure(bg=MENU_HOVER))
        lab.bind("<Leave>", lambda e: lab.configure(bg=MENU_BG))
        return lab

    def build_top(self):
        top = card(self.root)
        top.pack(fill="x", padx=12, pady=(10, 6))
        inner = tk.Frame(top, bg=CARD)
        inner.pack(fill="x", padx=12, pady=10)
        self.url_box = SearchBox(inner, "Paste a YouTube channel or playlist link", lambda: None,
                                 clear_button=True, width=60)
        self.url_box.entry.configure(font=(FONT, 11))
        self.url_box.pack(side="left", fill="x", expand=True, ipady=3)
        self.url_var = self.url_box.var
        self.url_box.entry.bind("<Return>", lambda e: self.slurp())
        self.slurp_btn = SplitButton(inner, "Slurp", self.slurp, self.slurp_menu)
        self.slurp_btn.pack(side="left", padx=(10, 0))
        self.pause_btn = RoundButton(inner, "Pause", self.toggle_pause, colour=SLATE, hover=SLATE_DARK,
                                     width=92, height=38, bg=CARD)
        self.pause_btn.pack(side="left", padx=(8, 0))
        self.stop_btn = RoundButton(inner, "Stop", self.stop, colour=RED, hover=RED_DARK, width=80, height=38,
                                    bg=CARD)
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.pause_btn.set_enabled(False)
        self.stop_btn.set_enabled(False)

        row = tk.Frame(top, bg=CARD)
        row.pack(fill="x", padx=12, pady=(0, 10))
        link = tk.Label(row, text="Use a list of links from a file", bg=CARD, fg=BLUE, font=(FONT, 9, "underline"),
                        cursor="hand2", takefocus=1, highlightthickness=1, highlightbackground=CARD,
                        highlightcolor=FOCUS)
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: self.pick_list())
        for key in ("<Return>", "<space>"):
            link.bind(key, lambda e: self.pick_list())
        self.list_label = tk.Label(row, text="", bg=CARD, fg=MUTED, font=(FONT, 9))
        self.list_label.pack(side="left", padx=8)
        self.source_var = tk.StringVar()
        self.source_box = ttk.Combobox(row, textvariable=self.source_var, state="readonly", width=40)
        self.source_box.pack(side="right")
        self.source_box.bind("<<ComboboxSelected>>", self.pick_source)
        tk.Label(row, text="Done before:", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="right", padx=6)

        self.type_menu = tk.Menu(self.root, tearoff=False)
        for key in ys.TYPES:
            self.type_menu.add_command(label=f"Just {TYPE_LABELS[key].lower()}" if key != "shorts" else "Just Shorts",
                                       command=lambda k=key: self.slurp(only_type=k))

    def build_middle(self):
        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill="both", expand=True, padx=12, pady=0)
        panes = tk.PanedWindow(mid, orient="horizontal", bg=BG, sashwidth=10, bd=0, sashrelief="flat")
        panes.pack(fill="both", expand=True)

        left = card(panes)
        chips = tk.Frame(left, bg=CARD)
        chips.pack(fill="x", padx=10, pady=(10, 6))
        self.chips = {}
        for kind in KIND_ORDER:
            chip = Chip(chips, kind, self.redraw)
            chip.pack(side="left", padx=(0, 6))
            self.chips[kind] = chip
        self.name_filter = SearchBox(left, "Filter by name", self.redraw)
        self.name_filter.pack(fill="x", padx=10, pady=(0, 6))
        listf = tk.Frame(left, bg=CARD)
        listf.pack(fill="both", expand=True, padx=(10, 4), pady=(0, 10))
        self.tree = ttk.Treeview(listf, show="tree", selectmode="extended", style="Out.Treeview")
        for kind, (_, colour, _) in KINDS.items():
            self.tree.tag_configure(kind, foreground=colour)
        sb = ttk.Scrollbar(listf, orient="vertical", command=self.tree.yview, style="Slim.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.preview)
        self.tree.bind("<Double-1>", self.open_selected)
        panes.add(left, minsize=320, width=520)

        right = self.right_pane = card(panes)
        srow = tk.Frame(right, bg=CARD)
        srow.pack(fill="x", padx=10, pady=(10, 4))
        self.text_search = SearchBox(srow, "Find in this file", self.schedule_search, clear_button=True)
        self.text_search.pack(side="left", fill="x", expand=True)
        self.text_search.entry.bind("<Return>", lambda e: self.step_match(1))
        self.line_starts = [0]
        self.text_search.entry.bind("<Shift-Return>", lambda e: self.step_match(-1))
        for sym, step in (("\u2039", -1), ("\u203a", 1)):
            b = tk.Label(srow, text=sym, bg=CARD, fg=SLATE, font=(FONT, 16), cursor="hand2", padx=6)
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, s=step: self.step_match(s))
        self.match_label = tk.Label(srow, text="", bg=CARD, fg=MUTED, font=(FONT, 9), width=10)
        self.match_label.pack(side="left")

        # Editing tools. Which ones show depends on what is selected; they wrap
        # onto more lines in a narrow window.
        self.edit_bar = FlowBar(right)
        self.edit_bar.pack(fill="x", padx=10, pady=(0, 6))
        small = dict(height=26, bg=CARD, font=(FONT, 9), pad=16)
        self.replace_box = SearchBox(self.edit_bar, "Replace with", lambda: None, clear_button=True, width=16)
        self.replace_btn = RoundButton(self.edit_bar, "Replace", self.replace_one, **small)
        self.replace_all_btn = RoundButton(self.edit_bar, "Replace all", self.replace_all, **small)
        self.undo_btn = RoundButton(self.edit_bar, "\u21b6", self.undo, **small)
        self.redo_btn = RoundButton(self.edit_bar, "\u21b7", self.redo, **small)
        self.save_btn = RoundButton(self.edit_bar, "Saved", self.save_file, colour=GREEN, hover=GREEN_DARK,
                                    width=62, height=26, bg=CARD, font=(FONT, 9, "bold"))
        self.play_btn = RoundButton(self.edit_bar, "\u25b6 Play", self.play_wav, colour=BLUE, hover=BLUE_DARK, **small)
        self.stop_play_btn = RoundButton(self.edit_bar, "\u25a0 Stop", self.stop_wav, **small)
        self.delete_btn = RoundButton(self.edit_bar, "Delete", self.delete_selected, colour=RED, hover=RED_DARK,
                                      **small)

        stack = tk.Frame(right, bg=CARD)
        stack.pack(fill="both", expand=True, padx=(10, 4), pady=(0, 10))
        stack.rowconfigure(0, weight=1)
        stack.columnconfigure(0, weight=1)
        self.view_frame, self.preview_text = self.text_area(stack, state="disabled")
        self.edit_frame, self.editor = self.text_area(stack, undo=True, maxundo=EDIT_UNDO_STEPS, autoseparators=True,
                                                      insertbackground=TEXT)
        self.editor.configure(font=("Consolas", 10))
        self.view_frame.tkraise()
        self.editing = False
        self.edit_item = None
        self.saved_text = ""
        self.preview_text.bind("<Button-1>", self.start_editing)
        self.preview_text.bind("<FocusIn>", lambda e: self.start_editing() if self.edit_item else None)
        self.editor.bind("<<Modified>>", self.edit_changed)
        self.editor.bind("<KeyRelease>", lambda e: self.update_edit_buttons())
        for seq in ("<Control-s>", "<Control-S>"):
            self.root.bind_all(seq, lambda e: (self.save_file(), "break")[1])
        self.root.bind_all("<FocusIn>", self.focus_moved, add="+")
        self.empty_hint = tk.Label(right, text="Select a file from the list to see it here.", bg=CARD, fg=MUTED,
                                   font=(FONT, 10))
        self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")
        self.update_edit_buttons()
        panes.add(right, minsize=320)

    def text_area(self, parent, **kw):
        frame = tk.Frame(parent, bg=CARD)
        frame.grid(row=0, column=0, sticky="nsew")
        text = tk.Text(frame, wrap="word", width=20, font=(FONT, 10), padx=10, pady=8, relief="flat", bg=CARD,
                       fg=TEXT, highlightthickness=0, selectbackground="#bbdefb", **kw)
        text.tag_configure("match", background=MATCH_BG)
        text.tag_configure("current", background=CURRENT_BG)
        for tag, opts in (("h1", {"font": (FONT, 15, "bold"), "spacing3": 6}),
                          ("h2", {"font": (FONT, 13, "bold"), "spacing3": 4}),
                          ("h3", {"font": (FONT, 11, "bold")}),
                          ("bold", {"font": (FONT, 10, "bold")}),
                          ("italic", {"font": (FONT, 10, "italic")}),
                          ("code", {"font": ("Consolas", 10), "background": "#f1f1f1"}),
                          ("link", {"foreground": BLUE, "underline": True}),
                          ("bullet", {"lmargin1": 8, "lmargin2": 24}),
                          ("quote", {"lmargin1": 16, "lmargin2": 16, "foreground": MUTED}),
                          ("hr", {"foreground": BORDER})):
            text.tag_configure(tag, **opts)
        text.tag_raise("match")
        text.tag_raise("current")
        sb = ttk.Scrollbar(frame, orient="vertical", command=text.yview, style="Slim.Vertical.TScrollbar")
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")  # pack the bar first, or the wide text squeezes it out
        text.pack(side="left", fill="both", expand=True)
        return frame, text

    def build_bottom(self):
        status = self.status_row = tk.Frame(self.root, bg=BG)
        status.pack(side="bottom", fill="x", padx=14, pady=(0, 8))
        self.status_label = tk.Label(status, text="", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w", cursor="hand2")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.status_label.bind("<Button-1>", lambda e: self.show_log())
        self.bar = ttk.Progressbar(status, mode="determinate", length=220)
        self.bar.pack(side="right")

        btns = self.btn_row = tk.Frame(self.root, bg=BG)
        btns.pack(side="bottom", fill="x", padx=12, pady=(8, 6))
        for text, cmd, colour, hover in (
                ("Open results folder", self.open_results, SLATE, SLATE_DARK),
                ("Open WAV folder", self.open_wavs, SLATE, SLATE_DARK),
                ("Launch transcription app", self.launch_whisper, BLUE, BLUE_DARK),
                ("Make Gemini Notebook files", self.make_gemini, SLATE, SLATE_DARK)):
            RoundButton(btns, text, cmd, colour=colour, hover=hover).pack(side="left", padx=(0, 8))

    # ----- status bar and log -----

    def update_status(self):
        parts = [self.stage]
        if self.counts_text:
            parts.append(self.counts_text)
        self.status_label.configure(text="   ·   ".join(parts) + "      Show log ›")

    def write_log(self, msg):
        self.log_lines.append(msg)
        if self.log_window is not None:
            self.log_window.append(msg)

    def show_log(self):
        if self.log_window is not None:
            self.log_window.top.lift()
            return
        self.log_window = LogWindow(self)

    # ----- sources -----

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

    def pick_list(self):
        f = filedialog.askopenfilename(title="Choose a text file with one link per line",
                                       filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f:
            self.list_file = f
            self.url_var.set("")
            self.list_label.configure(text=f"Using links from {Path(f).name} (paste a link to use that instead)")

    # ----- output list -----

    def show_folder(self, folder: Path):
        self.current_folder = folder
        self.items, self.keys = [], set()
        for it in folder_items(folder):
            self.keys.add(item_key(it))
            self.items.append(it)
        self.redraw()
        man = folder / "manifest.csv"
        if man.exists():
            self.show_counts(ys.Manifest(man).counts())

    def clear_items(self):
        # Clear the on-screen rows first, so no selection points at a result
        # that no longer exists.
        self.tree.selection_remove(*self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        self.items, self.keys, self.current_folder = [], set(), None
        self.redraw()

    def visible(self, it) -> bool:
        if not self.chips[it["kind"]].on:
            return False
        needle = self.name_filter.get().strip().lower()
        return not needle or needle in display_name(it).lower()

    def redraw(self):
        """Rebuild the list, grouped by kind, keeping the selection and scroll position."""
        self._redraw_job = None
        chosen = {id(it) for it in self.selected_items()}
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        order = sorted(range(len(self.items)), key=lambda i: sort_key(self.items[i]))
        keep = []
        for i in order:
            it = self.items[i]
            if self.visible(it):
                self.tree.insert("", "end", iid=str(i), text=row_text(it), tags=(it["kind"],))
                if id(it) in chosen:
                    keep.append(str(i))
        self.update_chip_counts()
        if keep:
            self.tree.selection_set(keep)
        self.tree.yview_moveto(top)

    def schedule_redraw(self):
        if not getattr(self, "_redraw_job", None):
            self._redraw_job = self.root.after(REDRAW_DELAY_MS, self.redraw)

    def update_chip_counts(self):
        for kind, chip in self.chips.items():
            chip.set_count(sum(1 for it in self.items if it["kind"] == kind))

    def add_item(self, kind, folder, path, text, title, vid=""):
        if self.current_folder is None:
            self.show_folder(folder)
        elif self.current_folder != folder:
            return  # results for another folder (an automatic merge); not on screen
        if not vid and path is not None:
            m = ys._ID_RE.search(Path(path).name)
            vid = m.group(1) if m else ""
        it = {"kind": kind, "path": path, "text": text, "title": title, "vid": vid}
        key = item_key(it)
        if key in self.keys:
            return
        self.keys.add(key)
        self.items.append(it)
        self.update_chip_counts()
        if self.visible(it):
            # Results are grouped by kind, so a new one may belong anywhere.
            # Redraw in a moment, keeping the scroll position and selection.
            self.schedule_redraw()

    def selected_items(self) -> list[dict]:
        out = []
        for iid in self.tree.selection():
            try:
                out.append(self.items[int(iid)])
            except (ValueError, IndexError):
                pass  # a row left over from before the list changed
        return out

    def selected(self):
        """The one selected result, or None if none or several are selected."""
        items = self.selected_items()
        return items[0] if len(items) == 1 else None

    # ----- content pane -----

    def preview(self, _=None):
        items = self.selected_items()
        if len(items) > 1:
            if self.multi and [id(i) for i in items] == [id(i) for i in self.multi]:
                return
            if not self.confirm_leave_edits():
                return
            self.stop_wav()
            self.show_multi(items)
            return
        it = items[0] if items else None
        if not it or (it is self.edit_item and not self.multi):
            return
        if not self.confirm_leave_edits():
            return
        self.stop_wav()
        self.multi = []
        self.edit_item = None
        self.view_item = it
        if it["kind"] == "transcript":
            try:
                text = ys.read_text(it["path"])
                self.edit_item = it
            except OSError:
                text = "(this file is no longer there)"
            self.load_editor(text if self.edit_item else "")
            self.set_preview(text, markdown=True)
            self.show_tools()
            return
        if it["kind"] == "wav":
            text = wav_info(it["path"]) if it["path"] and it["path"].exists() else "(this file is no longer there)"
        elif it["kind"] == "link":
            text = f"{it['title']}\n\n{it['text']}\n\nDouble-click to open it in your browser."
        else:
            text = f"{it['title']}\n\nSkipped: {it['text']}."
        self.load_editor("")
        self.set_preview(text)
        self.show_tools()

    def show_multi(self, items):
        """Several results selected: list them, and find and replace across the
        transcripts among them."""
        self.edit_item = None
        self.view_item = None
        self.multi = items
        editable = [it for it in items if it["kind"] == "transcript"]
        others = [it for it in items if it["kind"] != "transcript"]
        self.multi_saved, self.multi_texts = {}, {}
        for it in editable:
            try:
                self.multi_saved[it["path"]] = self.multi_texts[it["path"]] = ys.read_text(it["path"])
            except OSError:
                pass
        lines = [f"# {len(items)} results selected", ""]
        if editable:
            lines += [f"## Can be edited ({len(editable)})", ""]
            lines += [f"- {ys.md_escape_inline(display_name(it))}" for it in editable] + [""]
        if others:
            lines += [f"## Can't be edited ({len(others)})", ""]
            lines += [f"- {ys.md_escape_inline(display_name(it))} ({KINDS[it['kind']][0].lower().rstrip('s')})"
                      for it in others] + [""]
        if editable:
            lines.append("Find and replace below changes every selected transcript. Select Save to keep the changes.")
        self.load_editor("")
        self.set_preview("\n".join(lines), markdown=True)
        self.show_tools()

    def show_tools(self):
        """Show only the tools that apply to what is selected."""
        tools = []
        if self.multi:
            if any(it["kind"] == "transcript" for it in self.multi):
                tools = [self.replace_box, self.replace_all_btn, self.save_btn]
            tools.append(self.delete_btn)
        elif self.edit_item:
            tools = [self.replace_box, self.replace_btn, self.replace_all_btn, self.undo_btn, self.redo_btn,
                     self.save_btn, self.delete_btn]
        elif self.view_item:
            if self.view_item["kind"] == "wav" and winsound is not None:
                tools = [self.play_btn, self.stop_play_btn]
            tools.append(self.delete_btn)
        self.edit_bar.show(tools)
        self.update_edit_buttons()

    def set_preview(self, text, markdown=False):
        self.empty_hint.place_forget() if text else self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")
        self.show_view(text, markdown)

    def show_view(self, text, markdown=True):
        """The rich-text view: Markdown rendered, read-only."""
        t = self.preview_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        if markdown:
            for run, tags in md_segments(text):
                t.insert("end", run, tags)
        else:
            t.insert("1.0", text)
        t.configure(state="disabled")
        self.view_frame.tkraise()
        self.editing = False
        self.run_search()

    # ----- editing -----

    def load_editor(self, text):
        e = self.editor
        e.delete("1.0", "end")
        e.insert("1.0", text)
        e.edit_reset()
        e.edit_modified(False)
        self.saved_text = text
        self.update_edit_buttons()

    def start_editing(self, _=None):
        """Show the Markdown source for editing when the file pane is clicked."""
        if not self.edit_item:
            return None
        if not self.editing:
            self.editing = True
            self.edit_frame.tkraise()
            self.run_search()
        self.editor.focus_set()
        return "break"

    def focus_moved(self, event):
        """Show the rich-text view again once focus leaves the file pane."""
        w = event.widget
        if not self.editing or not isinstance(w, tk.Misc):
            return
        try:
            inside = str(w).startswith(str(self.right_pane))
        except Exception:
            inside = False
        if not inside:
            self.show_view(self.editor_text(), markdown=True)

    def editor_text(self) -> str:
        return self.editor.get("1.0", "end-1c")

    def dirty(self) -> bool:
        if self.multi:
            return any(self.multi_texts[p] != self.multi_saved[p] for p in self.multi_texts)
        return bool(self.edit_item) and self.editor_text() != self.saved_text

    def edit_changed(self, _=None):
        self.editor.edit_modified(False)
        self.update_edit_buttons()

    def update_edit_buttons(self):
        editable = bool(self.edit_item) or bool(self.multi_texts if self.multi else None)
        for b in (self.replace_btn, self.replace_all_btn):
            b.set_enabled(editable)
        self.stop_play_btn.set_enabled(self.playing)
        self.undo_btn.set_enabled(editable and self.can("canundo"))
        self.redo_btn.set_enabled(editable and self.can("canredo"))
        if self.dirty():
            self.save_btn.set_text("Save")
            self.save_btn.set_enabled(True)
        else:
            self.save_btn.set_text("Saved")
            self.save_btn.set_enabled(False)

    def can(self, what) -> bool:
        try:
            return bool(self.editor.tk.call(self.editor._w, "edit", what))
        except tk.TclError:
            return True  # older Tk can't say; let the button try

    def undo(self):
        self.start_editing()
        try:
            self.editor.edit_undo()
        except tk.TclError:
            pass
        self.after_edit()

    def redo(self):
        self.start_editing()
        try:
            self.editor.edit_redo()
        except tk.TclError:
            pass
        self.after_edit()

    def after_edit(self):
        self.update_edit_buttons()
        if self.text_search.get():
            self.run_search()

    def replace_one(self):
        needle, repl = self.text_search.get(), self.replace_box.get()
        if not self.edit_item or not needle:
            return
        self.start_editing()
        self.run_search()
        if not self.matches:
            return
        off = self.matches[self.match_i]
        with self.one_undo_step():
            self.editor.delete(self.index_of(off), self.index_of(off + len(needle)))
            self.editor.insert(self.index_of(off), repl)
        keep = self.match_i
        self.run_search()
        if self.matches:
            self.match_i = min(keep, len(self.matches) - 1)
            self.show_match()
        self.update_edit_buttons()

    def replace_all(self):
        needle, repl = self.text_search.get(), self.replace_box.get()
        if self.multi and needle:
            total, files = 0, 0
            for p, text in self.multi_texts.items():
                n = len(find_matches(text, needle))
                if n:
                    self.multi_texts[p] = re.sub(re.escape(needle), lambda m: repl, text, flags=re.IGNORECASE)
                    total, files = total + n, files + 1
            self.run_search()
            self.update_edit_buttons()
            self.stage = (f"Replaced {total} {'match' if total == 1 else 'matches'} in {files} "
                          f"{'file' if files == 1 else 'files'}. Select Save to keep the changes.")
            self.update_status()
            return
        if not self.edit_item or not needle:
            return
        self.start_editing()
        text = self.editor_text()
        count = len(find_matches(text, needle))
        if not count:
            return
        new = re.sub(re.escape(needle), lambda m: repl, text, flags=re.IGNORECASE)
        with self.one_undo_step():
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", new)
        self.run_search()
        self.update_edit_buttons()
        self.stage = f"Replaced {count} {'match' if count == 1 else 'matches'}."
        self.update_status()

    def one_undo_step(self):
        """Group a delete-and-insert so a single Undo reverses it."""
        import contextlib
        e = self.editor

        @contextlib.contextmanager
        def group():
            e.configure(autoseparators=False)
            e.edit_separator()
            try:
                yield
            finally:
                e.edit_separator()
                e.configure(autoseparators=True)
        return group()

    def save_file(self):
        if not self.dirty():
            return
        if self.multi:
            saved = 0
            for p, text in self.multi_texts.items():
                if text != self.multi_saved[p]:
                    try:
                        ys.write_atomic(p, text)
                    except OSError as e:
                        messagebox.showerror(APP_NAME, f"Could not save {p.name}: {e.strerror}")
                        continue
                    self.multi_saved[p] = text
                    saved += 1
            self.update_edit_buttons()
            self.stage = f"Saved {saved} {'file' if saved == 1 else 'files'}."
            self.update_status()
            return
        text = self.editor_text()
        try:
            ys.write_atomic(self.edit_item["path"], text)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not save {self.edit_item['path'].name}: {e.strerror}")
            return
        self.saved_text = text
        self.update_edit_buttons()
        self.stage = f"Saved {self.edit_item['path'].name}."
        self.update_status()

    def confirm_leave_edits(self) -> bool:
        """Before leaving a file with unsaved changes: save, discard, or stay."""
        if not self.dirty():
            return True
        what = (f"the {len([p for p in self.multi_texts if self.multi_texts[p] != self.multi_saved[p]])} "
                "changed transcripts" if self.multi else self.edit_item["title"])
        ans = messagebox.askyesnocancel(APP_NAME, f"Save your changes to {what}?")
        if ans is None:
            back = self.multi or [self.edit_item]
            iids = [str(i) for i, it in enumerate(self.items) if any(it is b for b in back)]
            iids = [i for i in iids if self.tree.exists(i)]
            if iids:
                self.tree.selection_set(iids)
            return False
        if ans:
            self.save_file()
        return True

    def delete_selected(self):
        items = self.selected_items()
        if not items or not self.current_folder:
            return
        counts = {}
        for it in items:
            counts[KINDS[it["kind"]][0].lower()] = counts.get(KINDS[it["kind"]][0].lower(), 0) + 1
        what = ", ".join(f"{n} {k if n != 1 else k.rstrip('s')}" for k, n in counts.items())
        if not messagebox.askyesno(
                APP_NAME, f"Delete {what}?\n\nFiles are deleted from the results folder, links are removed "
                          "from links.txt, and skipped videos are removed from the list. Slurping this channel "
                          "again won't bring them back.", icon="warning", default="no"):
            return
        self.stop_wav()
        if self.multi:
            self.multi_texts = {p: t for p, t in self.multi_saved.items()}  # drop unsaved changes
        targets = [(it["kind"], it.get("vid", ""), it["path"] if it["kind"] in ("transcript", "wav") else None)
                   for it in items]
        try:
            ys.remove_results(self.current_folder, targets)
        except ys.Stop as e:
            messagebox.showinfo(APP_NAME, str(e))
            return
        gone = {id(it) for it in items}
        self.items = [it for it in self.items if id(it) not in gone]
        self.keys = {item_key(it) for it in self.items}
        self.tree.selection_remove(*self.tree.selection())
        self.multi, self.edit_item, self.view_item = [], None, None
        self.load_editor("")
        self.redraw()
        self.set_preview("")
        self.show_tools()
        man = self.current_folder / "manifest.csv"
        if man.exists():
            self.show_counts(ys.Manifest(man).counts())
        self.stage = f"Deleted {what}."
        self.update_status()

    def play_wav(self):
        it = self.view_item
        if winsound is None or not it or it["kind"] != "wav" or not it["path"].exists():
            return
        winsound.PlaySound(str(it["path"]), winsound.SND_FILENAME | winsound.SND_ASYNC)
        self.playing = True
        self.update_edit_buttons()

    def stop_wav(self):
        if self.playing and winsound is not None:
            winsound.PlaySound(None, 0)
        self.playing = False
        self.update_edit_buttons()

    def active_text(self):
        return self.editor if self.editing else self.preview_text

    def schedule_search(self):
        """Search shortly after typing stops, not on every keystroke."""
        if getattr(self, "_search_job", None):
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(SEARCH_DELAY_MS, self.run_search)

    def run_search(self):
        self._search_job = None
        if self.multi:  # count matches across the selected transcripts
            needle = self.text_search.get()
            self.matches, self.match_i = [], -1
            if not needle:
                self.match_label.configure(text="")
            else:
                counts = [len(find_matches(t, needle)) for t in self.multi_texts.values()]
                total, files = sum(counts), sum(1 for c in counts if c)
                self.match_label.configure(text=f"{total} in {files} file{'' if files == 1 else 's'}"
                                           if total else "No matches")
            return
        t = self.active_text()
        t.tag_remove("match", "1.0", "end")
        t.tag_remove("current", "1.0", "end")
        needle = self.text_search.get()
        text = t.get("1.0", "end-1c")
        self.matches = find_matches(text, needle)
        self.line_starts = line_starts(text)
        # Highlight in batches, and only the first MAX_HIGHLIGHTS; the arrows
        # still step through every match.
        ranges = []
        for off in self.matches[:MAX_HIGHLIGHTS]:
            ranges += [self.index_of(off), self.index_of(off + len(needle))]
        for i in range(0, len(ranges), 400):
            t.tag_add("match", *ranges[i:i + 400])
        self.match_i = 0 if self.matches else -1
        self.show_match()

    def index_of(self, offset: int) -> str:
        return text_index(self.line_starts, offset)

    def step_match(self, step):
        if self.matches:
            self.match_i = (self.match_i + step) % len(self.matches)
            self.show_match()
        return "break"

    def show_match(self):
        t = self.active_text()
        t.tag_remove("current", "1.0", "end")
        needle = self.text_search.get()
        if not needle:
            self.match_label.configure(text="")
            return
        if not self.matches:
            self.match_label.configure(text="No matches")
            return
        off = self.matches[self.match_i]
        start = self.index_of(off)
        t.tag_add("current", start, self.index_of(off + len(needle)))
        t.see(start)
        self.match_label.configure(text=f"{self.match_i + 1} of {len(self.matches)}")

    def open_selected(self, _=None):
        it = self.selected()
        if not it:
            return
        if it["kind"] == "transcript":
            open_path(it["path"])
        elif it["kind"] == "wav":
            open_path(it["path"].parent)
        elif it["kind"] == "link":
            import webbrowser
            webbrowser.open(it["text"])

    def show_counts(self, counts):
        names = (("transcript", "transcripts"), ("merged", "merged"), ("wav", "waiting for transcription"),
                 ("pending", "to do"), ("no-captions", "no captions"), ("needs-signin", "need sign-in"),
                 ("failed", "failed"))
        parts = [f"{label} {counts[k]}" for k, label in names if counts.get(k)]
        skipped = sum(v for k, v in counts.items() if k.startswith("skipped"))
        if skipped:
            parts.append(f"skipped {skipped}")
        self.counts_text = ", ".join(parts)
        self.update_status()

    # ----- running -----

    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start(self, argv, label, after=None):
        if self.busy():
            messagebox.showinfo(APP_NAME, "yt-slurp is already working. Wait for it to finish, or click Stop.")
            return
        ys.PAUSE.clear()
        self.slurp_btn.set_enabled(False)
        self.pause_btn.set_text("Pause")
        self.pause_btn.set_enabled(True)
        self.stop_btn.set_enabled(True)
        self.stage = label
        self.update_status()
        # No moving bar until there is real progress to show: an animated bar
        # while a question waits for an answer looks like it's doing something.
        self.bar.configure(mode="determinate", value=0)

        def work():
            code = ys.run_command(argv)
            self.events.put(("done", code, after))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def slurp_menu(self, x, y):
        self.type_menu.tk_popup(x, y)

    def slurp(self, only_type: str | None = None):
        url = self.url_var.get().strip()
        if url:
            self.list_file = ""
            self.list_label.configure(text="")
        if not url and not self.list_file:
            messagebox.showinfo(APP_NAME, "Paste a YouTube channel or playlist link first.")
            self.url_box.entry.focus_set()
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
        if not any(self.settings[k] for k in ("make_transcripts", "make_wavs", "make_links")):
            messagebox.showinfo(APP_NAME, "Settings has Transcripts, WAV files and Links all turned off, "
                                          "so there is nothing to make.")
            return
        self.clear_items()
        self.write_log("")
        self.start(build_argv(self.settings, url, self.list_file, only_type), "Starting...")

    def toggle_pause(self):
        if ys.PAUSE.is_set():
            ys.PAUSE.clear()
            self.pause_btn.set_text("Pause")
            self.stage = "Carrying on..."
        else:
            ys.PAUSE.set()
            self.pause_btn.set_text("Resume")
            self.stage = "Paused. Click Resume to carry on."
        self.update_status()

    def stop(self):
        ys.STOP.set()
        self.stop_btn.set_enabled(False)
        self.pause_btn.set_enabled(False)
        self.stage = "Stopping after the current step..."
        self.update_status()

    def finished(self, code, after):
        ys.PAUSE.clear()
        self.bar.configure(mode="determinate", value=0)
        self.slurp_btn.set_enabled(True)
        self.pause_btn.set_text("Pause")
        self.pause_btn.set_enabled(False)
        self.stop_btn.set_enabled(False)
        self.stage = {0: "Finished.", 130: "Stopped. Slurp the same link again to carry on."}.get(
            code, "Stopped with a problem. Click here to see the log.")
        self.update_status()
        self.refresh_sources()
        if after:
            after(code)

    # ----- events from the worker -----

    def poll(self):
        try:
            while not self.closed:
                self.handle(self.events.get_nowait())
        except queue.Empty:
            pass
        if self.closed:
            return
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
            if not ys.PAUSE.is_set():
                self.bar.configure(mode="determinate", maximum=max(total, 1), value=done)
                self.stage = f"{stage}: {done} of {total}"
                self.update_status()
        elif kind == "counts":
            _, folder, counts = msg
            if self.current_folder is None and self.busy():
                self.show_folder(folder)  # show what an earlier run already made
            if self.current_folder == folder:
                self.show_counts(counts)
        elif kind == "item":
            _, ikind, folder, path, text, title, vid = msg
            self.add_item(ikind, folder, path, text, title, vid)
        elif kind == "ask":
            _, akind, data, reply = msg
            before = self.stage
            self.stage = "Waiting for your answer..."
            self.update_status()
            try:
                reply["value"] = self.answer(akind, data)
            finally:
                reply["event"].set()
                self.stage = before
                self.update_status()
        elif kind == "done":
            self.finished(msg[1], msg[2])
        elif kind == "setup":
            _, label, done, total = msg
            self.bar.configure(mode="determinate", maximum=max(total, 1), value=done)
            self.stage = f"{label}: {setup.download_text(done, total)}"
            self.update_status()
            if self.setup_window:
                self.setup_window.show_bytes(label, done, total)
        elif kind == "setup_step":
            self.stage = msg[1]
            self.update_status()
            if self.setup_window:
                self.setup_window.show_step(msg[1])
        elif kind == "setup_done":
            if self.setup_window:
                self.setup_window.close()
                self.setup_window = None
            self.bar.configure(value=0)
            self.slurp_btn.set_enabled(True)
            self.update_btn.set_enabled(True)
            if msg[1]:
                self.stage = "Setup did not finish."
                messagebox.showerror(APP_NAME, f"{msg[1]}\n\nCheck your internet connection and restart "
                                               "yt-slurp to try again.")
            else:
                self.stage = "Ready."
            self.update_status()
        elif kind == "updated":
            setup.restart(msg[1])
            self.on_close()
        elif kind == "update":
            self.show_update(msg[1], msg[2])

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
                        self.write_log(f"\nTranscripts found for {folder.name}. Merging...")
                        self.start(["merge", str(folder)], "Merging transcripts...")
                        break
        except Exception as e:  # never let a background check kill the window
            self.write_log(f"(Automatic merge check failed: {e})")
        self.root.after(AUTO_MERGE_EVERY_MS, self.auto_merge)

    def gemini_args(self):
        s = self.settings
        return ["--max-sources", str(s["max_sources"]),
                "--max-source-words", str(s["max_source_words"])]

    def make_gemini(self):
        """A second step after a slurp: bundle the transcripts for Gemini Notebook."""
        folder = self.current_folder or self.ask_folder()
        if not folder:
            return
        if not (folder / ys.DIR_TRANSCRIPTS).is_dir() or not any((folder / ys.DIR_TRANSCRIPTS).glob(f"*{ys.TRANSCRIPT_EXT}")):
            messagebox.showinfo(APP_NAME, "There are no transcripts in this folder yet. Slurp a channel or "
                                          "playlist first.")
            return

        def after(code):
            if code == 0:
                open_path(folder / ys.DIR_GEMINI)

        self.start(["gemini", str(folder)] + self.gemini_args(), "Making Gemini Notebook files...", after)

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

    def open_wavs(self):
        folder = self.folder_or_ask()
        if not folder:
            return
        target = folder / ys.DIR_NEEDS
        if not target.is_dir() or not any(target.glob("*.wav")):
            messagebox.showinfo(APP_NAME, "No WAV files are waiting for transcription in this folder.")
            return
        open_path(target)

    def launch_whisper(self):
        s = self.settings
        # Find an open copy by a word in its window title (default: the
        # program's filename), so a second copy isn't started.
        title = s["whisper_title"] or (Path(s["whisper_path"]).stem if s["whisper_path"] else "")
        hwnd = find_window(title)
        if hwnd:
            bring_to_front(hwnd)
            return
        if not s["whisper_path"] or not Path(s["whisper_path"]).exists():
            messagebox.showinfo(APP_NAME, "Show yt-slurp where your transcription app is: Settings, then Transcription app.")
            self.open_settings()
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

    def open_settings(self):
        SettingsDialog(self)

    # ----- first-run setup and updates -----

    def check_tools(self):
        setup.use_tools()
        missing = setup.missing_tools()
        if not missing:
            return
        names = {"ffmpeg": "ffmpeg (makes audio files for videos without captions)",
                 "deno": "Deno (yt-dlp needs it to read YouTube)"}
        if os.name != "nt":
            messagebox.showwarning(APP_NAME, "yt-slurp needs " + " and ".join(names[m] for m in missing)
                                   + ". Install them with your package manager, then restart yt-slurp.")
            return
        if not messagebox.askyesno(
                "Finish setting up yt-slurp",
                "yt-slurp needs two free tools that aren't on this computer yet:\n\n"
                + "\n".join(f"\u2022 {names[m]}" for m in missing)
                + "\n\nDownload them now? This happens once and needs no admin rights. They go in "
                  "yt-slurp's own folder. On a slow connection it can take 15 minutes or more."):
            self.stage = "ffmpeg or Deno is missing. Restart yt-slurp to install them."
            self.update_status()
            return
        self.slurp_btn.set_enabled(False)
        self.setup_window = SetupWindow(self.root, "Setting up yt-slurp")

        def work():
            try:
                for i, name in enumerate(missing, 1):
                    label = f"Downloading {setup.TOOL_NAMES[name]} ({i} of {len(missing)})"
                    self.events.put(("setup_step", label))

                    def prog(done, total, label=label):
                        self.events.put(("setup", label, done, total))
                    setup.install_tool(name, prog, lambda text: self.events.put(("setup_step", text)))
                setup.use_tools()
                self.events.put(("setup_done", None))
            except Exception as e:  # network or disk problem: say so, don't crash
                self.events.put(("setup_done", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def check_updates(self, quiet=True):
        def work():
            self.events.put(("update", setup.check_for_update(ys.__version__), quiet))
        threading.Thread(target=work, daemon=True).start()

    def show_update(self, info, quiet):
        self.update_info = info
        if info:
            self.update_btn.set_text(f"Update to {info['version']}")
            self.update_btn.pack(side="right", padx=8, pady=3)
        elif not quiet:
            messagebox.showinfo(APP_NAME, f"You have the latest version, {ys.__version__}.")

    def do_update(self):
        info = getattr(self, "update_info", None)
        if not info:
            return
        if self.busy():
            messagebox.showinfo(APP_NAME, "Wait for the current job to finish, then update.")
            return
        if not setup.frozen() or not info.get("url"):
            import webbrowser
            messagebox.showinfo(APP_NAME, f"Version {info['version']} is available. Your browser will open the "
                                          "download page." if setup.frozen() else
                                f"Version {info['version']} is available. You're running yt-slurp from its "
                                "source code, so update it with git pull in its folder.")
            if setup.frozen():
                webbrowser.open(info["page"])
            return
        if not messagebox.askyesno(APP_NAME, f"Update yt-slurp to version {info['version']}? It downloads the "
                                             "new version, then restarts. Your settings and results are kept."):
            return
        self.update_btn.set_enabled(False)
        self.setup_window = SetupWindow(self.root, f"Updating yt-slurp to {info['version']}")

        def work():
            try:
                def prog(done, total):
                    self.events.put(("setup", "Downloading the update", done, total))
                exe = setup.apply_update(info["url"], prog)
                self.events.put(("updated", exe))
            except Exception as e:
                self.events.put(("setup_done", f"The update could not be installed: {e}"))

        threading.Thread(target=work, daemon=True).start()

    def about(self):
        messagebox.showinfo(APP_NAME, f"yt-slurp {ys.__version__}\n\nCollects YouTube transcripts for AI "
                                      f"assistants such as Claude, ChatGPT and Gemini Notebook.\n\nhttps://github.com/{setup.REPO}")

    # ----- tools -----

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
            messagebox.showwarning(APP_NAME, f"Self-test failed: {last}\n\nThe details are in the log.")

    def welcome(self):
        messagebox.showinfo(
            "How to use yt-slurp",
            "1. Paste a YouTube channel or playlist link at the top and click Slurp. The arrow on the right of "
            "Slurp lets you do just normal videos, just Shorts or just live streams.\n\n"
            "2. Questions pop up when yt-slurp needs an answer.\n\n"
            "3. Results appear on the left as they are made: transcripts, WAV files, links and skipped "
            "videos, each in its own colour. Click the chips to hide or show each kind. Click a result to "
            "read it on the right.\n\n"
            "4. Videos without captions become WAV files. Click Open WAV folder and Launch transcription app, "
            "drag the WAVs in, and save each transcript into the whisper-transcripts folder. yt-slurp "
            "merges them by itself.\n\n"
            "5. Add the transcripts to Claude or ChatGPT as they are. For Gemini Notebook, which limits how many "
            "sources a notebook can hold, click Make Gemini Notebook files to bundle them.\n\n"
            "Settings is in the menu bar.")
        self.settings["welcomed"] = True
        save_settings(self.settings)

    def on_close(self):
        if not self.closed and not self.confirm_leave_edits():
            return
        if self.busy():
            if not messagebox.askyesno(APP_NAME, "yt-slurp is still working. Stop it and close? "
                                                 "Progress so far is saved."):
                return
            ys.STOP.set()
            ys.PAUSE.clear()
            self.worker.join(timeout=10)
        save_settings(self.settings)
        self.instance.release()
        self.closed = True
        self.root.destroy()


# =============================================================================
# Dialogs
# =============================================================================

def modal(parent, title) -> tuple[tk.Toplevel, tk.Frame]:
    top = tk.Toplevel(parent)
    top.title(title)
    top.configure(bg=SHADOW)
    top.transient(parent)
    top.resizable(False, False)
    # A fine border with a soft shadow below and to the right, drawn as two
    # graded edges; Windows adds its own drop shadow around the whole window.
    edge = tk.Frame(top, bg=SHADOW_SOFT)
    edge.pack(fill="both", expand=True, padx=(0, 0), pady=(0, 0))
    border = tk.Frame(edge, bg=CARD, highlightthickness=1, highlightbackground=BORDER_FINE)
    border.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))
    frame = tk.Frame(border, bg=CARD)
    frame.pack(fill="both", expand=True, padx=22, pady=18)
    top.after_idle(lambda: centre_over(top, parent))
    return top, frame


def centre_over(top, parent):
    """Open a pop-up in the middle of the main window."""
    try:
        top.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - top.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - top.winfo_reqheight()) // 3
        top.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    except tk.TclError:
        pass


def heading(parent, text):
    tk.Label(parent, text=text, bg=CARD, fg=TEXT, font=(FONT, 11, "bold")).pack(anchor="w", pady=(12, 4))


class SettingsDialog:
    """All settings in one place. Save keeps them; Cancel throws the changes away."""

    def __init__(self, app: App):
        self.app = app
        s = app.settings
        top, frame = modal(app.root, "yt-slurp settings")
        self.top = top
        cols = tk.Frame(frame, bg=CARD)
        cols.pack(fill="both")
        left = tk.Frame(cols, bg=CARD)
        left.pack(side="left", fill="y", anchor="n", padx=(0, 30))
        right = tk.Frame(cols, bg=CARD)
        right.pack(side="left", fill="y", anchor="n")
        self.vars: dict[str, tk.Variable] = {}

        def check(parent, key, text, command=None, indent=0):
            v = tk.BooleanVar(value=s[key])
            self.vars[key] = v
            w = ttk.Checkbutton(parent, text=text, variable=v, command=command)
            w.pack(anchor="w", padx=(indent, 0), pady=1)
            return w

        def number(parent, key, before, after, lo, hi, width=6):
            row = tk.Frame(parent, bg=CARD)
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=before, bg=CARD, fg=TEXT, font=(FONT, 10)).pack(side="left")
            v = tk.StringVar(value=str(s[key]))
            self.vars[key] = v
            ttk.Spinbox(row, from_=lo, to=hi, width=width, textvariable=v).pack(side="left", padx=5)
            if after:
                tk.Label(row, text=after, bg=CARD, fg=TEXT, font=(FONT, 10)).pack(side="left")

        heading(left, "Which videos")
        check(left, "ask_types", "Ask me each time", command=self.toggle_types)
        self.type_vars, self.type_checks = {}, []
        for key in ys.TYPES:
            v = tk.BooleanVar(value=key in s["types"])
            self.type_vars[key] = v
            cb = ttk.Checkbutton(left, text=TYPE_LABELS[key], variable=v)
            cb.pack(anchor="w", padx=(22, 0), pady=1)
            self.type_checks.append(cb)
        number(left, "min_minutes", "Skip videos shorter than", "minutes", 0, 600)
        check(left, "test_run", "Test run: only do the first few videos")
        number(left, "limit", "How many in a test run:", "", 1, 1000)

        heading(left, "What to make")
        check(left, "make_transcripts", "Transcripts (from captions)")
        check(left, "make_wavs", "WAV files (for videos without captions)")
        check(left, "make_links", "Links (links.txt)")

        heading(left, "Transcripts")
        row = tk.Frame(left, bg=CARD)
        row.pack(anchor="w", pady=2)
        tk.Label(row, text="Caption language:", bg=CARD, fg=TEXT, font=(FONT, 10)).pack(side="left")
        self.lang_var = tk.StringVar(value=dict(LANGUAGES).get(s["lang"], s["lang"]))
        ttk.Combobox(row, textvariable=self.lang_var, width=14, values=[n for _, n in LANGUAGES]).pack(
            side="left", padx=5)
        check(left, "timestamps", "Add the time at the start of each paragraph")

        heading(left, "Videos without captions")
        check(left, "include_non_english", "Make WAVs for videos not in English")
        number(left, "chunk_minutes", "Split long audio into parts of", "minutes", 0, 600)

        heading(right, "Pace")
        self.pace_var = tk.StringVar(value=s["pace"])
        for key, label in PACE_LABELS:
            ttk.Radiobutton(right, text=label, value=key, variable=self.pace_var).pack(anchor="w", pady=1)

        heading(right, "Where things go")
        self.output_var = tk.StringVar(value=s["output"])
        tk.Label(right, textvariable=self.output_var, bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=330,
                 justify="left").pack(anchor="w")
        RoundButton(right, "Change results folder...", self.pick_output, height=30, bg=CARD).pack(anchor="w", pady=4)

        heading(right, "Transcription app")
        self.whisper_var = tk.StringVar(value=s["whisper_path"] or "Not set yet")
        tk.Label(right, textvariable=self.whisper_var, bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=330,
                 justify="left").pack(anchor="w")
        RoundButton(right, "Choose the transcription app...", self.pick_whisper, height=30, bg=CARD).pack(anchor="w", pady=4)
        row = tk.Frame(right, bg=CARD)
        row.pack(anchor="w", pady=2)
        tk.Label(row, text="Word in its window title:", bg=CARD, fg=TEXT, font=(FONT, 10)).pack(side="left")
        v = tk.StringVar(value=s["whisper_title"])
        self.vars["whisper_title"] = v
        ttk.Entry(row, textvariable=v, width=14).pack(side="left", padx=5)

        heading(right, "Gemini Notebook files")
        number(right, "max_sources", "Gemini Notebook sources:", "", 1, 1000, width=9)
        number(right, "max_source_words", "Words per Gemini source:", "", 1000, 500_000, width=9)

        btns = tk.Frame(frame, bg=CARD)
        btns.pack(fill="x", pady=(18, 0))
        RoundButton(btns, "Save", self.save, colour=GREEN, hover=GREEN_DARK, width=100, bg=CARD).pack(side="right")
        RoundButton(btns, "Cancel", top.destroy, width=100, bg=CARD).pack(side="right", padx=8)
        self.toggle_types()
        top.grab_set()
        top.lift()

    def toggle_types(self):
        state = ["disabled"] if self.vars["ask_types"].get() else ["!disabled"]
        for cb in self.type_checks:
            cb.state(state)

    def pick_output(self):
        d = filedialog.askdirectory(parent=self.top, title="Where should yt-slurp save results?",
                                    initialdir=self.output_var.get())
        if d:
            self.output_var.set(d)

    def pick_whisper(self):
        f = filedialog.askopenfilename(
            parent=self.top, title="Choose your transcription app (its .exe, .bat, .py or shortcut)",
            filetypes=[("Programs and scripts", "*.exe *.bat *.cmd *.py *.pyw *.lnk"), ("All files", "*.*")])
        if f:
            self.whisper_var.set(f)

    def save(self):
        s = self.app.settings
        for key, var in self.vars.items():
            val = var.get()
            if key in ("min_minutes", "chunk_minutes"):
                try:
                    val = float(val)
                    val = int(val) if val == int(val) else val
                except ValueError:
                    val = DEFAULT_SETTINGS[key]
            elif key in ("limit", "max_sources", "max_source_words"):
                try:
                    val = max(1, int(float(val)))
                except ValueError:
                    val = DEFAULT_SETTINGS[key]
            s[key] = val
        s["types"] = [k for k, v in self.type_vars.items() if v.get()] or ["videos"]
        name = self.lang_var.get().strip()
        s["lang"] = next((c for c, n in LANGUAGES if n.lower() == name.lower()), name.lower() or "en")
        s["pace"] = self.pace_var.get()
        if self.output_var.get() != s["output"]:
            s["output"] = self.output_var.get()
        if self.whisper_var.get() != "Not set yet":
            s["whisper_path"] = self.whisper_var.get()
        save_settings(s)
        self.app.refresh_sources()
        self.top.destroy()


class LogWindow:
    """The full message history, opened from the status bar."""

    def __init__(self, app: App):
        self.app = app
        top, frame = modal(app.root, "yt-slurp log")
        top.resizable(True, True)
        top.geometry("820x520")
        self.top = top
        textf = tk.Frame(frame, bg=CARD)
        textf.pack(fill="both", expand=True)
        self.text = tk.Text(textf, wrap="word", font=("Consolas", 9), relief="flat", bg="#f7f7f7", fg=TEXT,
                            padx=8, pady=6, highlightthickness=0)
        sb = ttk.Scrollbar(textf, orient="vertical", command=self.text.yview, style="Slim.Vertical.TScrollbar")
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.insert("end", "\n".join(app.log_lines) + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")
        btns = tk.Frame(frame, bg=CARD)
        btns.pack(fill="x", pady=(10, 0))
        RoundButton(btns, "Close", self.close, width=90, bg=CARD).pack(side="right")
        RoundButton(btns, "Copy all", self.copy, width=90, bg=CARD).pack(side="right", padx=8)
        top.protocol("WM_DELETE_WINDOW", self.close)

    def append(self, msg):
        at_end = self.text.yview()[1] >= 0.999
        self.text.configure(state="normal")
        self.text.insert("end", msg + "\n")
        self.text.configure(state="disabled")
        if at_end:
            self.text.see("end")

    def copy(self):
        self.top.clipboard_clear()
        self.top.clipboard_append("\n".join(self.app.log_lines))

    def close(self):
        self.app.log_window = None
        self.top.destroy()


class SetupWindow:
    """Downloads of the tools or an update, shown in the middle of the window.
    Closing it only hides it: the status bar keeps showing the progress."""

    def __init__(self, parent, title):
        self.top, frame = modal(parent, title)
        tk.Label(frame, text=title, bg=CARD, fg=TEXT, font=(FONT, 11, "bold")).pack(anchor="w")
        self.step = tk.Label(frame, text="", bg=CARD, fg=TEXT, font=(FONT, 10), anchor="w")
        self.step.pack(fill="x", pady=(10, 6))
        self.bar = ttk.Progressbar(frame, length=380)
        self.bar.pack()
        self.detail = tk.Label(frame, text="", bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w")
        self.detail.pack(fill="x", pady=(6, 0))
        self.top.protocol("WM_DELETE_WINDOW", self.top.withdraw)
        self.started = None
        self.show_step("Connecting...")

    def show_step(self, text):
        """A step with no known length: the bar moves to show it's working."""
        self.step.configure(text=text)
        self.detail.configure(text="")
        self.bar.configure(mode="indeterminate")
        self.bar.start(15)
        self.started = None

    def show_bytes(self, text, done, total):
        if self.started is None or self.step.cget("text") != text:
            # Time from the first bytes, so connecting doesn't count against the rate
            self.bar.stop()
            self.step.configure(text=text)
            self.started = time.monotonic()
        self.bar.configure(mode="determinate", maximum=max(total, 1), value=done)
        self.detail.configure(text=setup.download_text(done, total, time.monotonic() - self.started))

    def close(self):
        self.bar.stop()
        self.top.destroy()


class ChoiceDialog:
    """A question with one button per answer. Closing it picks the cautious
    answer: keep what exists, or don't use a browser."""

    def __init__(self, parent, question, options):
        self.result = next((k for k, _ in options if k in ("update", "none")), options[-1][0])
        top, frame = modal(parent, APP_NAME)
        self.top = top
        tk.Label(frame, text=question, wraplength=420, bg=CARD, fg=TEXT, font=(FONT, 10), justify="left").pack(
            anchor="w", pady=(0, 12))
        for i, (key, label) in enumerate(options):
            colour, hover = (GREEN, GREEN_DARK) if i == 0 else (SLATE, SLATE_DARK)
            RoundButton(frame, label, lambda k=key: self.pick(k), colour=colour, hover=hover, width=420,
                        bg=CARD).pack(pady=3)
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
        top, frame = modal(parent, APP_NAME)
        self.top = top
        tk.Label(frame, text="Which kinds of video should yt-slurp include?", bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(anchor="w")
        if len(found) > 1:
            for name, counts in found:
                tk.Label(frame, text=f"{name}: " + ", ".join(f"{n} {t}" for t, n in counts.items()), bg=CARD,
                         fg=MUTED, font=(FONT, 9)).pack(anchor="w")
        self.vars = {}
        for t in ys.TYPES:
            if t in totals:
                v = tk.BooleanVar(value=(t == "videos"))
                self.vars[t] = v
                ttk.Checkbutton(frame, text=f"{TYPE_LABELS[t]} ({totals[t]})", variable=v).pack(anchor="w", pady=3)
        row = tk.Frame(frame, bg=CARD)
        row.pack(fill="x", pady=(14, 0))
        RoundButton(row, "Carry on", self.ok, colour=GREEN, hover=GREEN_DARK, width=110, bg=CARD).pack(side="right")
        RoundButton(row, "All of them", self.all, width=110, bg=CARD).pack(side="right", padx=8)
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
    if os.name == "nt":
        try:  # own taskbar entry and icon, rather than Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("yt-slurp.app")
        except (AttributeError, OSError):
            pass
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
        if messagebox.askyesno(
                APP_NAME,
                f"Something went wrong: {exc}\n\n"
                f"yt-slurp has saved the details to:\n{log}\n\n"
                "If the problem keeps happening, please report it on GitHub "
                "(github.com/aidanashby/yt-slurp/issues) and attach that file.\n\n"
                "Open the folder with the log now?", icon="error"):
            if os.name == "nt":
                os.startfile(str(log.parent))
            else:
                subprocess.Popen(["xdg-open", str(log.parent)])
    except (tk.TclError, OSError):
        pass


if __name__ == "__main__":
    sys.exit(main())
