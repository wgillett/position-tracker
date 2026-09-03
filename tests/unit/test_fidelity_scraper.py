from pathlib import Path

import pytest

from position_tracker.firm_config import FirmConfig
from position_tracker.scrapers.fidelity import FidelityScraper, _parse_number
from position_tracker.settings import Settings


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,234.56", 1234.56),
        ("$12,000.00", 12000.0),
        ("-42.5", -42.5),
        ("7", 7.0),
    ],
)
def test_parse_number(text: str, expected: float) -> None:
    assert _parse_number(text) == expected


def test_parse_number_rejects_empty() -> None:
    with pytest.raises(ValueError, match="Could not parse"):
        _parse_number("N/A")


def _scraper(**config_kwargs: object) -> FidelityScraper:
    config = FirmConfig(firm="fidelity", login_url="https://example.com/login", **config_kwargs)  # type: ignore[arg-type]
    settings = Settings(output_dir=Path("/tmp/out"))
    return FidelityScraper(config, settings)


def test_selector_missing_raises_informative_error() -> None:
    scraper = _scraper(selectors={})
    with pytest.raises(ValueError, match="missing selector 'account_row'"):
        scraper._selector("account_row")


def test_positions_url_missing_raises_informative_error() -> None:
    scraper = _scraper(positions_url=None)
    with pytest.raises(ValueError, match="missing 'positions_url'"):
        scraper._positions_url()
