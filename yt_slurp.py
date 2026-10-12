"""yt-slurp: collect YouTube transcripts for every video in a channel or playlist.

Videos with captions become clean text. Videos without captions become
16 kHz mono WAV files for the Whisper transcriber app, and "yt-slurp merge"
brings the app's saved .txt files back in. See README.md for the routine.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import html
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Constants
# =============================================================================

# The characters around the video ID in every filename. The merge step finds
# videos by these, so if the Whisper app's save dialog mangles brackets, change
# them here and nowhere else.
ID_OPEN = "["
ID_CLOSE = "]"

# Gemini Notebook (formerly NotebookLM). Third-party guides in 2026 give 50
# sources per notebook on the free tier (paid tiers quoted as 100, 300 or 600)
# and 500,000 words or 200 MB per source on every plan. Google's own help page
# was not checked, so these are the values to change if Google changes them.
GEMINI_MAX_SOURCES_FREE = 50
GEMINI_MAX_WORDS_PER_SOURCE = 500_000

DEFAULT_MAX_SOURCES = GEMINI_MAX_SOURCES_FREE
DEFAULT_MAX_SOURCE_WORDS = 400_000  # margin below the limit: Google may count words differently
DEFAULT_CHUNK_WORDS = 100_000       # per claude-parts file
DEFAULT_MIN_MINUTES = 5
DEFAULT_LANG = "en"
DEFAULT_WAV_RATE = 16_000
DEFAULT_CHUNK_MINUTES = 60
DEFAULT_BATCH_FILES = 10
DEFAULT_OUTPUT = "output"

MAX_PATH_LEN = 240          # every file yt-slurp writes stays at or under this
MAX_TITLE_LEN = 100         # title part of a filename
MAX_FOLDER_NAME_LEN = 60    # per-source output folder name
MIN_TITLE_BUDGET = 20       # stop if a deep output path leaves less than this for titles

# Paragraph breaks in caption transcripts (seconds).
PARA_LONG_PAUSE_S = 3.0     # a pause this long ends a paragraph...
PARA_LONG_PAUSE_MIN_S = 15  # ...once the paragraph is at least this long
PARA_SOFT_LEN_S = 60        # after this long, break at the next short pause or sentence end
PARA_SOFT_PAUSE_S = 1.0
PARA_HARD_LEN_S = 90        # always break by this point
WORD_DURATION_EST_S = 0.6   # estimated length of the last word in an auto-caption event

# Audio splitting.
SPLIT_WINDOW_S = 120                      # look this far either side of each boundary
SILENCE_THRESHOLDS_DB = (-50, -40, -35, -30, -25)  # quietest first
SILENCE_MIN_S = 0.3
MIN_PART_S = 60

SHORTS_MAX_S = 180  # YouTube Shorts are at most 3 minutes

# Network politeness and retries.
DELAY_RANGE_S = (2.0, 5.0)
RETRY_DELAYS_S = (10, 20, 40, 80, 160)
BOT_CHECK_LIMIT = 3  # consecutive "confirm you're not a bot" errors before pausing
CAPTION_INFO_MAX_AGE_S = 3 * 3600  # caption URLs in cached metadata expire

TYPES = ("videos", "shorts", "streams")
TYPE_LABEL = {"videos": "video", "shorts": "short", "streams": "stream"}
BROWSERS = ("chrome", "edge", "firefox", "brave")

STATUSES = (
    "pending", "transcript", "wav", "merged", "skipped-short", "skipped-live",
    "skipped-private", "skipped-non-english", "needs-signin", "failed",
)
MANIFEST_FIELDS = (
    "id", "title", "channel", "upload_date", "duration", "type", "status",
    "source", "language", "wav_files", "batch", "error", "updated",
)
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

DIR_TRANSCRIPTS = "transcripts"
DIR_NEEDS = "needs-transcription"
DIR_WHISPER = "whisper-transcripts"
DIR_CLAUDE = "claude-parts"
DIR_GEMINI = "gemini-notebook"
DIR_WORK = ".work"

SEPARATOR = "=" * 72


# =============================================================================
# Pure helpers: names and paths
# =============================================================================

def safe_filename(text: str, max_len: int = MAX_TITLE_LEN) -> str:
    """ASCII-only, punctuation-free text that is safe in a Windows filename."""
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"['`]", "", text)               # "Don't" becomes "Dont"
    text = re.sub(r"[^A-Za-z0-9 _-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    text = truncate_words(text, max_len)
    if not text:
        text = "untitled"
    if text.upper() in WINDOWS_RESERVED:
        text = "_" + text
    return text


def truncate_words(text: str, max_len: int) -> str:
    """Cut text to max_len, at a word boundary when that keeps most of it."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    space = cut.rfind(" ")
    if space >= max_len * 0.6:
        cut = cut[:space]
    return cut.rstrip(" .-_")


def iso_date(yyyymmdd: str | None) -> str:
    """'20240308' to '2024-03-08'; anything else to 'undated'."""
    if yyyymmdd and re.fullmatch(r"\d{8}", yyyymmdd):
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    if yyyymmdd and re.fullmatch(r"\d{4}-\d{2}-\d{2}", yyyymmdd):
        return yyyymmdd
    return "undated"


def video_stem(date: str, title: str, vid: str) -> str:
    return f"{iso_date(date)} {title} {ID_OPEN}{vid}{ID_CLOSE}"


def part_suffix(part: int, parts: int) -> str:
    return f" part {part:02d} of {parts:02d}" if parts > 1 else ""


def title_budget(out_dir: Path, max_path: int = MAX_PATH_LEN) -> int:
    """Characters left for the title in the longest path a video produces.

    The longest is a WAV part in a batch folder:
    <out_dir>/needs-transcription/batch 999/<date> <title> [<id>] part 99 of 99.wav
    The Whisper app's .txt for it lives in whisper-transcripts/, which is shorter.
    """
    fixed = len(str(out_dir)) + len(f"/{DIR_NEEDS}/batch 999/")
    fixed += len(video_stem("2000-01-01", "", "x" * 11)) + len(part_suffix(99, 99)) + len(".wav")
    return min(MAX_TITLE_LEN, max_path - fixed)


def fit_title(title: str, budget: int) -> str:
    """Shorten an already-safe title to the path budget."""
    return truncate_words(title, budget) or "untitled"


