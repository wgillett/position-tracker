from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables.

    Values here are non-sensitive (paths, delays). Credentials and session
    tokens are never part of Settings — they live in the OS keychain.
    """

    model_config = SettingsConfigDict(env_prefix="POSITION_TRACKER_", env_file=".env")

    output_dir: Path = Field(
        ...,
        description=(
            "Directory where output CSVs are written. Set via POSITION_TRACKER_OUTPUT_DIR."
        ),
    )
    config_dir: Path = Field(
        default=Path(__file__).resolve().parent.parent.parent / "config",
        description="Directory containing per-firm YAML config files.",
    )
    session_ttl_seconds: int = Field(
        default=3600,
        description="Maximum age of a cached session before re-login is required.",
    )
    min_delay_seconds: float = Field(default=2.0, description="Minimum delay between page hits.")
    max_delay_seconds: float = Field(default=5.0, description="Maximum delay between page hits.")


def load_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:
        raise SystemExit(
            "Missing configuration: output_dir is not set.\n"
            "Set it via the POSITION_TRACKER_OUTPUT_DIR environment variable, e.g.:\n"
            "  export POSITION_TRACKER_OUTPUT_DIR=~/finances/positions\n"
            f"\nDetails: {exc}"
        ) from exc
