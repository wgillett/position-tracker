from pathlib import Path

import pytest
from playwright.sync_api import Page, Route

from position_tracker.firm_config import FirmConfig
from position_tracker.scrapers.vanguard import VanguardScraper
from position_tracker.settings import Settings

_POSITIONS_URL = "https://vanguard.example/investments/"

_SELECTORS = {
    "account_container": "[data-testid^='account-id:']",
    "account_heading": ".c11n-accordion__heading",
    "expand_accounts_button": "[data-testid='expand-accounts']",
    "holdings_table": "table",
    "holding_row": "tbody tr:has(th[scope='row'])",
    "ticker": ".holding-ticker",
    "description": ".holding-name__text",
    "quantity_column_header": "thead th[data-testid='quantity-column']",
    "balance_column_header": "thead th[data-testid='current-balance-column']",
    "settlement_fund_section": "[data-testid='settlement-fund-section']",
    "settlement_fund_name": "[data-testid='settlementFundName']",
    "settlement_fund_balance": "[data-testid='settlement-fund-balance']",
}

# Approximates Vanguard's real Holdings page markup: each account is its own
# accordion (data-testid="account-id:<id>") with its own <table>. The header
# row's column order deliberately doesn't put quantity/balance in the same
# position, to prove VanguardScraper resolves column position dynamically
# (from the header) rather than assuming a fixed index. Category-header rows
# (e.g. "Mutual funds") share the <tr> shape of real holding rows but use
# scope="colgroup" on their lone cell instead of scope="row".
_FIXTURE_HTML = """
<button data-testid="expand-accounts">Expand accounts</button>

<div data-testid="account-id:111111111111111">
  <span class="c11n-accordion__heading">
    Test Person — Traditional IRA Brokerage Account — 12345678*
  </span>
  <table>
    <thead>
      <tr>
        <th data-testid="symbol-column">Symbol</th>
        <th data-testid="price-column">Price</th>
        <th data-testid="quantity-column">Quantity</th>
        <th>Unrealized gain/loss</th>
        <th data-testid="current-balance-column">Current balance</th>
      </tr>
    </thead>
    <tbody>
      <tr><th scope="colgroup" colspan="5">Mutual funds</th></tr>
      <tr>
        <th scope="row">
          <span class="holding-ticker">VFIAX</span>
          <span class="holding-name__text">VANGUARD 500 INDEX ADMIRAL CL</span>
        </th>
        <td>$450.00</td>
        <td>10.123</td>
        <td>$50.00</td>
        <td>$4,555.35</td>
      </tr>
    </tbody>
  </table>
</div>

<div data-testid="settlement-fund-section">
  <a data-testid="settlementFundName"
     href="/en/investor/portfolio/investments/holding-details/111111111111111?positionId=1">
    Vanguard Federal Money Market Fund
  </a>
  <p data-testid="settlement-fund-balance">$0.86</p>
</div>

<div data-testid="account-id:222222222222222">
  <span class="c11n-accordion__heading">
    Test Person — Rollover IRA Brokerage Account — 87654321*
  </span>
  <table>
    <thead>
      <tr>
        <th data-testid="symbol-column">Symbol</th>
        <th data-testid="price-column">Price</th>
        <th data-testid="quantity-column">Quantity</th>
        <th>Unrealized gain/loss</th>
        <th data-testid="current-balance-column">Current balance</th>
      </tr>
    </thead>
    <tbody>
      <tr><th scope="colgroup" colspan="5">Stocks</th></tr>
      <tr>
        <th scope="row">
          <span class="holding-ticker">AAPL</span>
          <span class="holding-name__text">APPLE INC</span>
        </th>
        <td>$180.00</td>
        <td>5</td>
        <td>$0.00</td>
        <td>$900.00</td>
      </tr>
    </tbody>
  </table>
</div>

<div data-testid="account-id:333333333333333">
  <span class="c11n-accordion__heading">
    Test Person — Cash Management Account — 55555555*
  </span>
</div>

<div data-testid="account-id:444444444444444">
  <span class="c11n-accordion__heading">
    Test Person — SEP-IRA
  </span>
</div>

<div data-testid="settlement-fund-section">
  <a data-testid="settlementFundName"
     href="/en/investor/portfolio/investments/holding-details/444444444444444?positionId=2">
    Vanguard Federal Money Market Fund
  </a>
  <p data-testid="settlement-fund-balance">$0.00</p>
</div>
"""