def fmt_duration(seconds) -> str:
    if seconds in (None, ""):
        return "?:??"
    s = int(float(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def watch_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def find_by_id(folder: Path, vid: str, suffix: str) -> list[Path]:
    """Files in folder (recursively) whose names carry [vid]. Avoids glob, since
    brackets are glob syntax."""
    if not folder.is_dir():
        return []
    token = f"{ID_OPEN}{vid}{ID_CLOSE}"
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and token in p.name and p.name.lower().endswith(suffix))


# =============================================================================
# Pure helpers: URLs and errors
# =============================================================================

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
VIDEO_PATHS = ("watch", "shorts", "live", "embed", "v")


def classify_url(url: str) -> tuple[str, str, str]:
    """Return (kind, normalised url, note). kind is channel, playlist, video or unknown."""
    url = url.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    query = urllib.parse.parse_qs(parsed.query)
    segs = [s for s in parsed.path.split("/") if s]

    if host in ("youtu.be", "www.youtu.be"):
        if "list" in query:
            return _playlist_from_list(query["list"][0], "video link with a playlist")
        return "video", url, ""
    if host not in YOUTUBE_HOSTS:
        return "unknown", url, "not a YouTube address"
    if not segs:
        return "unknown", url, "no channel or playlist in the address"

    first = segs[0]
    if first == "playlist":
        if "list" in query:
            return _playlist_from_list(query["list"][0], "")
        return "unknown", url, "playlist address has no list= value"
    if first in VIDEO_PATHS:
        if "list" in query:
            return _playlist_from_list(query["list"][0], "video link with a playlist")
        return "video", url, ""
    if first.startswith("@"):
        return "channel", f"https://www.youtube.com/{first}", ""
    if first in ("channel", "c", "user") and len(segs) >= 2:
        return "channel", f"https://www.youtube.com/{first}/{segs[1]}", ""
    if first in ("results", "feed", "hashtag", "post", "account"):
        return "unknown", url, "not a channel or playlist"
    # Legacy custom URL such as youtube.com/SomeName
    return "channel", f"https://www.youtube.com/{first}", ""


def _playlist_from_list(list_id: str, note: str) -> tuple[str, str, str]:
    if list_id.startswith(("RD", "WL", "LL")):
        return "unknown", "", "that list is a YouTube mix or personal list, not a playlist"
    if note:
        note = f"{note}: using the playlist"
    return "playlist", f"https://www.youtube.com/playlist?list={list_id}", note


def classify_error(message: str) -> str:
    """Map a yt-dlp error message to how yt-slurp handles it."""
    m = (message or "").lower()
    if "not a bot" in m:
        return "bot-check"
    if "javascript runtime" in m or "challenge solving failed" in m:
        return "js-runtime"
    if ("cookie database" in m or "failed to decrypt" in m or "cookies database" in m
            or "dpapi" in m or "cookieloaderror" in m):
        return "cookies"
    if "private video" in m or "video is private" in m:
        return "private"
    if ("members-only" in m or "members only" in m or "join this channel" in m
            or "channel's members" in m):
        return "needs-signin"
    if ("confirm your age" in m or "age-restricted" in m or "age restricted" in m
            or "inappropriate for some users" in m or "age_verification" in m):
        return "needs-signin"
    if ("live event will begin" in m or "premiere" in m and "begin" in m
            or "is_upcoming" in m or "this live event" in m):
        return "live"
    if ("video unavailable" in m or "has been removed" in m or "no longer available" in m
            or "account associated with this video has been terminated" in m
            or "this video is not available" in m):
        return "unavailable"
    if (re.search(r"http error (429|5\d\d)", m) or "too many requests" in m
            or "try again later" in m or "rate-limited" in m or "timed out" in m
            or "connection reset" in m or "connection aborted" in m
            or "remote end closed" in m or "temporary failure" in m
            or "name resolution" in m or "incompleteread" in m
            or "connection refused" in m or "unable to connect" in m):
        return "transient"
    return "other"


def short_error(message: str, limit: int = 300) -> str:
    msg = re.sub(r"^ERROR:\s*", "", str(message)).strip()
    msg = re.sub(r"\s+", " ", msg)
    return msg[:limit]


# =============================================================================
# Pure helpers: captions to text
# =============================================================================

@dataclass
class Cue:
    start: float
    end: float
    text: str


_TAG_RE = re.compile(r"<[^>]*>")
_ANNOTATION_RE = re.compile(r"\[[^\]\n]{0,40}\]|\([^)\n]{0,15}(?:music|applause|laughter|laughs)[^)\n]{0,15}\)",
                            re.IGNORECASE)


def clean_caption_text(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _ANNOTATION_RE.sub(" ", text)  # [Music], [Applause], [ __ ]
    text = text.replace("♪", " ").replace(">>", " ")
    return re.sub(r"\s+", " ", text).strip()


def _vtt_time(t: str) -> float:
    parts = t.strip().replace(",", ".").split(":")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


def parse_vtt(data: str) -> list[Cue]:
    cues = []
    for block in re.split(r"\n\s*\n", data.replace("\r\n", "\n").replace("\r", "\n")):
        lines = block.strip("\n").split("\n")
        for i, line in enumerate(lines):
            if "-->" in line:
                start_s, end_s = line.split("-->", 1)
                end_s = end_s.strip().split(" ")[0]
                try:
                    start, end = _vtt_time(start_s), _vtt_time(end_s)
                except ValueError:
                    break
                text = clean_caption_text(" ".join(lines[i + 1:]))
                if text:
                    cues.append(Cue(start, end, text))
                break
    return cues


def parse_json3(data: str) -> list[Cue]:
    obj = json.loads(data)
    cues = []
    for ev in obj.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = clean_caption_text("".join(s.get("utf8", "") for s in segs))
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000
        dur = ev.get("dDurationMs", 0) / 1000
        end = start + dur
        if any("tOffsetMs" in s for s in segs):
            # Auto captions: events stay on screen until replaced, so use the
            # last word's start to find where speech in this event stopped.
            last_word = start + max(s.get("tOffsetMs", 0) for s in segs) / 1000
            end = min(end, last_word + WORD_DURATION_EST_S) if dur else last_word + WORD_DURATION_EST_S
        cues.append(Cue(start, end, text))
    cues.sort(key=lambda c: c.start)
    return cues


def dedupe_cues(cues: list[Cue], max_overlap: int = 60) -> list[Cue]:
    """Remove the rolling repeats auto-captions produce.

    Each auto-caption cue usually repeats the previous line before adding new
    words. For each cue, drop its longest leading run of words that matches the
    end of the text so far. A one-word match is treated as coincidence unless
    the whole cue is that word.
    """
    out_words: list[str] = []
    result = []
    for c in cues:
        words = c.text.split()
        if not words:
            continue
        tail = [w.lower() for w in out_words[-max_overlap:]]
        lowered = [w.lower() for w in words]
        k = 0
        for n in range(min(len(tail), len(words)), 0, -1):
            if tail[-n:] == lowered[:n]:
                k = n
                break
        if k == 1 and len(words) > 1:
            k = 0
        new = words[k:]
        if not new:
            continue
        out_words.extend(new)
        result.append(Cue(c.start, c.end, " ".join(new)))
    return result


def paragraphise(cues: list[Cue], timestamps: bool = False) -> str:
    """Join cues into paragraphs separated by blank lines."""
    paras: list[tuple[float, str]] = []
    cur: list[str] = []
    p_start = prev_end = 0.0
    prev_text = ""
    for c in cues:
        if cur:
            gap = c.start - prev_end
            elapsed = c.start - p_start
            if ((gap >= PARA_LONG_PAUSE_S and elapsed >= PARA_LONG_PAUSE_MIN_S)
                    or (elapsed >= PARA_SOFT_LEN_S
                        and (gap >= PARA_SOFT_PAUSE_S or prev_text.endswith((".", "?", "!"))))
                    or elapsed >= PARA_HARD_LEN_S):
                paras.append((p_start, " ".join(cur)))
                cur = []
        if not cur:
            p_start = c.start
        cur.append(c.text)
        prev_end = max(c.end, c.start)
        prev_text = c.text
    if cur:
        paras.append((p_start, " ".join(cur)))
    if timestamps:
        return "\n\n".join(f"[{fmt_ts(s)}] {t}" for s, t in paras)
    return "\n\n".join(t for _, t in paras)


def choose_caption_track(subtitles: dict, automatic: dict, lang: str):
    """Pick (kind, key, url, ext) for the best caption track, or None.

    Manual captions in lang (exact, then regional such as en-GB) win. Otherwise
    the auto track in the video's original language, which yt-dlp labels
    '<lang>-orig'. Machine translations of other languages are not used.
    """
    def pick_format(entries):
        by_ext = {e.get("ext"): e for e in entries or [] if e.get("url")}
        for ext in ("json3", "vtt"):
            if ext in by_ext:
                return by_ext[ext]["url"], ext
        return None

    lang = lang.lower()
    manual_keys = [k for k in subtitles or {} if k.lower() != "live_chat"]
    ordered = ([k for k in manual_keys if k.lower() == lang]
               + sorted(k for k in manual_keys if k.lower().startswith(lang + "-")))
    for key in ordered:
        fmt = pick_format(subtitles[key])
        if fmt:
            return ("manual", key, *fmt)
    for key in sorted(automatic or {}):
        if not key.endswith("-orig"):
            continue
        base = key[:-5].lower()
        if base == lang or base.startswith(lang + "-"):
            fmt = pick_format(automatic[key])
            if fmt:
                return ("auto", key, *fmt)
    return None


def captions_to_text(data: str, ext: str, kind: str, timestamps: bool) -> str:
    cues = parse_json3(data) if ext == "json3" else parse_vtt(data)
    if kind == "auto" or ext == "vtt":
        cues = dedupe_cues(cues)
    return paragraphise(cues, timestamps)


def make_header(title: str, channel: str, date: str, duration, vid: str, source: str) -> str:
    return (f"Title: {title}\n"
            f"Channel: {channel or 'unknown'}\n"
            f"Date: {iso_date(date)}\n"
            f"Duration: {fmt_duration(duration)}\n"
            f"URL: {watch_url(vid)}\n"
            f"Transcript: {source}\n")


def is_english(language: str | None) -> bool:
    """Metadata language check; missing language counts as English."""
    return not language or language.lower().split("-")[0] == "en"


# =============================================================================
# Pure helpers: audio splitting and batches
# =============================================================================

def plan_boundaries(duration: float, chunk_s: float) -> list[float]:
    """Target cut times giving equal parts no longer than chunk_s."""
    if chunk_s <= 0 or duration <= chunk_s:
        return []
    n = math.ceil(duration / chunk_s)
    return [duration * k / n for k in range(1, n)]


def parse_silencedetect(stderr: str, offset: float, window_end: float) -> list[tuple[float, float]]:
    """Silences from ffmpeg silencedetect output, shifted by the seek offset."""
    silences = []
    start = None
    for line in stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            start = float(m.group(1)) + offset
            continue
        m = re.search(r"silence_end:\s*(-?[\d.]+)", line)
        if m and start is not None:
            silences.append((max(start, offset), float(m.group(1)) + offset))
            start = None
    if start is not None:
        silences.append((max(start, offset), window_end))
    return silences


def choose_split_point(silences: list[tuple[float, float]], target: float,
                       lo: float, hi: float, window: float = SPLIT_WINDOW_S) -> float | None:
    """Middle of the longest silence near target (nearest wins a tie), or None."""
    best = None
    for s, e in silences:
        mid = (s + e) / 2
        if abs(mid - target) > window or not lo < mid < hi:
            continue
        key = (-(e - s), abs(mid - target))
        if best is None or key < best[0]:
            best = (key, mid)
    return best[1] if best else None


def cuts_to_ranges(duration: float, cuts: list[float]) -> list[tuple[float, float]]:
    edges = [0.0, *cuts, duration]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


class BatchAllocator:
    """Assigns WAV batch numbers. A video's files share one batch; each run
    starts a new batch after the highest existing one (append-only)."""

    def __init__(self, last_batch: int, size: int):
        self.size = size
        self.current = last_batch
        self.count = 0
        self.started = False

    def add(self, nfiles: int) -> int:
        if self.size <= 0:
            return 0
        if not self.started or (self.count > 0 and self.count + nfiles > self.size):
            self.current += 1
            self.count = 0
            self.started = True
        self.count += nfiles
        return self.current


def batch_dir_name(batch: int) -> str:
    return f"batch {batch:02d}"


# =============================================================================
# Pure helpers: merge
# =============================================================================

_TXT_RE = re.compile(
    re.escape(ID_OPEN) + r"([A-Za-z0-9_-]{11})" + re.escape(ID_CLOSE)
    + r"(?: part (\d{1,3}) of (\d{1,3}))?(?:\s*\(\d+\))?\.txt$",
    re.IGNORECASE,
)


def parse_transcript_filename(name: str) -> tuple[str, int, int] | None:
    """'... [id] part 02 of 03.txt' to (id, 2, 3). No part suffix means (id, 1, 1)."""
    m = _TXT_RE.search(name)
    if not m:
        return None
    vid, part, parts = m.group(1), m.group(2), m.group(3)
    if part:
        return vid, int(part), int(parts)
    return vid, 1, 1


def collect_whisper_files(files: list[tuple[str, float]]):
    """Group (path, mtime) pairs by video and part.

    Returns (found, duplicates, unmatched): found maps id to {part: path} and the
    'of NN' each file claimed; duplicates lists the older files that lost to a
    newer one for the same part.
    """
    found: dict[str, dict] = {}
    duplicates, unmatched = [], []
    for path, mtime in files:
        parsed = parse_transcript_filename(os.path.basename(path))
        if not parsed:
            unmatched.append(path)
            continue
        vid, part, parts = parsed
        entry = found.setdefault(vid, {"parts": {}, "claimed": set()})
        entry["claimed"].add(parts)
        prev = entry["parts"].get(part)
        if prev is None or mtime > prev[1]:
            if prev:
                duplicates.append(prev[0])
            entry["parts"][part] = (path, mtime)
        else:
            duplicates.append(path)
    for entry in found.values():
        entry["parts"] = {k: v[0] for k, v in entry["parts"].items()}
    return found, duplicates, unmatched


def stitch_parts(texts: dict[int, str], parts: int) -> tuple[str | None, list[int]]:
    """Join parts 1..parts in order with a blank line, or list the missing ones."""
    missing = [i for i in range(1, parts + 1) if i not in texts]
    if missing:
        return None, missing
    return "\n\n".join(texts[i].strip() for i in range(1, parts + 1)), []


# =============================================================================
# Pure helpers: combined files
# =============================================================================

def group_for_claude(word_counts: list[int], chunk_words: int) -> list[list[int]]:
    """Consecutive groups of at most chunk_words; a larger video gets its own group."""
    groups, cur, size = [], [], 0
    for i, wc in enumerate(word_counts):
        if cur and size + wc > chunk_words:
            groups.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += wc
    if cur:
        groups.append(cur)
    return groups


def _balanced_groups(word_counts: list[int], k: int) -> list[list[int]]:
    """Split into exactly k consecutive groups of roughly equal word count."""
    n = len(word_counts)
    total = sum(word_counts)
    groups, start, cum = [], 0, 0
    for j in range(1, k):
        target = total * j / k
        end = start
        cum += word_counts[start]
        while end + 1 < n - (k - j) and abs(cum + word_counts[end + 1] - target) <= abs(cum - target):
            end += 1
            cum += word_counts[end]
        groups.append(list(range(start, end + 1)))
        start = end + 1
    groups.append(list(range(start, n)))
    return groups


def group_for_gemini(word_counts: list[int], max_sources: int, max_words: int) -> tuple[list[list[int]], int]:
    """Groups for Gemini Notebook, and how many sources over max_sources they are.

    One file per video when the count and sizes allow, because Gemini then cites
    individual videos. Otherwise max_sources groups of roughly equal size; if
    any would exceed max_words, pack up to max_words instead, which can need
    more files than max_sources.
    """
    n = len(word_counts)
    if n == 0:
        return [], 0
    if n <= max_sources and all(wc <= max_words for wc in word_counts):
        return [[i] for i in range(n)], 0
    groups = _balanced_groups(word_counts, min(n, max_sources))
    if any(sum(word_counts[i] for i in g) > max_words for g in groups):
        groups = group_for_claude(word_counts, max_words)
    return groups, max(0, len(groups) - max_sources)


def split_words(body: str, max_words: int) -> list[str]:
    """Split text at paragraph breaks into pieces of at most max_words (a single
    longer paragraph is cut at a word boundary)."""
    pieces, cur, size = [], [], 0
    for para in body.split("\n\n"):
        words = para.split()
        while len(words) > max_words:
            if cur:
                pieces.append("\n\n".join(cur))
                cur, size = [], 0
            pieces.append(" ".join(words[:max_words]))
            words = words[max_words:]
        if cur and size + len(words) > max_words:
            pieces.append("\n\n".join(cur))
            cur, size = [], 0
        if words:
            cur.append(" ".join(words) if para.split() != words else para)
            size += len(words)
    if cur:
        pieces.append("\n\n".join(cur))
    return pieces


def split_transcript(text: str, max_words: int) -> list[str]:
    """Split one transcript (header, blank line, body) into pieces under
    max_words, each starting with the header marked as continued."""
    if len(text.split()) <= max_words:
        return [text]
    header, _, body = text.partition("\n\n")
    room = max(1000, max_words - len(header.split()) - 10)
    pieces = split_words(body, room)
    n = len(pieces)
    return [f"{header}\nSection: {i} of {n}\n\n{p}" for i, p in enumerate(pieces, 1)]


# =============================================================================
# Console and files
# =============================================================================

def say(msg: str = "") -> None:
    print(msg, flush=True)


class NeedsAnswer(Exception):
    pass


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise NeedsAnswer(prompt.strip())


def ask_choice(prompt: str, choices: dict[str, str]) -> str:
    while True:
        ans = ask(prompt).lower()
        if ans in choices:
            return choices[ans]
        say(f"Please enter one of: {', '.join(choices)}")


def write_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".tmp-{os.getpid()}-{random.randint(0, 1 << 30):x}"
    with open(tmp, "w", encoding=encoding, newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def now_stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =============================================================================
# Manifest
# =============================================================================

class Manifest:
    """manifest.csv: one row per video, the state for update, fresh and merge."""

    def __init__(self, path: Path):
        self.path = path
        self.rows: dict[str, dict] = {}
        if path.exists():
            with open(path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("id"):
                        self.rows[row["id"]] = {k: row.get(k) or "" for k in MANIFEST_FIELDS}

    def get(self, vid: str) -> dict | None:
        return self.rows.get(vid)

    def set(self, vid: str, **fields) -> dict:
        row = self.rows.setdefault(vid, {k: "" for k in MANIFEST_FIELDS})
        row["id"] = vid
        for k, v in fields.items():
            if k in MANIFEST_FIELDS:
                row[k] = "" if v is None else str(v)
        row["updated"] = now_stamp()
        return row

    def save(self) -> None:
        rows = sorted(self.rows.values(), key=lambda r: (r["upload_date"] or "99999999", r["id"]))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(".manifest.tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel reads UTF-8
            w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, self.path)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rows.values():
            out[r["status"]] = out.get(r["status"], 0) + 1
        return out

    def last_batch(self) -> int:
        nums = [int(r["batch"]) for r in self.rows.values() if r["batch"].isdigit()]
        return max(nums, default=0)


# =============================================================================
# Preflight and Windows details
# =============================================================================

class Stop(Exception):
    """Ends the run with a message and exit code 2, after saving state."""


def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def preflight() -> None:
    if sys.version_info < (3, 10):
        raise Stop("yt-slurp needs Python 3.10 or later.")
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        raise Stop(
            f"{' and '.join(missing)} not found on the PATH.\n"
            "Install it with:\n\n    winget install Gyan.FFmpeg\n\n"
            "then open a new terminal (the PATH only updates in new windows) and run yt-slurp again.")
    try:
        from yt_dlp.version import __version__
    except ImportError:
        raise Stop('yt-dlp is not installed. In the virtual environment run:  pip install -e .')
    say(f"yt-dlp {__version__}")


JS_RUNTIME_HELP = (
    "yt-dlp needs a JavaScript runtime to read YouTube. Install Deno with:\n\n"
    "    winget install DenoLand.Deno\n\n"
    "then open a new terminal and run yt-slurp again (your progress is saved).\n"
    'If Deno is already installed, update yt-dlp:  pip install -U "yt-dlp[default]"')

COOKIE_HELP = (
    "Chrome, Edge and Brave lock their cookie file while open and encrypt it in a way "
    "yt-dlp often cannot read on Windows. Close the browser completely (check the system "
    "tray) and try again, or use Firefox, which works while open.")


# =============================================================================
# Network (yt-dlp)
# =============================================================================

class YdlLogger:
    def __init__(self):
        self.js_missing = False
        self.last_error = ""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        if classify_error(msg) == "js-runtime":
            self.js_missing = True

    def error(self, msg):
        self.last_error = msg
        if classify_error(msg) == "js-runtime":
            self.js_missing = True


class Net:
    """All network access, with polite delays and retries."""

    def __init__(self, browser: str | None = None):
        self.browser = browser
        self.logger = YdlLogger()
        self._ydls: dict = {}
        self._last_request = 0.0

    def _ydl(self, key: str, **extra):
        from yt_dlp import YoutubeDL
        if key not in self._ydls:
            params = {
                "quiet": True, "no_warnings": False, "noprogress": True,
                "logger": self.logger, "socket_timeout": 30,
                "retries": 3, "extractor_retries": 3,
                "skip_download": True,
            }
            if self.browser:
                params["cookiesfrombrowser"] = (self.browser,)
            params.update(extra)
            self._ydls[key] = YoutubeDL(params)
        return self._ydls[key]

    def _info(self):
        return self._ydl("info", format="bestaudio/best")

    def close(self):
        for y in self._ydls.values():
            try:
                y.close()
            except Exception:
                pass
        self._ydls.clear()

    def check_cookies(self) -> None:
        """Load the browser cookies now so a failure is reported clearly."""
        try:
            self._info().cookiejar
        except Exception as e:
            self.close()
            raise CookieError(short_error(e)) from None

    def _pause(self):
        if self._last_request:
            wait = random.uniform(*DELAY_RANGE_S) - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
        self._last_request = time.monotonic()

    def call(self, what: str, fn):
        for attempt in range(len(RETRY_DELAYS_S) + 1):
            self._pause()
            try:
                result = fn()
            except Exception as e:
                if self.logger.js_missing or classify_error(str(e)) == "js-runtime":
                    raise Stop(JS_RUNTIME_HELP)
                kind = classify_error(str(e))
                if kind == "cookies":
                    raise CookieError(short_error(e)) from None
                if kind == "transient" and attempt < len(RETRY_DELAYS_S):
                    wait = RETRY_DELAYS_S[attempt] * random.uniform(0.8, 1.2)
                    say(f"    {what}: {short_error(e, 120)}. Waiting {wait:.0f} s, then retrying.")
                    time.sleep(wait)
                    continue
                raise
            finally:
                self._last_request = time.monotonic()
            if self.logger.js_missing:
                raise Stop(JS_RUNTIME_HELP)
            return result

    def flat(self, url: str) -> dict:
        return self.call("listing", lambda: self._ydl("flat", extract_flat="in_playlist")
                         .extract_info(url, download=False))

    def video_info(self, vid: str) -> dict:
        return self.call("metadata", lambda: self._info().extract_info(watch_url(vid), download=False))

    def fetch_text(self, url: str) -> str:
        def get():
            with self._info().urlopen(url) as r:
                return r.read().decode("utf-8", "replace")
        return self.call("captions", get)

    def download_audio(self, vid: str, dest: Path) -> Path:
        def get():
            y = self._ydl(f"audio:{dest}", format="bestaudio/best", skip_download=False,
                          outtmpl={"default": str(dest / "%(id)s.%(ext)s")}, noplaylist=True)
            info = y.extract_info(watch_url(vid), download=True)
            downloads = info.get("requested_downloads") or []
            path = downloads[0].get("filepath") if downloads else None
            if not path or not os.path.exists(path):
                raise RuntimeError("audio download finished but the file is missing")
            return Path(path)
        return self.call("audio", get)


class CookieError(Exception):
    pass


# =============================================================================
# Audio (ffmpeg)
# =============================================================================

def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError(f"ffprobe could not read the duration: {short_error(r.stderr)}")


def to_wav(src: Path, dest: Path, rate: int) -> None:
    r = run_ffmpeg(["-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1",
                    "-ar", str(rate), "-c:a", "pcm_s16le", str(dest)])
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"ffmpeg conversion failed: {short_error(r.stderr)}")


def find_cuts(wav: Path, duration: float, chunk_s: float) -> list[float]:
    cuts = []
    for target in plan_boundaries(duration, chunk_s):
        lo = (cuts[-1] if cuts else 0) + MIN_PART_S
        hi = duration - MIN_PART_S
        w_start = max(0.0, target - SPLIT_WINDOW_S)
        w_len = min(duration, target + SPLIT_WINDOW_S) - w_start
        chosen = None
        for db in SILENCE_THRESHOLDS_DB:
            r = run_ffmpeg(["-ss", f"{w_start:.3f}", "-t", f"{w_len:.3f}", "-i", str(wav),
                            "-af", f"silencedetect=noise={db}dB:d={SILENCE_MIN_S}", "-f", "null", "-"])
            chosen = choose_split_point(parse_silencedetect(r.stderr, w_start, w_start + w_len),
                                        target, lo, hi)
            if chosen is not None:
                break
        cuts.append(chosen if chosen is not None else max(lo, min(target, hi)))
    return cuts


def cut_wav(src: Path, dest: Path, start: float, end: float) -> None:
    r = run_ffmpeg(["-loglevel", "error", "-y", "-i", str(src), "-ss", f"{start:.3f}",
                    "-to", f"{end:.3f}", "-c:a", "pcm_s16le", str(dest)])
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"ffmpeg split failed: {short_error(r.stderr)}")


# =============================================================================
# Per-source run
# =============================================================================

@dataclass
class Source:
    url: str
    kind: str                 # channel or playlist
    name: str = ""
    source_id: str = ""
    folder: Path | None = None
    tabs: dict | None = None  # type to list of flat entries (channels)
    entries: list | None = None  # playlists
    mode: str = "new"         # new, update or fresh
    types: list | None = None
    failed: str = ""


def probe_source(src: Source, net: Net) -> None:
    """Flat-list a channel's tabs or a playlist."""
    if src.kind == "playlist":
        info = net.flat(src.url)
        src.name = info.get("title") or info.get("id") or "playlist"
        src.source_id = info.get("id") or ""
        src.entries = [e for e in info.get("entries") or [] if e and e.get("id")]
        return
    src.tabs = {}
    for tab in TYPES:
        try:
            info = net.flat(f"{src.url}/{tab}")
        except Stop:
            raise
        except Exception as e:
            if classify_error(str(e)) == "transient":
                raise
            continue  # tab missing
        if not src.name:
            src.name = info.get("channel") or info.get("uploader") or ""
            src.source_id = info.get("channel_id") or info.get("uploader_id") or ""
        entries = [e for e in info.get("entries") or [] if e and e.get("id")]
        if entries:
            src.tabs[tab] = entries
    if not src.name:
        src.name = src.url.rstrip("/").rsplit("/", 1)[-1].lstrip("@")


def choose_folder(src: Source, output: Path, taken: set) -> Path:
    base = safe_filename(src.name, MAX_FOLDER_NAME_LEN)
    folder = output / base
    run_file = folder / "run.json"
    clash = str(folder).lower() in taken
    if not clash and run_file.exists():
        try:
            clash = json.loads(read_text(run_file)).get("url") != src.url
        except (ValueError, OSError):
            clash = False
    if clash:
        folder = output / safe_filename(f"{base} {src.source_id or 'source'}", MAX_FOLDER_NAME_LEN + 30)
    taken.add(str(folder).lower())
    return folder


def decide_mode(src: Source, args) -> None:
    folder = src.folder
    if not (folder / "manifest.csv").exists():
        src.mode = "new"
        return
    if args.update:
        src.mode = "update"
    elif args.fresh:
        src.mode = "fresh"
    else:
        rows = len(Manifest(folder / "manifest.csv").rows)
        say(f"\n{folder} already has a manifest with {rows} videos.")
        src.mode = ask_choice("(u) update: fetch new videos and retry failures, or (f) start fresh? [u/f] ",
                              {"u": "update", "f": "fresh"})
    if src.mode == "fresh":
        confirm_fresh(folder)


def confirm_fresh(folder: Path) -> None:
    doomed = [p for p in folder.iterdir() if p.name != DIR_WHISPER]
    nfiles = sum(1 for p in doomed for _ in ([p] if p.is_file() else p.rglob("*")))
    say(f"Start fresh deletes {nfiles} files in {folder}, keeping {DIR_WHISPER}/ (your saved Whisper text).")
    if ask("Type yes to delete them: ").lower() != "yes":
        raise Stop("Nothing deleted. Run again and choose (u) to update instead.")
    for p in doomed:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


def choose_types(sources: list[Source], args) -> None:
    """Set src.types for every channel. Ask once, covering all channels that
    have more than one type, unless --types or a stored choice applies."""
    wanted = parse_types(args.types) if args.types else None
    undecided = []
    for src in sources:
        if src.kind != "channel":
            continue
        present = [t for t in TYPES if t in (src.tabs or {})]
        if wanted:
            src.types = [t for t in wanted if t in present]
        elif src.mode == "update" and (stored := load_run(src.folder).get("types")):
            src.types = [t for t in stored if t in present]
        elif len(present) <= 1:
            src.types = present
        else:
            undecided.append(src)
    if not undecided:
        return
    say("\nVideo types found:")
    for src in undecided:
        counts = ", ".join(f"{t} {len(src.tabs[t])}" for t in TYPES if t in src.tabs)
        say(f"  {src.name}: {counts}")
    say("  1 videos   2 shorts   3 streams   a all")
    while True:
        ans = ask("Which types? Enter numbers separated by commas, or a for all: ").lower().replace(" ", "")
        picked = set()
        for part in ans.split(","):
            if part in ("a", "all"):
                picked.update(TYPES)
            elif part in ("1", "2", "3"):
                picked.add(TYPES[int(part) - 1])
            elif part in TYPES:
                picked.add(part)
            else:
                picked = set()
                break
        if picked:
            break
        say("Please enter for example 1 or 1,3 or a.")
    for src in undecided:
        src.types = [t for t in TYPES if t in picked and t in src.tabs]


def parse_types(value: str) -> list[str]:
    items = [v.strip().lower() for v in value.split(",") if v.strip()]
    if "all" in items:
        return list(TYPES)
    bad = [v for v in items if v not in TYPES]
    if bad:
        raise Stop(f"--types: unknown type {', '.join(bad)}. Use videos, shorts, streams or all.")
    return [t for t in TYPES if t in items]


def load_run(folder: Path) -> dict:
    try:
        return json.loads(read_text(folder / "run.json"))
    except (OSError, ValueError):
        return {}


META_KEYS = ("id", "title", "channel", "uploader", "upload_date", "release_date", "duration",
             "language", "live_status", "availability", "webpage_url")


def trim_meta(info: dict, lang: str) -> dict:
    meta = {k: info.get(k) for k in META_KEYS}

    def keep(entries):
        return [{"ext": e.get("ext"), "url": e.get("url")} for e in entries or []
                if e.get("ext") in ("json3", "vtt")]

    lang = lang.lower()
    meta["subtitles"] = {k: keep(v) for k, v in (info.get("subtitles") or {}).items()
                         if k.lower().startswith(lang)}
    meta["automatic_captions"] = {k: keep(v) for k, v in (info.get("automatic_captions") or {}).items()
                                  if k.endswith("-orig") or k.lower().startswith(lang)}
    meta["fetched"] = time.time()
    return meta


class RunContext:
    """Settings and shared state for one yt-slurp run."""

    def __init__(self, args, net: Net):
        self.args = args
        self.net = net
        self.bot_streak = 0
        self.stop_all = False
        self.signin_asked = False


class SourceRun:
    def __init__(self, src: Source, ctx: RunContext):
        self.src = src
        self.ctx = ctx
        self.args = ctx.args
        self.folder = src.folder
        self.manifest = Manifest(self.folder / "manifest.csv")
        self.meta_dir = self.folder / DIR_WORK / "meta"
        self.audio_dir = self.folder / DIR_WORK / "audio"
        self.tmp_dir = self.folder / DIR_WORK / "tmp"
        self.budget = title_budget(self.folder.resolve())
        self.batches: BatchAllocator | None = None

    # ----- metadata -----

    def meta_path(self, vid):
        return self.meta_dir / f"{vid}.json"

    def load_meta(self, vid, max_age=None) -> dict | None:
        try:
            meta = json.loads(read_text(self.meta_path(vid)))
        except (OSError, ValueError):
            return None
        if max_age is not None and time.time() - meta.get("fetched", 0) > max_age:
            return None
        return meta

    def fetch_meta(self, vid, max_age=None) -> dict:
        meta = self.load_meta(vid, max_age)
        if meta is None:
            info = self.ctx.net.video_info(vid)
            meta = trim_meta(info, self.args.lang)
            write_atomic(self.meta_path(vid), json.dumps(meta))
        return meta

    # ----- listing -----

    def listing(self) -> list[tuple[dict, str]]:
        if self.src.kind == "playlist":
            return [(e, "video") for e in self.src.entries]
        out, seen = [], set()
        for tab in self.src.types or []:
            for e in self.src.tabs.get(tab, []):
                if e["id"] not in seen:
                    seen.add(e["id"])
                    out.append((e, TYPE_LABEL[tab]))
        return out

    def select(self) -> list[str]:
        """Record listing rows and return the IDs to process, in listing order."""
        a = self.args
        min_s = a.min_minutes * 60
        update = self.src.mode == "update"
        todo, short_n, short_by_type, total_by_type = [], 0, {}, {}
        for e, vtype in self.listing():
            vid = e["id"]
            total_by_type[vtype] = total_by_type.get(vtype, 0) + 1
            row = self.manifest.get(vid)
            title = e.get("title") or (row or {}).get("title") or vid
            dur = e.get("duration") or ((row or {}).get("duration") or None)
            if title in ("[Private video]", "[Deleted video]"):
                self.manifest.set(vid, title=title, type=vtype, status="skipped-private",
                                  error="private or deleted")
                continue
            known_short = dur is not None and float(dur) < min_s
            if dur is None and vtype == "short" and min_s > SHORTS_MAX_S:
                known_short = True  # every Short is under the limit; no need to fetch it
            if known_short:
                if not row or row["status"] in ("", "pending", "skipped-short"):
                    self.manifest.set(vid, title=title, type=vtype, duration=int(float(dur)) if dur else "",
                                      status="skipped-short", error="")
                short_n += 1
                short_by_type[vtype] = short_by_type.get(vtype, 0) + 1
                continue
            if row and update and not self.needs_work(row):
                continue
            if row and not update:
                continue  # already handled earlier in this run
            if not row:
                self.manifest.set(vid, title=title, type=vtype, status="pending",
                                  duration=int(float(dur)) if dur else "")
            elif row["status"] == "skipped-short":
                self.manifest.set(vid, status="pending")
            todo.append(vid)
        if short_n:
            say(f"  Excluded {short_n} videos shorter than {a.min_minutes} minutes.")
        for vtype, n in short_by_type.items():
            if n == total_by_type.get(vtype) and vtype == "short":
                say("  Every Short is under the minimum length. Use --min-minutes 0 to include them.")
        if a.limit and len(todo) > a.limit:
            say(f"  --limit {a.limit}: processing {a.limit} of {len(todo)}.")
            todo = todo[:a.limit]
        return todo

    def needs_work(self, row: dict) -> bool:
        st = row["status"]
        if st in ("pending", "failed", "skipped-live", "skipped-short"):
            return True
        if st == "needs-signin":
            return bool(self.ctx.net.browser)
        if st == "skipped-non-english":
            return self.args.include_non_english
        if st == "transcript":
            return not find_by_id(self.folder / DIR_TRANSCRIPTS, row["id"], ".txt")
        if st == "wav":
            n = int(row["wav_files"] or 0)
            return len(find_by_id(self.folder / DIR_NEEDS, row["id"], ".wav")) < n or n == 0
        return False

    # ----- per video -----

    def record_error(self, vid: str, err: Exception) -> None:
        msg = short_error(err)
        kind = classify_error(msg)
        status = {"needs-signin": "needs-signin", "private": "skipped-private",
                  "unavailable": "skipped-private", "live": "skipped-live"}.get(kind, "failed")
        self.manifest.set(vid, status=status, error=msg)
        say(f"    {status}: {msg[:160]}")
        if kind == "bot-check":
            self.ctx.bot_streak += 1
        else:
            self.ctx.bot_streak = 0

    def metadata_pass(self, todo: list[str]) -> list[str]:
        """Fetch metadata for each video. Returns the IDs ready for content."""
        ready = []
        min_s = self.args.min_minutes * 60
        for i, vid in enumerate(todo, 1):
            if self.ctx.stop_all:
                break
            row = self.manifest.get(vid)
            say(f"  [{i}/{len(todo)}] metadata: {row['title'][:70]}")
            try:
                meta = self.fetch_meta(vid)
            except CookieError:
                raise
            except Stop:
                raise
            except Exception as e:
                self.record_error(vid, e)
                self.manifest.save()
                if self.ctx.bot_streak >= BOT_CHECK_LIMIT:
                    self.handle_bot_check()
                continue
            self.ctx.bot_streak = 0
            self.manifest.set(
                vid, title=meta.get("title") or row["title"],
                channel=meta.get("channel") or meta.get("uploader") or "",
                upload_date=meta.get("upload_date") or meta.get("release_date") or "",
                duration=int(meta["duration"]) if meta.get("duration") else row["duration"],
                language=meta.get("language") or "", error="")
            if meta.get("live_status") in ("is_live", "is_upcoming", "post_live"):
                self.manifest.set(vid, status="skipped-live", error=meta.get("live_status"))
            elif meta.get("duration") and meta["duration"] < min_s:
                self.manifest.set(vid, status="skipped-short")
            else:
                if self.manifest.get(vid)["status"] != "pending":
                    self.manifest.set(vid, status="pending")
                ready.append(vid)
            self.manifest.save()
        return ready

    def handle_bot_check(self) -> None:
        say("\nYouTube is asking to confirm you are not a bot, on several videos in a row.")
        self.ctx.bot_streak = 0
        if self.ctx.net.browser:
            say("Cookies are already in use. Stopping here; wait an hour and run with --update.")
            self.ctx.stop_all = True
            return
        browser = ask_browser(self.args, "Sign in with cookies from a browser and carry on?")
        if not browser or not switch_to_cookies(self.ctx, browser):
            say("Stopping this pass. Run again later with --update to continue.")
            self.ctx.stop_all = True

    def content_pass(self, ready: list[str]) -> None:
        for i, vid in enumerate(ready, 1):
            if self.ctx.stop_all:
                break
            row = self.manifest.get(vid)
            say(f"  [{i}/{len(ready)}] {row['title'][:70]}")
            try:
                self.process_content(vid)
            except (CookieError, Stop):
                raise
            except Exception as e:
                self.record_error(vid, e)
                if self.ctx.bot_streak >= BOT_CHECK_LIMIT:
                    self.manifest.save()
                    self.handle_bot_check()
            self.manifest.save()

    def process_content(self, vid: str) -> None:
        a = self.args
        meta = self.fetch_meta(vid, max_age=CAPTION_INFO_MAX_AGE_S)
        row = self.manifest.get(vid)
        title = fit_title(safe_filename(meta.get("title") or row["title"]), self.budget)
        stem = video_stem(row["upload_date"], title, vid)
        channel = row["channel"] or self.src.name

        track = choose_caption_track(meta.get("subtitles"), meta.get("automatic_captions"), a.lang)
        if track:
            kind, key, url, ext = track
            text = captions_to_text(self.ctx.net.fetch_text(url), ext, kind, a.timestamps)
            if text.strip():
                label = f"YouTube {'manual' if kind == 'manual' else 'auto-generated'} captions ({key.removesuffix('-orig')})"
                header = make_header(meta.get("title") or row["title"], channel, row["upload_date"],
                                     row["duration"], vid, label)
                for old in find_by_id(self.folder / DIR_TRANSCRIPTS, vid, ".txt"):
                    old.unlink()
                write_atomic(self.folder / DIR_TRANSCRIPTS / f"{stem}.txt", f"{header}\n{text}\n")
                self.manifest.set(vid, status="transcript", source=kind, error="")
                say(f"    transcript ({kind} captions)")
                return

        if not is_english(meta.get("language")) and not a.include_non_english:
            self.manifest.set(vid, status="skipped-non-english",
                              error=f"no captions; language {meta.get('language')}")
            say(f"    skipped-non-english ({meta.get('language')})")
            return
        self.make_wavs(vid, stem)

    def make_wavs(self, vid: str, stem: str) -> None:
        a = self.args
        for old in find_by_id(self.folder / DIR_NEEDS, vid, ".wav"):
            old.unlink()
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        audio = next((p for p in self.audio_dir.iterdir()
                      if p.name.startswith(vid + ".") and not p.name.endswith((".part", ".ytdl"))), None)
        if audio is None:
            say("    downloading audio")
            audio = self.ctx.net.download_audio(vid, self.audio_dir)
        say("    converting to WAV")
        full = self.tmp_dir / f"{vid}.wav"
        to_wav(audio, full, a.wav_rate)
        duration = probe_duration(full)
        cuts = find_cuts(full, duration, a.chunk_minutes * 60) if a.chunk_minutes > 0 else []
        ranges = cuts_to_ranges(duration, cuts)
        parts = len(ranges)
        pieces = []
        if parts == 1:
            pieces.append(full)
        else:
            say(f"    splitting into {parts} parts")
            for n, (s, e) in enumerate(ranges, 1):
                piece = self.tmp_dir / f"{vid}_{n:02d}.wav"
                cut_wav(full, piece, s, e)
                pieces.append(piece)
        if self.batches is None:
            self.batches = BatchAllocator(max(self.manifest.last_batch(), existing_batches(self.folder)),
                                          a.batch_files)
        batch = self.batches.add(parts)
        dest_dir = self.folder / DIR_NEEDS / (batch_dir_name(batch) if batch else "")
        dest_dir.mkdir(parents=True, exist_ok=True)
        (self.folder / DIR_WHISPER).mkdir(exist_ok=True)
        for n, piece in enumerate(pieces, 1):
            os.replace(piece, dest_dir / f"{stem}{part_suffix(n, parts)}.wav")
        if full.exists():
            full.unlink()
        audio.unlink(missing_ok=True)
        self.manifest.set(vid, status="wav", source="", wav_files=parts, batch=batch or "", error="")
        say(f"    {parts} WAV file{'s' if parts > 1 else ''} in {dest_dir.relative_to(self.folder)}")

    # ----- whole source -----

    def run(self, only: list[str] | None = None) -> None:
        a = self.args
        if self.budget < MIN_TITLE_BUDGET:
            raise Stop(f"The output path {self.folder.resolve()} is too long to keep filenames under "
                       f"{MAX_PATH_LEN} characters. Use --output with a shorter folder, such as C:\\yt.")
        self.folder.mkdir(parents=True, exist_ok=True)
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        save_run(self.src, a)
        try:
            todo = only if only is not None else self.select()
            self.manifest.save()
            say(f"  {len(todo)} videos to process.")
            ready = self.metadata_pass(todo)
            write_links(self.folder, self.manifest)
            if not a.links_only:
                self.content_pass(ready)
        finally:
            self.manifest.save()
            write_needs_list(self.folder, self.manifest)


def existing_batches(folder: Path) -> int:
    needs = folder / DIR_NEEDS
    if not needs.is_dir():
        return 0
    nums = [int(m.group(1)) for p in needs.iterdir() if (m := re.fullmatch(r"batch (\d+)", p.name))]
    return max(nums, default=0)


def save_run(src: Source, args) -> None:
    run = load_run(src.folder)
    run.update({
        "url": src.url, "kind": src.kind, "name": src.name, "types": src.types,
        "lang": args.lang, "min_minutes": args.min_minutes, "chunk_minutes": args.chunk_minutes,
        "wav_rate": args.wav_rate, "updated": now_stamp(),
    })
    run.setdefault("created", now_stamp())
    write_atomic(src.folder / "run.json", json.dumps(run, indent=2))


def write_links(folder: Path, manifest: Manifest) -> None:
    rows = [r for r in manifest.rows.values() if r["status"] not in ("skipped-short", "skipped-private")]
    rows.sort(key=lambda r: (r["upload_date"] or "99999999", r["id"]))
    lines = [f"{iso_date(r['upload_date'])} | {fmt_duration(r['duration'])} | {r['title']} | {watch_url(r['id'])}"
             for r in rows]
    write_atomic(folder / "links.txt", "\n".join(lines) + ("\n" if lines else ""))


def write_needs_list(folder: Path, manifest: Manifest) -> None:
    rows = [r for r in manifest.rows.values() if r["status"] in ("wav", "merged") and r["wav_files"]]
    if not rows and not (folder / "needs-transcription.txt").exists():
        return
    rows.sort(key=lambda r: (int(r["batch"] or 0), r["upload_date"], r["id"]))
    lines = ["Videos without captions, as WAV files for the Whisper app.",
             f"Save each transcript into {DIR_WHISPER}/, then run: yt-slurp merge \"{folder}\"",
             "",
             "Batch | ID | WAV files | Status | Title"]
    for r in rows:
        status = "merged" if r["status"] == "merged" else "pending"
        lines.append(f"{r['batch'] or '-'} | {r['id']} | {r['wav_files']} | {status} | {r['title']}")
    write_atomic(folder / "needs-transcription.txt", "\n".join(lines) + "\n")


# =============================================================================
# Combined files
# =============================================================================

def build_combined(folder: Path, chunk_words: int, max_sources: int, max_source_words: int) -> dict:
    """Rebuild claude-parts/ and gemini-notebook/ from transcripts/."""
    tdir = folder / DIR_TRANSCRIPTS
    files = sorted(tdir.glob("*.txt")) if tdir.is_dir() else []
    texts = [read_text(p).strip() for p in files]
    name = folder.name
    for d in (DIR_CLAUDE, DIR_GEMINI):
        if (folder / d).exists():
            shutil.rmtree(folder / d)
    if not texts:
        return {"videos": 0, "claude": 0, "gemini": 0, "gemini_over": 0, "oversize": []}

    joiner = f"\n\n{SEPARATOR}\n\n"
    counts = [len(t.split()) for t in texts]
    oversize = [files[i].name for i, wc in enumerate(counts) if wc > chunk_words]

    groups = group_for_claude(counts, chunk_words)
    for n, g in enumerate(groups, 1):
        write_atomic(folder / DIR_CLAUDE / f"{name} part {n:02d} of {len(groups):02d}.txt",
                     joiner.join(texts[i] for i in g) + "\n")

    # Gemini: split any video over the hard per-source limit into sections first.
    limit = min(max_source_words, GEMINI_MAX_WORDS_PER_SOURCE)
    items, item_files = [], []
    for f, t in zip(files, texts):
        for piece in split_transcript(t, limit):
            items.append(piece)
            item_files.append(f)
    icounts = [len(t.split()) for t in items]
    ggroups, over = group_for_gemini(icounts, max_sources, limit)
    per_video = all(len(g) == 1 for g in ggroups) and len(items) == len(files)
    for n, g in enumerate(ggroups, 1):
        if per_video:
            fname = f"{n:03d} {item_files[g[0]].name}"
        else:
            first = file_date(item_files[g[0]].name)
            last = file_date(item_files[g[-1]].name)
            fname = f"{n:02d} of {len(ggroups):02d} {first} to {last}.txt"
        write_atomic(folder / DIR_GEMINI / fname, joiner.join(items[i] for i in g) + "\n")
    return {"videos": len(texts), "claude": len(groups), "gemini": len(ggroups),
            "gemini_over": over, "oversize": oversize}


def file_date(name: str) -> str:
    m = re.match(r"\d{4}-\d{2}-\d{2}", name)
    return m.group(0) if m else "undated"


def report_combined(stats: dict, args) -> None:
    if not stats["videos"]:
        say("No transcripts yet, so no combined files.")
        return
    say(f"Combined {stats['videos']} transcripts: {stats['claude']} Claude parts, "
        f"{stats['gemini']} Gemini Notebook sources.")
    for name in stats["oversize"]:
        say(f"  Warning: {name} is over {args.chunk_words:,} words, so it has a Claude part to itself.")
    if stats["gemini_over"]:
        say(f"  Warning: Gemini Notebook needs {stats['gemini']} sources, {stats['gemini_over']} over "
            f"the limit of {args.max_sources}. Use two notebooks or a paid plan.")


# =============================================================================
# Merge
# =============================================================================

def merge(folder: Path, args) -> None:
    manifest_path = folder / "manifest.csv"
    if not manifest_path.exists():
        raise Stop(f"No manifest.csv in {folder}. Give the folder that yt-slurp created for the channel or playlist.")
    manifest = Manifest(manifest_path)
    run = load_run(folder)
    files = []
    for d in (folder / DIR_WHISPER, folder / DIR_NEEDS):
        if d.is_dir():
            files += [(str(p), p.stat().st_mtime) for p in d.rglob("*")
                      if p.is_file() and p.suffix.lower() == ".txt"]
    found, duplicates, unmatched = collect_whisper_files(files)
    budget = title_budget(folder.resolve())

    merged, incomplete = [], []
    for vid, entry in sorted(found.items()):
        row = manifest.get(vid)
        if not row or row["status"] not in ("wav", "merged"):
            unmatched += list(entry["parts"].values())
            continue
        expected = int(row["wav_files"] or 0) or max(entry["claimed"])
        texts = {k: read_text(Path(p)) for k, p in entry["parts"].items() if k <= expected}
        body, missing = stitch_parts(texts, expected)
        if body is None:
            incomplete.append((row, missing, expected))
            continue
        meta = {}
        try:
            meta = json.loads(read_text(folder / DIR_WORK / "meta" / f"{vid}.json"))
        except (OSError, ValueError):
            pass
        title = meta.get("title") or row["title"]
        header = make_header(title, row["channel"] or run.get("name", ""), row["upload_date"],
                             row["duration"], vid, "Whisper large-v3 (transcriber app)")
        stem = video_stem(row["upload_date"], fit_title(safe_filename(title), budget), vid)
        for old in find_by_id(folder / DIR_TRANSCRIPTS, vid, ".txt"):
            old.unlink()
        write_atomic(folder / DIR_TRANSCRIPTS / f"{stem}.txt", f"{header}\n{body.strip()}\n")
        manifest.set(vid, status="merged", source="whisper", error="")
        merged.append(row)
        if args.delete_wavs:
            for wav in find_by_id(folder / DIR_NEEDS, vid, ".wav"):
                wav.unlink()
    manifest.save()
    write_needs_list(folder, manifest)

    say(f"Merged {len(merged)} videos.")
    for row, missing, expected in incomplete:
        miss = ", ".join(f"{m:02d}" for m in missing)
        say(f"  Not merged, parts missing ({miss} of {expected:02d}): {row['title']} [{row['id']}]")
    if duplicates:
        say(f"  {len(duplicates)} duplicate .txt files ignored (the newest copy of each part was used):")
        for p in duplicates:
            say(f"    {p}")
    if unmatched:
        say(f"  {len(unmatched)} .txt files match no video awaiting transcription:")
        for p in unmatched:
            say(f"    {p}")
    waiting = [r for r in manifest.rows.values() if r["status"] == "wav"]
    if waiting:
        say(f"  {len(waiting)} videos still need Whisper transcripts.")
    report_combined(build_combined(folder, args.chunk_words, args.max_sources, args.max_source_words), args)


# =============================================================================
# Smoke test
# =============================================================================

SMOKE_ID = "AbC-d_123xY"


def smoke_wav(folder: Path) -> None:
    """Write a two-part WAV pair with the real naming scheme, for testing the
    Whisper app's save dialog before a large batch."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / DIR_WHISPER).mkdir(exist_ok=True)
    dest_dir = folder / DIR_NEEDS / batch_dir_name(1)
    dest_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().strftime("%Y%m%d")
    title = "yt-slurp smoke test"
    stem = video_stem(today, title, SMOKE_ID)
    tmp = folder / DIR_WORK / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for n in (1, 2):
        words = "one" if n == 1 else "two"
        dest = dest_dir / f"{stem}{part_suffix(n, 2)}.wav"
        raw = tmp / f"speech{n}.wav"
        spoken = os.name == "nt" and speak_to_wav(
            f"This is part {words} of the yt slurp smoke test. If you can read this, the file name worked.", raw)
        if spoken:
            to_wav(raw, dest, DEFAULT_WAV_RATE)
        else:
            r = run_ffmpeg(["-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                            "-ac", "1", "-ar", str(DEFAULT_WAV_RATE), "-c:a", "pcm_s16le", str(dest)])
            if r.returncode != 0:
                raise Stop(f"ffmpeg could not make the test WAV: {short_error(r.stderr)}")
        say(f"Wrote {dest}")
    shutil.rmtree(tmp, ignore_errors=True)
    manifest = Manifest(folder / "manifest.csv")
    manifest.set(SMOKE_ID, title=title, channel="yt-slurp", upload_date=today, duration=10,
                 type="video", status="wav", wav_files=2, batch=1)
    manifest.save()
    write_atomic(folder / "run.json", json.dumps({"name": "yt-slurp smoke test", "kind": "smoke"}, indent=2))
    write_needs_list(folder, manifest)
    say("")
    say("Now:")
    say(f"  1. Drag both WAVs from {dest_dir} into the Whisper app and transcribe them.")
    say(f"  2. Click Save as .txt for each and save into {folder / DIR_WHISPER}")
    say("     Check the pre-filled filename still has the [brackets] and the ID exactly.")
    say(f"  3. Run: yt-slurp merge \"{folder}\"")
    say("Pass: merge reports 1 video merged. If the brackets were changed or the merge finds")
    say("nothing, change ID_OPEN and ID_CLOSE at the top of yt_slurp.py.")


def speak_to_wav(text: str, dest: Path) -> bool:
    """Use Windows' built-in speech voice to make a short spoken WAV."""
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{str(dest).replace(chr(39), chr(39) * 2)}'); "
        f"$s.Speak('{text.replace(chr(39), chr(39) * 2)}'); $s.Dispose()")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, timeout=60)
        return r.returncode == 0 and dest.exists() and dest.stat().st_size > 1000
    except (OSError, subprocess.SubprocessError):
        return False


