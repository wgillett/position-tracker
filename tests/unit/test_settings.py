from pathlib import Path

import pytest

from position_tracker.settings import load_settings


def test_load_settings_requires_output_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("POSITION_TRACKER_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # avoid picking up the repo's own .env file
    with pytest.raises(SystemExit):
        load_settings()


def test_load_settings_reads_output_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("POSITION_TRACKER_OUTPUT_DIR", "/tmp/positions")
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    assert str(settings.output_dir) == "/tmp/positions"
