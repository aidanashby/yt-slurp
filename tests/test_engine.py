"""Updating yt-dlp and repairing a run, without a network."""

import hashlib
import io
import json
import sys
import time
import zipfile

import pytest

import yt_slurp as ys
import yt_slurp_engine as engine
import yt_slurp_setup as setup
from test_pipeline import VIDEOS, fake  # noqa: F401
from test_setup import FakeResponse, make_zip

NEW = "2099.01.02"


def fake_package(version=NEW):
    return {"yt_dlp/__init__.py": "class YoutubeDL: pass", "yt_dlp/version.py": f"__version__ = '{version}'",
            "yt_dlp_ejs/__init__.py": "", "other/evil.py": "x"}


@pytest.fixture
def pypi(monkeypatch):
    """PyPI offering one new yt-dlp. Change data['files'] to change the wheel."""
    data = {"files": fake_package(), "age": 72 * 3600, "sha": None}

    def wheel(name):
        raw = make_zip(data["files"])
        up = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - data["age"]))
        return {"packagetype": "bdist_wheel", "filename": f"{name}-py3-none-any.whl", "url": f"https://x/{name}",
                "upload_time_iso_8601": up, "requires_python": ">=3.10",
                "digests": {"sha256": data["sha"] or hashlib.sha256(raw).hexdigest()}}

    def fake_open(url):
        if url.startswith("https://x/"):
            return FakeResponse(make_zip(data["files"]))
        if "yt-dlp-ejs" in url:
            body = {"urls": [wheel("ejs")]}
        elif NEW in url:
            body = {"info": {"requires_dist": ["requests; extra == 'default'", "yt-dlp-ejs==0.8.0; extra == 'default'"]}}
        else:
            body = {"releases": {"2020.1.1": [], NEW: [wheel("yt_dlp")], "2100.1.1.dev0": [wheel("dev")]}}
        return FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr(setup, "_open", fake_open)
    monkeypatch.setattr(engine, "run_check", lambda folder: "")
    # make_zip stamps the time, so keep it still
    monkeypatch.setattr(zipfile.time, "localtime", lambda *a: time.struct_time((2026, 1, 1, 0, 0, 0, 0, 1, 0)))
    return data


def test_hotfix_versions_compare():
    assert engine.full_version("2026.11.23.1") > engine.full_version("2026.11.23")


def test_update_installs_and_is_used(pypi):
    assert engine.prepare() == NEW
    assert not (engine.engines_dir() / NEW / "other").exists()
    assert sys.modules["yt_dlp"].__file__.startswith(str(engine.engines_dir()))
    with pytest.raises(ModuleNotFoundError):  # nothing from the built-in copy
        import yt_dlp.extractor  # noqa: F401
    assert not (engine.engines_dir() / "update.lock").exists()


def test_bad_checksum_failed_test_and_unsafe_path_keep_the_old_copy(pypi, monkeypatch):
    for change in ("sha", "check", "path"):
        pypi["sha"] = "0" * 64 if change == "sha" else None
        pypi["files"] = {**fake_package(), **({"yt_dlp/../../evil.py": "x"} if change == "path" else {})}
        monkeypatch.setattr(engine, "run_check", lambda f, c=change: "broken" if c == "check" else "")
        with pytest.raises(RuntimeError):
            engine.update("2026.1.1")
        assert engine.read_state() == {}
    assert engine.prepare() == engine.builtin_version()


def test_new_release_waits_unless_repairing(pypi):
    pypi["age"] = 3600
    assert engine.update("2026.1.1") is None
    assert engine.update("2026.1.1", force=True) == NEW


def test_offline_carries_on_and_checks_daily(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "newest_release", lambda age: calls.append(age) or (_ for _ in ()).throw(OSError("off")))
    assert engine.prepare() and engine.prepare()
    assert len(calls) == 1


def test_broken_current_falls_back(pypi):
    engine.update("2026.1.1")
    (engine.engines_dir() / NEW / "yt_dlp" / "__init__.py").write_text("raise RuntimeError")
    assert engine.activate() == engine.builtin_version()