def _fulfill_positions_page(route: Route) -> None:
    route.fulfill(body=_FIXTURE_HTML, content_type="text/html; charset=utf-8")


def _config(**overrides: object) -> FirmConfig:
    kwargs: dict[str, object] = {
        "firm": "vanguard",
        "login_url": "https://vanguard.example/login",
        "positions_url": _POSITIONS_URL,
        "selectors": _SELECTORS,
    }
    kwargs.update(overrides)
    return FirmConfig(**kwargs)  # type: ignore[arg-type]


def _settings() -> Settings:
    return Settings(output_dir=Path("/tmp/out"), min_delay_seconds=0, max_delay_seconds=0)


def test_scrape_positions_parses_accounts_and_holdings(page: Page) -> None:
    page.route(_POSITIONS_URL, _fulfill_positions_page)

    scraper = VanguardScraper(_config(), _settings())
    positions = scraper.scrape_positions(page)

    # The third account (Cash Management) has no holdings table, and the
    # fourth (numberless "SEP-IRA") is a defunct/duplicate entry -- both must
    # be skipped entirely, along with the settlement fund card that
    # references the numberless account, rather than raising or producing a
    # bogus position.
    assert len(positions) == 3

    ira_holding = positions[0]
    assert ira_holding.firm == "vanguard"
    assert ira_holding.account_name == "Test Person — Traditional IRA Brokerage Account"
    assert ira_holding.account_number == "...5678"
    assert ira_holding.ticker == "VFIAX"
    assert ira_holding.asset_name == "VANGUARD 500 INDEX ADMIRAL CL"
    assert ira_holding.shares == 10.123
    assert ira_holding.value == 4555.35

    rollover_holding = positions[1]
    assert rollover_holding.account_name == "Test Person — Rollover IRA Brokerage Account"
    assert rollover_holding.account_number == "...4321"
    assert rollover_holding.ticker == "AAPL"
    assert rollover_holding.shares == 5.0
    assert rollover_holding.value == 900.0

    # The settlement fund card is matched to its account (Traditional IRA) via
    # the account id embedded in its link, not DOM nesting.
    settlement_fund = positions[2]
    assert settlement_fund.account_name == "Test Person — Traditional IRA Brokerage Account"
    assert settlement_fund.account_number == "...5678"
    assert settlement_fund.ticker == "VMFXX"
    assert settlement_fund.asset_name == "Vanguard Federal Money Market Fund"
    assert settlement_fund.shares == 0.86
    assert settlement_fund.value == 0.86


def _fulfill_unknown_settlement_fund_page(route: Route) -> None:
    html = """
    <button data-testid="expand-accounts">Expand accounts</button>
    <div data-testid="account-id:111111111111111">
      <span class="c11n-accordion__heading">
        Test Person — Traditional IRA Brokerage Account — 12345678*
      </span>
    </div>
    <div data-testid="settlement-fund-section">
      <a data-testid="settlementFundName"
         href="/en/investor/portfolio/investments/holding-details/111111111111111?positionId=1">
        Some New Settlement Fund
      </a>
      <p data-testid="settlement-fund-balance">$1.00</p>
    </div>
    """
    route.fulfill(body=html, content_type="text/html; charset=utf-8")


def test_scrape_positions_raises_on_unknown_settlement_fund(page: Page) -> None:
    page.route(_POSITIONS_URL, _fulfill_unknown_settlement_fund_page)

    scraper = VanguardScraper(_config(), _settings())

    with pytest.raises(ValueError, match="Unknown settlement fund"):
        scraper.scrape_positions(page)


def _fulfill_empty_page(route: Route) -> None:
    route.fulfill(body="<html></html>", content_type="text/html")


def test_scrape_positions_raises_when_no_accounts_found(page: Page) -> None:
    page.route(_POSITIONS_URL, _fulfill_empty_page)

    scraper = VanguardScraper(_config(), _settings())

    with pytest.raises(ValueError, match="No account containers found"):
        scraper.scrape_positions(page)