# =============================================================================
# Sign-in retry
# =============================================================================

def ask_browser(args, question: str) -> str | None:
    say(question)
    say("  1 chrome   2 edge   3 firefox   4 brave   n none")
    choice = ask_choice("Browser: ", {"1": "chrome", "2": "edge", "3": "firefox", "4": "brave",
                                      "chrome": "chrome", "edge": "edge", "firefox": "firefox",
                                      "brave": "brave", "n": "", "none": ""})
    return choice or None


def switch_to_cookies(ctx: RunContext, browser: str) -> bool:
    net = Net(browser)
    try:
        net.check_cookies()
    except CookieError as e:
        say(f"Could not read cookies from {browser}: {e}")
        say(COOKIE_HELP)
        return False
    ctx.net.close()
    ctx.net = net
    say(f"Using cookies from {browser}.")
    return True


def signin_retry(runs: list[SourceRun], ctx: RunContext) -> None:
    pending = {r: [v for v, row in r.manifest.rows.items() if row["status"] == "needs-signin"] for r in runs}
    total = sum(len(v) for v in pending.values())
    if not total:
        return
    if ctx.net.browser:
        return  # cookies were already in use for this pass
    say(f"\n{total} videos need you to be signed in (members-only or age-restricted).")
    browser = ctx.args.cookies_from_browser
    if browser is None:
        browser = ask_browser(ctx.args, "Retry them with cookies from a browser where you are signed in to YouTube?")
    if not browser or browser == "none":
        say("Left as needs-signin. Run with --update --cookies-from-browser firefox to try again.")
        return
    if not switch_to_cookies(ctx, browser):
        return
    for run, vids in pending.items():
        if vids:
            say(f"\n{run.src.name}: retrying {len(vids)} with cookies")
            for v in vids:
                (run.meta_path(v)).unlink(missing_ok=True)
            run.src.mode = "update"
            run.run(only=vids)


