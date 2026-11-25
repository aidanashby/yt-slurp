import pytest

import yt_slurp_engine as engine


@pytest.fixture(autouse=True)
def private_engine(monkeypatch, tmp_path):
    """Tests never see the real yt-dlp folder."""
    monkeypatch.setattr(engine, "engines_dir", lambda: tmp_path / "engine")
    yield
    if engine.active_folder():
        engine.deactivate()
