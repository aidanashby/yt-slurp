"""Keeps yt-dlp current without a new yt-slurp release.

YouTube changes often break older yt-dlp versions, and the copy built into the
.exe cannot be changed. Newer versions are downloaded from PyPI into yt-slurp's
own folder, tested in a separate process, and used in place of the built-in
copy. If a newer one does not work, the previous one stays in use.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

import yt_slurp_setup as setup

PYPI = "https://pypi.org/pypi"
PACKAGES = ("yt_dlp", "yt_dlp_ejs")
CHECK_EVERY_S = 24 * 3600
MIN_AGE_S = 48 * 3600  # routine updates skip brand-new releases; repairs do not
CHECK_TIMEOUT_S = 120
LOCK_STALE_S = 15 * 60
CHECK_FLAG = "--check-engine"


def engines_dir() -> Path:
    return setup.data_dir() / "engine"


def full_version(v: str) -> tuple:
    """Every part of a version, so the hotfix 2026.11.23.1 beats 2026.11.23."""
    return tuple(int(n) for n in re.findall(r"\d+", v or ""))


def builtin_version() -> str:
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return ""


def read_state() -> dict:
    try:
        state = json.loads((engines_dir() / "engine.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    if not isinstance(state, dict):
        return {}
    clean = {k: v for k in ("current", "previous")
             if isinstance(v := state.get(k), str) and re.fullmatch(r"\d{1,8}(\.\d{1,8}){1,5}", v)}
    checked = state.get("checked")
    if isinstance(checked, (int, float)) and 0 <= checked < 1e12:  # not NaN either
        clean["checked"] = checked
    return clean


def write_state(state: dict) -> None:
    engines_dir().mkdir(parents=True, exist_ok=True)
    tmp = engines_dir() / f"engine.json.{os.getpid()}"
    tmp.write_text(json.dumps(state), encoding="utf-8")
    _replace(tmp, engines_dir() / "engine.json")


def _replace(src: Path, dest: Path) -> None:
    """os.replace, retried because antivirus can hold new files briefly."""
    for wait in (0.2, 0.5, 1, 2, None):
        try:
            os.replace(src, dest)
            return
        except PermissionError:
            if wait is None:
                raise
            time.sleep(wait)


# =============================================================================
# Using a downloaded version
# =============================================================================

class EngineFinder(importlib.abc.MetaPathFinder):
    """Loads yt-dlp from one folder only, ahead of the copy built into the .exe."""

    def __init__(self, folder: Path):
        self.folder = str(folder)

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] not in PACKAGES:
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path if "." in name else [self.folder])
        if spec is None:  # never mix in modules from the built-in copy
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return spec


def deactivate() -> None:
    """Forget any loaded yt-dlp, so the next import loads afresh."""
    sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, EngineFinder)
                        and type(f).__module__ != "yt_dlp.plugins"]
    for name in [n for n in sys.modules if n.split(".")[0] in PACKAGES]:
        del sys.modules[name]
    importlib.invalidate_caches()


def use_folder(folder: Path) -> None:
    deactivate()
    sys.meta_path.insert(0, EngineFinder(folder))


def active_folder() -> str | None:
    return next((f.folder for f in sys.meta_path if isinstance(f, EngineFinder)), None)


def activate() -> str:
    """Use the newest yt-dlp that imports, and return its version."""
    if active_folder():
        from yt_dlp.version import __version__
        return __version__
    state = read_state()
    for version in (state.get("current"), state.get("previous")):
        if not version:
            continue
        folder = engines_dir() / version
        if full_version(version) <= full_version(builtin_version()) or not (folder / "yt_dlp").is_dir():
            continue
        try:
            use_folder(folder)
            from yt_dlp import YoutubeDL  # noqa: F401
            from yt_dlp.version import __version__
            return __version__
        except Exception:
            deactivate()
    from yt_dlp.version import __version__
    return __version__


# =============================================================================
# Testing a downloaded version
# =============================================================================

def check_engine(folder: str, report: str) -> int:
    """Run in a separate process: load everything yt-slurp needs from a folder.
    Writes any problem to the report file, since the .exe has no console."""
    try:
        import pkgutil
        use_folder(Path(folder))
        from yt_dlp import YoutubeDL
        for pkg in ("networking", "downloader", "postprocessor", "extractor.youtube"):
            parent = importlib.import_module(f"yt_dlp.{pkg}")
            for m in pkgutil.walk_packages(parent.__path__, parent.__name__ + "."):
                try:
                    importlib.import_module(m.name)
                except ImportError as e:
                    # Optional add-ons (curl_cffi and the like) may be absent
                    missing = (getattr(e, "name", "") or "").split(".")[0]
                    if missing in sys.stdlib_module_names or missing in PACKAGES:
                        raise
        import yt_dlp_ejs.yt.solver as solver
        if not (solver.core() and solver.lib()):
            raise RuntimeError("the YouTube solver scripts are empty")
        with YoutubeDL({"quiet": True}) as y:
            y.get_info_extractor("Youtube")
        return 0
    except BaseException as e:
        try:
            Path(report).write_text(f"{type(e).__name__}: {e}", encoding="utf-8")
        except OSError:
            pass
        return 1


def run_check(folder: Path) -> str:
    """Test a version in a child process. Returns the problem, or ''."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.txt"
        if setup.frozen():
            cmd = [sys.executable]
        else:
            cmd = [sys.executable, str(Path(__file__).with_name("yt_slurp_app.py"))]
        try:
            r = subprocess.run([*cmd, CHECK_FLAG, str(folder), str(report)], timeout=CHECK_TIMEOUT_S,
                               stdin=subprocess.DEVNULL, capture_output=True, env=setup.child_env(),
                               **setup.NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as e:
            return str(e)
        if r.returncode == 0:
            return ""
        return report.read_text(encoding="utf-8") if report.exists() else f"exit code {r.returncode}"


# =============================================================================
# Downloading
# =============================================================================

def _json(url: str) -> dict:
    with setup._open(url) as r:
        return json.loads(r.read().decode("utf-8"))


def _python_ok(requires: str | None) -> bool:
    for op, v in re.findall(r"(>=|<=|<|>|==|!=|~=)\s*([\d.]+)", requires or ""):
        have, want = sys.version_info[:3], (full_version(v) + (0, 0))[:3]
        if op in (">=", "~=") and have < want or op == ">" and have <= want:
            return False
        if op == "<" and have >= want or op == "<=" and have > want:
            return False
    return True


def _wheel(files: list) -> dict | None:
    return next((f for f in files if f.get("packagetype") == "bdist_wheel"
                 and str(f.get("filename", "")).endswith("-none-any.whl") and not f.get("yanked")
                 and _python_ok(f.get("requires_python"))), None)


def newest_release(min_age_s: float = 0) -> tuple[str, dict] | None:
    """(version, wheel) for the newest stable yt-dlp at least min_age_s old."""
    found = []
    for version, files in (_json(f"{PYPI}/yt-dlp/json").get("releases") or {}).items():
        wheel = _wheel(files) if re.fullmatch(r"\d+(\.\d+)+", version) else None
        if not wheel:
            continue
        up = datetime.datetime.fromisoformat(wheel["upload_time_iso_8601"].replace("Z", "+00:00"))
        if time.time() - up.timestamp() >= min_age_s:
            found.append((full_version(version), version, wheel))
    if not found:
        return None
    _, version, wheel = max(found, key=lambda f: f[0])
    return version, wheel


def _fetch_wheel(wheel: dict, dest: Path, work: Path, progress=None) -> None:
    path = work / "package.whl"
    setup.download(wheel["url"], path, progress)
    if hashlib.sha256(path.read_bytes()).hexdigest() != wheel["digests"]["sha256"]:
        raise RuntimeError("The yt-dlp download did not match its published checksum, so it was not used.")
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            parts = PurePosixPath(info.filename).parts
            if not parts or parts[0] not in PACKAGES:
                continue
            if ".." in parts or "\\" in info.filename or ":" in info.filename:
                raise RuntimeError("The yt-dlp download contains an unsafe file path, so it was not used.")
            z.extract(info, dest)


def _lock() -> Path | None:
    path = engines_dir() / "update.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            with open(path, "x", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return path
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime < LOCK_STALE_S:
                    return None
                path.unlink()
            except OSError:
                return None
    return None


def update(current: str, say=lambda msg: None, progress=None, force: bool = False) -> str | None:
    """Download, test and select a newer yt-dlp. Returns its version, or None
    if there is none newer. Raises on network, disk or test failures."""
    found = newest_release(0 if force else MIN_AGE_S)
    if not found or full_version(found[0]) <= full_version(current):
        return None
    version, wheel = found
    lock = _lock()
    if not lock:
        raise RuntimeError("another copy of yt-slurp is updating yt-dlp")
    try:
        say(f"Updating yt-dlp to {version}...")
        requires = (_json(f"{PYPI}/yt-dlp/{version}/json").get("info") or {}).get("requires_dist") or []
        pin = next((m.group(1) for m in (re.match(r"yt-dlp-ejs\s*==\s*([\d.]+)", r) for r in requires) if m), None)
        if not pin:
            raise RuntimeError("the new yt-dlp does not name its solver version")
        ejs = _wheel(_json(f"{PYPI}/yt-dlp-ejs/{pin}/json").get("urls") or [])
        if not ejs:
            raise RuntimeError("the new yt-dlp's solver cannot be used here")
        # Staged beside its destination so the final move is a rename
        with tempfile.TemporaryDirectory(dir=engines_dir(), ignore_cleanup_errors=True) as tmp:
            stage = Path(tmp) / "stage"
            stage.mkdir()
            _fetch_wheel(wheel, stage, Path(tmp), progress)
            _fetch_wheel(ejs, stage, Path(tmp))
            problem = run_check(stage)
            if problem:
                raise RuntimeError(f"yt-dlp {version} did not pass its test: {problem}")
            dest = engines_dir() / version
            if dest.exists():
                shutil.rmtree(dest)
            _replace(stage, dest)
        state = read_state()
        if state.get("current") != version:
            state["previous"] = state.get("current")
        state["current"] = version
        write_state(state)
        _tidy(state)
        return version
    finally:
        try:
            if lock.read_text(encoding="utf-8") == str(os.getpid()):  # not one that replaced ours as stale
                lock.unlink()
        except OSError:
            pass


def _tidy(state: dict) -> None:
    keep = {state.get("current"), state.get("previous")}
    for d in engines_dir().iterdir():
        # tmp...: left by an update that was cut short
        if d.is_dir() and d.name not in keep and re.fullmatch(r"\d+(\.\d+)+|tmp\w+", d.name):
            shutil.rmtree(d, ignore_errors=True)


def prepare(say=lambda msg: None, progress=None) -> str:
    """Before a run: check for a newer yt-dlp at most daily, then load the
    newest that works. Being offline is no reason to stop."""
    state = read_state()
    if abs(time.time() - state.get("checked", 0)) > CHECK_EVERY_S:
        try:
            if update(activate(), say, progress):
                deactivate()
        except Exception as e:
            say(f"Could not update yt-dlp, so using the one already here ({str(e)[:200]}).")
        try:
            state = read_state()
            state["checked"] = time.time()
            write_state(state)
        except OSError:
            pass
    return activate()


def repair(current: str, say=lambda msg: None, progress=None) -> str | None:
    """YouTube cannot be read: switch to the very newest yt-dlp, if it is newer."""
    version = update(current, say, progress, force=True)
    if version:
        deactivate()
        activate()
    return version