# =============================================================================
# Summary
# =============================================================================

def summarise(run: SourceRun, combined: dict) -> None:
    m = run.manifest
    counts = m.counts()
    say(f"\n{run.src.name}")
    say("  " + ", ".join(f"{s} {counts[s]}" for s in STATUSES if counts.get(s)))
    say(f"  Folder: {run.folder.resolve()}")
    if combined["videos"]:
        say(f"  Claude: {DIR_CLAUDE}/ ({combined['claude']} files)   "
            f"Gemini Notebook: {DIR_GEMINI}/ ({combined['gemini']} files)")
    waiting = [r for r in m.rows.values() if r["status"] == "wav"]
    if waiting:
        nfiles = sum(int(r["wav_files"] or 0) for r in waiting)
        batches = sorted({int(r["batch"]) for r in waiting if r["batch"].isdigit()})
        say(f"  Next: {nfiles} WAV files for {len(waiting)} videos"
            + (f" in batches {', '.join(f'{b:02d}' for b in batches)}" if batches else "") + ".")
        say(f"    1. Drag one batch folder's WAVs from {run.folder.resolve() / DIR_NEEDS} into the Whisper app.")
        say(f"    2. Click Save as .txt for each into {run.folder.resolve() / DIR_WHISPER} before closing the app.")
        say(f"    3. Repeat per batch, then run: yt-slurp merge \"{run.folder.resolve()}\"")
    risky = [r for r in waiting if not r["language"] and non_ascii_share(r["title"]) > 0.5]
    for r in risky:
        say(f"  Check the language (no language in metadata): {r['title']} [{r['id']}]")
    if counts.get("needs-signin"):
        say("  Signed-in videos: run with --update --cookies-from-browser firefox")
    if counts.get("failed"):
        say("  Failures: see the error column in manifest.csv; --update retries them.")


