from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class FirmConfig(BaseModel):
    """Non-sensitive, firm-specific settings loaded from config/<firm>.yaml.

    Contains things like base URLs and CSS selectors — never credentials or
    account data. Selectors are kept in config (rather than hardcoded) so
    they can be tuned after inspecting the real, logged-in page without a
    code change.
    """

    firm: str
    login_url: str
    positions_url: str | None = None
    selectors: dict[str, str] = Field(default_factory=dict)


def load_firm_config(firm: str, config_dir: Path) -> FirmConfig:
    config_path = config_dir / f"{firm}.yaml"
    if not config_path.exists():
        raise SystemExit(
            f"No config found for firm '{firm}' (expected {config_path}).\n"
            f"Supported firms have a config/<firm>.yaml file."
        )
    with config_path.open() as f:
        raw = yaml.safe_load(f)
    return FirmConfig.model_validate(raw)
