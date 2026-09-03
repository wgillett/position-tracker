import re
from datetime import date

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from position_tracker.models import Position, mask_account_number
from position_tracker.scrapers.base import FirmScraper

_LOGIN_REDIRECT_CHECK_MS = 5 * 1000
_LOGIN_URL_PATTERN = re.compile(r"login", re.IGNORECASE)


class FidelityScraper(FirmScraper):
    def is_logged_in(self, page: Page) -> bool:
        """Best-effort check for headless session reuse: navigate to the positions
        page and see whether Fidelity redirects us to a login URL. Deliberately
        avoids relying on any guessed content selector, since a false negative
        here just costs an extra (harmless) manual-login prompt, while a wrong
        selector can hang the flow entirely."""
        page.goto(self._positions_url())
        try:
            page.wait_for_url(_LOGIN_URL_PATTERN, timeout=_LOGIN_REDIRECT_CHECK_MS)
            return False
        except PlaywrightTimeoutError:
            return not _LOGIN_URL_PATTERN.search(page.url)

    def wait_for_manual_login(self, page: Page) -> None:
        """Block on the human, not on a guessed selector: Fidelity's logged-in
        markup can't be verified without a live session, so ask the person doing
        the login to confirm completion themselves."""
        page.goto(self.config.login_url)
        input(
            "\nComplete login (and any MFA/2FA challenge) in the browser window, "
            "then press Enter here to continue... "
        )

    def scrape_positions(self, page: Page) -> list[Position]:
        """Fidelity's positions grid (ag-Grid) has no nested account containers:
        an account row and its holdings' position rows are flat siblings in DOM
        order, so we walk them in order and track the "current account" as we go."""
        page.goto(self._positions_url())
        self.jittered_delay()

        account_row_selector = self._selector("account_row")
        position_row_selector = self._selector("position_row")
        rows = page.locator(f"{account_row_selector}, {position_row_selector}")
        row_count = rows.count()
        if row_count == 0:
            raise ValueError(
                "No account or position rows found on the Fidelity positions page; "
                "the page structure may have changed. Check the selectors in "
                "config/fidelity.yaml."
            )

        today = date.today()
        positions: list[Position] = []
        current_account_name: str | None = None
        current_account_number: str | None = None

        for i in range(row_count):
            row = rows.nth(i)
            is_account_row = row.evaluate("(el, sel) => el.matches(sel)", account_row_selector)

            if is_account_row:
                name_locator = row.locator(self._selector("account_name"))
                current_account_name = name_locator.inner_text().strip()
                raw_number = row.locator(self._selector("account_number")).inner_text().strip()
                current_account_number = mask_account_number(raw_number)
                continue

            if current_account_name is None or current_account_number is None:
                raise ValueError(
                    "Found a position row before any account row; can't attribute "
                    "it to an account. Check the selectors in config/fidelity.yaml."
                )

            quantity_locator = row.locator(self._selector("quantity"))
            value_locator = row.locator(self._selector("market_value"))
            if quantity_locator.count() == 0 or value_locator.count() == 0:
                # Category header rows (e.g. Fidelity's "Cash / HELD IN MONEY
                # MARKET" divider above the actual settlement-fund holding)
                # match `position_row` but carry no quantity/value cells --
                # they're section labels, not real holdings.
                continue

            positions.append(
                Position(
                    firm=self.config.firm,
                    account_name=current_account_name,
                    account_number=current_account_number,
                    asset_name=row.locator(self._selector("description")).inner_text().strip(),
                    ticker=row.locator(self._selector("symbol")).inner_text().strip(),
                    shares=_parse_number(quantity_locator.inner_text()),
                    value=_parse_number(value_locator.inner_text()),
                    date=today,
                )
            )

        return positions

    def _positions_url(self) -> str:
        if not self.config.positions_url:
            raise ValueError("config/fidelity.yaml is missing 'positions_url'")
        return self.config.positions_url

    def _selector(self, key: str) -> str:
        try:
            return self.config.selectors[key]
        except KeyError as exc:
            raise ValueError(
                f"config/fidelity.yaml is missing selector '{key}' under 'selectors:'"
            ) from exc


def _parse_number(text: str) -> float:
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned:
        raise ValueError(f"Could not parse numeric value from {text!r}")
    return float(cleaned)