def non_ascii_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum(1 for c in letters if ord(c) > 127) / len(letters) if letters else 0.0


# =============================================================================
# Command line
# =============================================================================

def build_run_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yt-slurp",
        description="Collect YouTube transcripts for a channel or playlist. "
                    "Other commands: 'yt-slurp merge <folder>' and 'yt-slurp smoke-wav [folder]'.")
    p.add_argument("url", nargs="?", help="channel or playlist URL")
    p.add_argument("--file", help="text file of URLs, one per line (# comments allowed)")
    p.add_argument("--output", default=DEFAULT_OUTPUT, help=f"parent output folder (default {DEFAULT_OUTPUT})")
    p.add_argument("--types", help="videos, shorts, streams (comma-separated) or all")
    p.add_argument("--min-minutes", type=float, default=DEFAULT_MIN_MINUTES,
                   help=f"skip videos shorter than this (default {DEFAULT_MIN_MINUTES})")
    p.add_argument("--lang", default=DEFAULT_LANG, help=f"caption language (default {DEFAULT_LANG})")
    p.add_argument("--timestamps", action="store_true", help="add [mm:ss] at the start of each paragraph")
    p.add_argument("--links-only", action="store_true", help="stop after links.txt")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true", help="re-run: new videos and retries")
    mode.add_argument("--fresh", action="store_true", help="re-run: delete and start again")
    p.add_argument("--include-non-english", action="store_true",
                   help="make WAVs for non-English videos without captions")
    p.add_argument("--wav-rate", type=int, default=DEFAULT_WAV_RATE, help="WAV sample rate (default 16000)")
    p.add_argument("--chunk-minutes", type=float, default=DEFAULT_CHUNK_MINUTES,
                   help="split audio longer than this; 0 disables (default 60)")
    p.add_argument("--batch-files", type=int, default=DEFAULT_BATCH_FILES,
                   help="WAV files per batch folder; 0 disables (default 10)")
    p.add_argument("--cookies-from-browser", choices=[*BROWSERS, "none"],
                   help="browser for retrying sign-in videos, or none")
    p.add_argument("--limit", type=int, help="process only the first N videos")
    add_combined_args(p)
    return p


