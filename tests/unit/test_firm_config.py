from pathlib import Path

import pytest

from position_tracker.firm_config import load_firm_config


def test_load_firm_config_reads_yaml(tmp_path: Path) -> None:
    (tmp_path / "fidelity.yaml").write_text(
        "firm: fidelity\nlogin_url: https://example.com/login\n"
    )

    config = load_firm_config("fidelity", tmp_path)

    assert config.firm == "fidelity"
    assert config.login_url == "https://example.com/login"


def test_load_firm_config_missing_file_exits(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        load_firm_config("unknown", tmp_path)