def test_the_installed_ytdlp_passes_the_real_check(tmp_path):
    import yt_dlp
    from pathlib import Path
    assert engine.run_check(Path(yt_dlp.__file__).parent.parent) == ""
    assert engine.run_check(tmp_path / "nothing")


# ----- repairing a run -----

class FailingNet(ys.Net):
    def _pause(self):
        pass


def js_failure(net):
    net.logger.warning("[youtube] n challenge solving failed: JavaScript runtime")
    raise RuntimeError("Requested format is not available")


@pytest.fixture
def deno(monkeypatch):
    monkeypatch.setattr(setup, "find_tool", lambda name: "deno")


def test_repair_then_retry(monkeypatch, deno):
    net, tries = FailingNet(), []
    monkeypatch.setattr(engine, "repair", lambda *a: NEW)
    assert net.call("x", lambda: tries.append(1) or (js_failure(net) if len(tries) == 1 else "ok")) == "ok"


def test_help_names_the_real_cause(monkeypatch, deno):
    for outcome, words in ((lambda *a: None, "no newer version"),
                           (lambda *a: (_ for _ in ()).throw(OSError("offline")), "could not update")):
        net = FailingNet()
        monkeypatch.setattr(engine, "repair", outcome)
        with pytest.raises(ys.NeedsHelp) as e:
            net.call("x", lambda: js_failure(net))
        assert words in str(e.value) and "challenge" in e.value.details
        assert "pip" not in str(e.value) and "winget" not in str(e.value)


def test_missing_deno_is_installed(monkeypatch):
    net, got = FailingNet(), []
    monkeypatch.setattr(setup, "find_tool", lambda name: None)
    monkeypatch.setattr(ys, "install_tools", got.extend)
    monkeypatch.setattr(engine, "repair", lambda *a: None)
    with pytest.raises(ys.NeedsHelp):
        net.call("x", lambda: js_failure(net))
    assert got == ["deno"]


def test_private_video_is_not_mistaken_for_a_challenge_failure(monkeypatch):
    net = FailingNet()

    def private():
        net.logger.warning("n challenge solving failed")
        raise RuntimeError("Private video")
    with pytest.raises(RuntimeError, match="Private"):
        net.call("x", private)


# ----- single videos -----

def test_single_video(fake):  # noqa: F811
    url = "https://www.youtube.com/watch?v=capt0000001"
    assert ys.main([url, "--no-transcripts", "--min-minutes", "60"]) == 0
    folder = fake / "output" / "Test Channel"
    assert len(list((folder / "transcripts").iterdir())) == 1
    assert not (folder / "links.txt").exists()
    short = "https://youtu.be/short000005"
    assert ys.main([short, "--no-wavs"]) == 0 and ys.main([url]) == 0  # second video, then a repeat: no questions
    assert set(ys.Manifest(folder / "manifest.csv").rows) == {"capt0000001", "short000005"}


# ----- damaged state -----

@pytest.mark.parametrize("state", ['{"checked": "abc"}', '{"checked": [1]}', '{"checked": NaN}', '{"current": 5}',
                                   '{"current": ["x"]}', '{"current": "2099.1.1"}', '{"current": "../x"}',
                                   '{"current": "' + "9" * 5000 + '"}', pytest.param("[" * 100000, id="nested")])
def test_damaged_state_still_updates(pypi, state):
    engine.engines_dir().mkdir(parents=True)
    (engine.engines_dir() / "engine.json").write_text(state)
    assert engine.prepare() == NEW


def test_leftovers_are_cleared(pypi):
    (engine.engines_dir() / "tmpabc").mkdir(parents=True)
    assert engine.update("2026.1.1") == NEW
    assert not (engine.engines_dir() / "tmpabc").exists()


def test_a_replaced_lock_is_left_alone(pypi, monkeypatch):
    lock = engine.engines_dir() / "update.lock"
    monkeypatch.setattr(engine, "run_check", lambda f: lock.write_text("other") and "")
    assert engine.update("2026.1.1") == NEW
    assert lock.read_text() == "other"