def add_combined_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--chunk-words", type=int, default=DEFAULT_CHUNK_WORDS,
                   help=f"max words per Claude part (default {DEFAULT_CHUNK_WORDS})")
    p.add_argument("--max-sources", type=int, default=DEFAULT_MAX_SOURCES,
                   help=f"max Gemini Notebook files (default {DEFAULT_MAX_SOURCES})")
    p.add_argument("--max-source-words", type=int, default=DEFAULT_MAX_SOURCE_WORDS,
                   help=f"max words per Gemini Notebook file (default {DEFAULT_MAX_SOURCE_WORDS})")


def read_url_file(path: str) -> list[str]:
    try:
        lines = read_text(Path(path)).splitlines()
    except OSError as e:
        raise Stop(f"Could not read {path}: {e.strerror}")
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def cmd_run(argv: list[str]) -> None:
    args = build_run_parser().parse_args(argv)
    if bool(args.url) == bool(args.file):
        raise Stop("Give one channel or playlist URL, or --file urls.txt.")
    preflight()
    urls = read_url_file(args.file) if args.file else [args.url]

    sources = []
    for url in urls:
        kind, norm, note = classify_url(url)
        if kind == "video":
            say(f"Skipping {url}: that is a single video. Give a channel or playlist URL.")
        elif kind == "unknown":
            say(f"Skipping {url}: {note}.")
        else:
            if note:
                say(f"{url}: {note}.")
            sources.append(Source(url=norm, kind=kind))
    if not sources:
        raise Stop("No channel or playlist URLs to process.")

    output = Path(args.output)
    net = Net()
    ctx = RunContext(args, net)
    taken: set = set()
    say("Listing videos...")
    for src in sources:
        try:
            probe_source(src, ctx.net)
        except Stop:
            raise
        except Exception as e:
            src.failed = short_error(e)
            say(f"  Could not list {src.url}: {src.failed}")
            continue
        if not (src.entries or src.tabs):
            src.failed = "no videos found (check the address)"
            say(f"  {src.url}: {src.failed}")
            continue
        src.folder = choose_folder(src, output, taken)
        count = (len(src.entries) if src.kind == "playlist"
                 else ", ".join(f"{t} {len(v)}" for t, v in src.tabs.items()))
        say(f"  {src.name}: {count}")
        decide_mode(src, args)
    live = [s for s in sources if not s.failed]
    choose_types(live, args)

    runs = []
    for src in live:
        if ctx.stop_all:
            break
        say(f"\n== {src.name} ({src.folder}) ==")
        run = SourceRun(src, ctx)
        runs.append(run)
        run.run()
    if not args.links_only and not ctx.stop_all:
        signin_retry(runs, ctx)
    ctx.net.close()

    say("\nSummary")
    for run in runs:
        combined = {"videos": 0}
        if not args.links_only:
            combined = build_combined(run.folder, args.chunk_words, args.max_sources, args.max_source_words)
        summarise(run, combined)
        if not args.links_only:
            report_combined(combined, args)
        else:
            say(f"  Links: {run.folder.resolve() / 'links.txt'}")
    for src in sources:
        if src.failed:
            say(f"\nNot listed: {src.url} ({src.failed})")


