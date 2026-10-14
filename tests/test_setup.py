"""First-run tool setup and the update check, without a network."""

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

import yt_slurp as ys
import yt_slurp_setup as setup


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    return tmp_path


def make_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_version_compare():
    assert setup.newer("v0.2.1", "0.2.0")
    assert setup.newer("v1.0", "0.9.9")
    assert not setup.newer("v0.2.0", "0.2.0")
    assert not setup.newer("v0.1.9", "0.2.0")
    assert not setup.newer("", "0.2.0")


def test_missing_tools_and_use_tools(home):
    assert set(setup.missing_tools()) == {"ffmpeg", "deno"}
    tdir = setup.tools_dir()
    tdir.mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe", "deno"):
        (tdir / setup.exe_name(name)).write_text("x")
    assert setup.missing_tools() == []
    setup.use_tools()
    import os
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tdir)
    assert os.environ["YT_SLURP_DENO"].endswith(setup.exe_name("deno"))


def test_install_tool_extracts_and_checks_checksum(home, monkeypatch):
    archive = make_zip({"ffmpeg-7.1-essentials_build/bin/ffmpeg.exe": "FF",
                        "ffmpeg-7.1-essentials_build/bin/ffprobe.exe": "FP",
                        "ffmpeg-7.1-essentials_build/README.txt": "r"})
    digest = hashlib.sha256(archive).hexdigest()

    def fake_open(url):
        if url == setup.FFMPEG_URL:
            return FakeResponse(archive)
        if url == setup.FFMPEG_URL + ".sha256":
            return FakeResponse(digest.encode())
        raise OSError("not found")

    monkeypatch.setattr(setup, "_open", fake_open)
    seen = []
    setup.install_tool("ffmpeg", lambda d, t: seen.append((d, t)))
    assert (setup.tools_dir() / "ffmpeg.exe").read_text() == "FF"
    assert (setup.tools_dir() / "ffprobe.exe").read_text() == "FP"
    assert seen and seen[-1][0] == len(archive)


def test_install_tool_refuses_a_bad_checksum(home, monkeypatch):
    archive = make_zip({"deno.exe": "D"})

    def fake_open(url):
        if url == setup.DENO_URL:
            return FakeResponse(archive)
        if url.endswith(".sha256sum"):
            return FakeResponse(("0" * 64 + "  deno.zip").encode())
        raise OSError("not found")

    monkeypatch.setattr(setup, "_open", fake_open)
    with pytest.raises(RuntimeError, match="checksum"):
        setup.install_tool("deno")
    assert not (setup.tools_dir() / "deno.exe").exists()


def test_check_for_update(monkeypatch):
    release = {"tag_name": "v9.9.9", "html_url": "https://example/rel",
               "assets": [{"name": "yt-slurp.exe", "browser_download_url": "https://example/yt-slurp.exe"}]}
    monkeypatch.setattr(setup, "_open", lambda url: FakeResponse(json.dumps(release).encode()))
    info = setup.check_for_update(ys.__version__)
    assert info["version"] == "9.9.9" and info["url"].endswith("yt-slurp.exe")
    release["tag_name"] = "v" + ys.__version__
    assert setup.check_for_update(ys.__version__) is None


def test_check_for_update_never_raises(monkeypatch):
    def boom(url):
        raise OSError("offline")
    monkeypatch.setattr(setup, "_open", boom)
    assert setup.check_for_update("0.1.0") is None


def test_apply_update_swaps_the_exe(tmp_path, monkeypatch):
    exe = tmp_path / "yt-slurp.exe"
    exe.write_text("old")
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(setup, "_open", lambda url: FakeResponse(b"new"))
    setup.apply_update("https://example/yt-slurp.exe")
    assert exe.read_text() == "new"
    assert (tmp_path / "yt-slurp.exe.old").read_text() == "old"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    setup.tidy_after_update()
    assert not (tmp_path / "yt-slurp.exe.old").exists()


def test_resource_dir_has_the_icon():
    assert (setup.resource_dir() / "icon.png").exists()
    assert (Path(setup.resource_dir()) / "icon.ico").exists()
