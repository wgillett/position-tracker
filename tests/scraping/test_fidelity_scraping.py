from pathlib import Path

import pytest
from playwright.sync_api import Page, Route

from position_tracker.firm_config import FirmConfig
from position_tracker.scrapers.fidelity import FidelityScraper
from position_tracker.settings import Settings

_POSITIONS_URL = "https://fidelity.example/positions"

_SELECTORS = {
    "account_row": ".posweb-row-account",
    "account_name": ".posweb-cell-account_primary",
    "account_number": ".posweb-cell-account_secondary",
    "position_row": ".posweb-row-position",
    "symbol": ".posweb-cell-symbol-name_container > span",
    "description": ".posweb-cell-symbol-description",
    "quantity": ".posweb-cell-quantity_value",
    "market_value": ".posweb-cell-current_value",
}

# Approximates Fidelity's real ag-Grid markup: accounts and their holdings are
# flat sibling rows, not nested containers -- an account row is followed by
# that account's position rows until the next account row. Each logical row is
# itself split into two DOM elements sharing a row-id: a pinned "Symbol"
# fragment (symbol/description, or account name/number) and a "center columns"
# fragment (quantity/value) -- neither fragment alone has everything.
_FIXTURE_HTML = """
<div role="grid">
  <div class="ag-row posweb-row-account" row-id="1">
    <div class="posweb-cell-account_primary">INDIVIDUAL - TOD</div>
    <div class="posweb-cell-account_secondary">Z12-345678</div>
  </div>
  <div class="ag-row posweb-row-position posweb-row-core" row-id="2">
    <div class="posweb-cell-symbol-name_container"><span>Cash</span></div>
    <p class="posweb-cell-symbol-description">HELD IN MONEY MARKET</p>
  </div>
  <div class="ag-row posweb-row-position" row-id="3">
    <div class="posweb-cell-symbol-name_container"><span>SPAXX</span></div>
    <p class="posweb-cell-symbol-description">Fidelity Government Money Market Fund</p>
  </div>
  <div class="ag-row posweb-row-position" row-id="3">
    <span class="posweb-cell-quantity_value">1,234.56</span>
    <span class="posweb-cell-current_value">$1,234.56</span>
  </div>
  <div class="ag-row posweb-row-position" row-id="4">
    <div class="posweb-cell-symbol-name_container"><span>FXAIX</span></div>
    <p class="posweb-cell-symbol-description">Fidelity 500 Index Fund</p>
  </div>
  <div class="ag-row posweb-row-position" row-id="4">
    <span class="posweb-cell-quantity_value">10</span>
    <span class="posweb-cell-current_value">$2,000.00</span>
  </div>
  <div class="ag-row posweb-row-position posweb-row-pending_activity" row-id="5">
    <span class="posweb-cell-quantity_value">1</span>
    <span class="posweb-cell-current_value">$42.00</span>
  </div>
  <div class="ag-row posweb-row-account" row-id="6">
    <span class="posweb-cell-account_total_label">Account total</span>
  </div>
  <div class="ag-row posweb-row-account" row-id="7">
    <div class="posweb-cell-account_primary">ROTH IRA</div>
    <div class="posweb-cell-account_secondary">Z98-765432</div>
  </div>
  <div class="ag-row posweb-row-position" row-id="8">
    <div class="posweb-cell-symbol-name_container"><span>FZROX</span></div>
    <p class="posweb-cell-symbol-description">Fidelity ZERO Total Market Index Fund</p>
  </div>
  <div class="ag-row posweb-row-position" row-id="8">
    <span class="posweb-cell-quantity_value">50</span>
    <span class="posweb-cell-current_value">$5,500.00</span>
  </div>
</div>
"""


def _fulfill_positions_page(route: Route) -> None:
    route.fulfill(body=_FIXTURE_HTML, content_type="text/html")


def _config(**overrides: object) -> FirmConfig:
    kwargs: dict[str, object] = {
        "firm": "fidelity",
        "login_url": "https://fidelity.example/login",
        "positions_url": _POSITIONS_URL,
        "selectors": _SELECTORS,
    }
    kwargs.update(overrides)
    return FirmConfig(**kwargs)  # type: ignore[arg-type]


def _settings() -> Settings:
    return Settings(output_dir=Path("/tmp/out"), min_delay_seconds=0, max_delay_seconds=0)


def test_scrape_positions_parses_account_rows_and_holdings(page: Page) -> None:
    page.route(_POSITIONS_URL, _fulfill_positions_page)

    scraper = FidelityScraper(_config(), _settings())
    positions = scraper.scrape_positions(page)

    # The "Cash / HELD IN MONEY MARKET" row is a section-header divider, not a
    # real holding (no quantity/value cells) -- it must be skipped, not scraped.
    # The pending-activity row has quantity/value but no symbol/description --
    # it must be skipped too, not scraped as a bogus holding.
    # The "Account total" row shares the account_row class but has no
    # name/number cells -- it must be skipped too, not treated as a new account.
    assert len(positions) == 3
    assert all(p.ticker != "Cash" for p in positions)
    assert all(p.value != 42.0 for p in positions)

    money_market = positions[0]
    assert money_market.firm == "fidelity"
    assert money_market.account_name == "INDIVIDUAL - TOD"
    assert money_market.account_number == "...5678"
    assert money_market.ticker == "SPAXX"
    assert money_market.asset_name == "Fidelity Government Money Market Fund"
    assert money_market.shares == 1234.56
    assert money_market.value == 1234.56

    second_holding = positions[1]
    assert second_holding.account_name == "INDIVIDUAL - TOD"
    assert second_holding.account_number == "...5678"
    assert second_holding.ticker == "FXAIX"

    roth_holding = positions[2]
    assert roth_holding.account_name == "ROTH IRA"
    assert roth_holding.account_number == "...5432"
    assert roth_holding.ticker == "FZROX"
    assert roth_holding.shares == 50.0
    assert roth_holding.value == 5500.0


def _fulfill_empty_page(route: Route) -> None:
    route.fulfill(body="<html></html>", content_type="text/html")


def test_scrape_positions_raises_when_no_rows_found(page: Page) -> None:
    page.route(_POSITIONS_URL, _fulfill_empty_page)

    scraper = FidelityScraper(_config(), _settings())

    with pytest.raises(ValueError, match="No account or position rows found"):
        scraper.scrape_positions(page)


def _fulfill_position_row_only(route: Route) -> None:
    html = """
    <div role="grid">
      <div class="ag-row posweb-row-position" row-id="1">
        <div class="posweb-cell-symbol-name_container"><span>SPAXX</span></div>
        <p class="posweb-cell-symbol-description">Fidelity Government Money Market Fund</p>
        <span class="posweb-cell-quantity_value">1</span>
        <span class="posweb-cell-current_value">$1.00</span>
      </div>
    </div>
    """
    route.fulfill(body=html, content_type="text/html")


def test_scrape_positions_raises_when_position_row_precedes_account_row(page: Page) -> None:
    page.route(_POSITIONS_URL, _fulfill_position_row_only)

    scraper = FidelityScraper(_config(), _settings())

    with pytest.raises(ValueError, match="before any account row"):
        scraper.scrape_positions(page)
