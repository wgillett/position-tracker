from pathlib import Path

import pytest

from position_tracker.firm_config import FirmConfig
from position_tracker.scrapers.vanguard import VanguardScraper
from position_tracker.settings import Settings


def _scraper(**config_kwargs: object) -> VanguardScraper:
    config = FirmConfig(firm="vanguard", login_url="https://example.com/login", **config_kwargs)  # type: ignore[arg-type]
    settings = Settings(output_dir=Path("/tmp/out"))
    return VanguardScraper(config, settings)


def test_selector_missing_raises_informative_error() -> None:
    scraper = _scraper(selectors={})
    with pytest.raises(ValueError, match="missing selector 'account_container'"):
        scraper._selector("account_container")


def test_positions_url_missing_raises_informative_error() -> None:
    scraper = _scraper(positions_url=None)
    with pytest.raises(ValueError, match="missing 'positions_url'"):
        scraper._positions_url()


@pytest.mark.parametrize(
    ("heading", "expected_name", "expected_number"),
    [
        (
            " Walter Gillett — Traditional IRA Brokerage Account — 12345678* ",
            "Walter Gillett — Traditional IRA Brokerage Account",
            "...5678",
        ),
        (
            "Walter Gillett — Rollover IRA Brokerage Account — 87654321*",
            "Walter Gillett — Rollover IRA Brokerage Account",
            "...4321",
        ),
    ],
)
def test_parse_heading(heading: str, expected_name: str, expected_number: str) -> None:
    scraper = _scraper()
    parsed = scraper._parse_heading(heading)
    assert parsed is not None
    account_name, account_number = parsed
    assert account_name == expected_name
    assert account_number == expected_number


def test_parse_heading_returns_none_for_numberless_account() -> None:
    """A heading with no trailing number segment (just "Name — Account Type")
    is a defunct/duplicate account entry with no real holdings -- callers
    should skip it, not treat it as an error."""
    scraper = _scraper()
    assert scraper._parse_heading("Sharon E. Gillett — SEP-IRA") is None


def test_parse_heading_rejects_unexpected_format() -> None:
    scraper = _scraper()
    with pytest.raises(ValueError, match="Could not parse account name/number"):
        scraper._parse_heading("Not a real heading")


def test_parse_heading_rejects_missing_digits() -> None:
    scraper = _scraper()
    with pytest.raises(ValueError, match="Could not find an account number"):
        scraper._parse_heading("Walter Gillett — Traditional IRA Brokerage Account — *")
