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
        """Fidelity's positions grid (ag-Grid) splits each logical row into two
        DOM elements that share a `row-id` attribute: a pinned "Symbol" column
        fragment and a scrollable "center columns" fragment (quantity, value,
        etc.) -- neither fragment alone has all the cells we need. Account rows
        and position rows are themselves flat siblings (no nested containers).
        So: group fragments by row-id (preserving DOM order) into logical rows,
        then walk those, merging cell lookups across each row's fragment(s) and
        tracking the "current account" as we go."""
        page.goto(self._positions_url())
        self.jittered_delay()

        account_row_selector = self._selector("account_row")
        position_row_selector = self._selector("position_row")
        combined_selector = f"{account_row_selector}, {position_row_selector}"
        fragments = page.locator(combined_selector)
        fragment_count = fragments.count()
        if fragment_count == 0:
            raise ValueError(
                "No account or position rows found on the Fidelity positions page; "
                "the page structure may have changed. Check the selectors in "
                "config/fidelity.yaml."
            )

        ordered_row_ids: list[str] = []
        seen_row_ids: set[str] = set()
        for i in range(fragment_count):
            row_id = fragments.nth(i).get_attribute("row-id")
            if row_id and row_id not in seen_row_ids:
                seen_row_ids.add(row_id)
                ordered_row_ids.append(row_id)

        today = date.today()
        positions: list[Position] = []
        current_account_name: str | None = None
        current_account_number: str | None = None
        any_account_seen = False

        for row_id in ordered_row_ids:
            row = page.locator(
                f'{account_row_selector}[row-id="{row_id}"], '
                f'{position_row_selector}[row-id="{row_id}"]'
            )
            matches_account_row = "(el, sel) => el.matches(sel)"
            is_account_row = row.first.evaluate(matches_account_row, account_row_selector)

            if is_account_row:
                name_locator = row.locator(self._selector("account_name"))
                number_locator = row.locator(self._selector("account_number"))
                if name_locator.count() == 0 and number_locator.count() == 0:
                    # Some account rows (e.g. an "Account total" summary row)
                    # don't carry name/number cells in either fragment -- skip
                    # rather than erroring; current_account_name/number carry over.
                    continue
                if number_locator.count() == 0:
                    # A "view" row (e.g. a linked account like "Vanguard SEP IRA")
                    # that has a name but no account number of its own. Its
                    # positions can't be attributed to a real account, so ignore
                    # the whole block until the next real account row.
                    self.ignored_accounts.append(name_locator.inner_text().strip())
                    current_account_name = None
                    current_account_number = None
                    any_account_seen = True
                    continue
                current_account_name = name_locator.inner_text().strip()
                current_account_number = mask_account_number(number_locator.inner_text().strip())
                any_account_seen = True
                continue

            if current_account_name is None or current_account_number is None:
                if any_account_seen:
                    # Belongs to an ignored account block -- skip its positions too.
                    continue
                raise ValueError(
                    "Found a position row before any account row; can't attribute "
                    "it to an account. Check the selectors in config/fidelity.yaml."
                )

            symbol_locator = row.locator(self._selector("symbol"))
            description_locator = row.locator(self._selector("description"))
            quantity_locator = row.locator(self._selector("quantity"))
            value_locator = row.locator(self._selector("market_value"))
            cell_locators = (symbol_locator, description_locator, quantity_locator, value_locator)
            if any(locator.count() == 0 for locator in cell_locators):
                # Category-header dividers (e.g. "Cash / HELD IN MONEY MARKET")
                # match position_row but are missing cells in both fragments --
                # they're section labels, not real holdings.
                continue

            positions.append(
                Position(
                    firm=self.config.firm,
                    account_name=current_account_name,
                    account_number=current_account_number,
                    asset_name=description_locator.inner_text().strip(),
                    ticker=symbol_locator.inner_text().strip(),
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
    if text.strip() == "--":
        # Fidelity uses "--" for cells with no applicable value, e.g. shares
        # on a holding that isn't share-denominated.
        return 0.0
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned:
        raise ValueError(f"Could not parse numeric value from {text!r}")
    return float(cleaned)
