"""First-run setup and updates for the yt-slurp app.

- Finds ffmpeg, ffprobe and Deno, and downloads them into yt-slurp's own
  tools folder if they are missing (no admin rights, no PATH changes).
- Checks GitHub for a newer release, and replaces the running .exe with it.

Kept separate from the window so it can be tested without a display.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "aidanashby/yt-slurp"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
EXE_ASSET = "yt-slurp.exe"

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
TIMEOUT_S = 30
USER_AGENT = "yt-slurp"


def frozen() -> bool:
    """True when running as the bundled .exe."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Where the icon and other bundled files are."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "yt-slurp"


def tools_dir() -> Path:
    return data_dir() / "tools"


def exe_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


# =============================================================================
# Finding the tools
# =============================================================================

def find_tool(name: str) -> str | None:
    """A tool from yt-slurp's own folder, the PATH, or a usual install place."""
    candidates = [tools_dir() / exe_name(name)]
    on_path = shutil.which(name)
    if on_path:
        candidates.insert(1, Path(on_path))
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates += [
            Path("C:/ffmpeg/bin") / exe_name(name),
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "ffmpeg" / "bin" / exe_name(name),
            local / "Microsoft" / "WinGet" / "Links" / exe_name(name),
            Path.home() / ".deno" / "bin" / exe_name(name),
        ]
    for c in candidates:
        if c and c.is_file():
            return str(c)
    return None


def missing_tools() -> list[str]:
    """Which of ffmpeg (with ffprobe) and Deno are missing. Takes milliseconds."""
    missing = []
    if not (find_tool("ffmpeg") and find_tool("ffprobe")):
        missing.append("ffmpeg")
    if not find_tool("deno"):
        missing.append("deno")
    return missing


def use_tools() -> None:
    """Make the tools findable by yt-slurp and yt-dlp for this process."""
    dirs = []
    for name in ("ffmpeg", "ffprobe", "deno"):
        path = find_tool(name)
        if path:
            d = str(Path(path).parent)
            if d not in dirs:
                dirs.append(d)
            if name == "deno":
                os.environ["YT_SLURP_DENO"] = path
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(dirs + [current]) if dirs else current


# =============================================================================
# Downloading the tools
# =============================================================================

def _open(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=TIMEOUT_S)


def download(url: str, dest: Path, progress=None) -> None:
    """Download url to dest, reporting progress(done_bytes, total_bytes)."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _open(url) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    os.replace(tmp, dest)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def published_checksum(url: str) -> str | None:
    """The SHA-256 the publisher lists next to a download, if there is one."""
    for suffix in (".sha256", ".sha256sum"):
        try:
            with _open(url + suffix) as r:
                text = r.read(4096).decode("ascii", "replace")
        except Exception:
            continue
        m = re.search(r"\b[0-9a-fA-F]{64}\b", text)
        if m:
            return m.group(0).lower()
    return None


def extract_member(zip_path: Path, wanted: str, dest: Path) -> None:
    """Copy the first file called `wanted` (at any depth) out of a zip."""
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if not info.is_dir() and Path(info.filename).name.lower() == wanted.lower():
                with z.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                return
    raise RuntimeError(f"{wanted} was not found in the download")


def install_tool(name: str, progress=None) -> None:
    """Download ffmpeg (with ffprobe) or Deno into yt-slurp's tools folder,
    checking the publisher's SHA-256 checksum when one is published."""
    url = {"ffmpeg": FFMPEG_URL, "deno": DENO_URL}[name]
    tools_dir().mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / f"{name}.zip"
        download(url, zip_path, progress)
        expected = published_checksum(url)
        if expected and sha256(zip_path) != expected:
            raise RuntimeError(f"The {name} download did not match its published checksum, so it was not used.")
        members = ["ffmpeg.exe", "ffprobe.exe"] if name == "ffmpeg" else ["deno.exe"]
        for m in members:
            extract_member(zip_path, m, tools_dir() / m)


# =============================================================================
# Updates
# =============================================================================

def version_tuple(v: str) -> tuple:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def newer(latest: str, current: str) -> bool:
    return version_tuple(latest) > version_tuple(current)


def check_for_update(current: str) -> dict | None:
    """The latest release if it is newer than current, else None. Never raises."""
    try:
        with _open(RELEASES_API) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    tag = data.get("tag_name") or ""
    if not newer(tag, current):
        return None
    asset = next((a for a in data.get("assets") or [] if a.get("name") == EXE_ASSET), None)
    return {"version": tag.lstrip("v"), "url": asset.get("browser_download_url") if asset else None,
            "page": data.get("html_url") or RELEASES_PAGE, "notes": data.get("body") or ""}


def apply_update(url: str, progress=None) -> Path:
    """Download the new .exe and swap it in. Windows allows renaming a running
    .exe, so the old one is moved aside and removed on the next start."""
    exe = Path(sys.executable)
    new = exe.with_name(exe.name + ".new")
    old = exe.with_name(exe.name + ".old")
    download(url, new, progress)
    if old.exists():
        old.unlink()
    os.replace(exe, old)
    os.replace(new, exe)
    return exe


def restart(exe: Path) -> None:
    subprocess.Popen([str(exe)], close_fds=True)


def tidy_after_update() -> None:
    """Remove the previous .exe left by an update."""
    if frozen():
        old = Path(sys.executable).with_name(Path(sys.executable).name + ".old")
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass  # still in use; try next time