def cmd_merge(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="yt-slurp merge",
                                description="Merge Whisper .txt files and rebuild the combined files.")
    p.add_argument("folder", help="the output folder for one channel or playlist")
    p.add_argument("--delete-wavs", action="store_true", help="delete a video's WAVs once it merges")
    add_combined_args(p)
    args = p.parse_args(argv)
    folder = Path(args.folder.strip('"'))
    if not folder.is_dir():
        raise Stop(f"No folder at {folder}.")
    merge(folder, args)


def cmd_smoke(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="yt-slurp smoke-wav",
                                description="Make test WAVs to check the Whisper app keeps the filenames.")
    p.add_argument("folder", nargs="?", default=str(Path(DEFAULT_OUTPUT) / "smoke-test"))
    args = p.parse_args(argv)
    preflight()
    smoke_wav(Path(args.folder))


def main(argv: list[str] | None = None) -> int:
    setup_console()
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv and argv[0] == "merge":
            cmd_merge(argv[1:])
        elif argv and argv[0] == "smoke-wav":
            cmd_smoke(argv[1:])
        else:
            cmd_run(argv)
    except KeyboardInterrupt:
        say("\nStopped. Progress is saved; run again with --update to continue.")
        return 130
    except Stop as e:
        say(f"\n{e}")
        return 2
    except CookieError as e:
        say(f"\nCould not read browser cookies: {e}\n{COOKIE_HELP}")
        return 2
    except NeedsAnswer as e:
        say(f"\nyt-slurp needs an answer to: {e}\nRun it in a terminal, or pass the matching option.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
