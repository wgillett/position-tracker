import re
from datetime import date

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from position_tracker.models import Position, mask_account_number
from position_tracker.scrapers.base import FirmScraper

_LOGIN_REDIRECT_CHECK_MS = 5 * 1000
# Vanguard's authentication flow runs on a separate "logon" subdomain (unlike
# Fidelity, which redirects to a /login path on the same host) -- match both
# so a future change to either flow doesn't silently break detection.
_LOGIN_URL_PATTERN = re.compile(r"logon|login|signin", re.IGNORECASE)

# Splits an account accordion's heading, e.g.
# "Walter Gillett — Traditional IRA Brokerage Account — 12345678*", on the em
# dash Vanguard uses as a separator.
_HEADING_SEPARATOR = re.compile(r"\s+—\s+")

# The settlement (sweep) fund's card has no ticker in its markup, so known
# fund names are mapped to their ticker by hand. Add an entry here (and see
# the ValueError raised below) if a new settlement fund name is encountered.
_SETTLEMENT_FUND_TICKERS = {
    "VANGUARD FEDERAL MONEY MARKET FUND": "VMFXX",
}

# Extracts the Vanguard account id embedded in a settlement-fund card's
# details link, e.g. "/en/.../holding-details/123456789012345?positionId=...",
# so each settlement-fund balance can be matched to its account without
# assuming it's nested inside that account's DOM container.
_ACCOUNT_ID_IN_HREF = re.compile(r"/holding-details/(\d+)")


class VanguardScraper(FirmScraper):
    def is_logged_in(self, page: Page) -> bool:
        """Best-effort check for headless session reuse: navigate to the positions
        page and see whether Vanguard redirects us to a login/logon URL. Mirrors
        FidelityScraper.is_logged_in -- see its docstring for the reasoning."""
        page.goto(self._positions_url())
        try:
            page.wait_for_url(_LOGIN_URL_PATTERN, timeout=_LOGIN_REDIRECT_CHECK_MS)
            return False
        except PlaywrightTimeoutError:
            return not _LOGIN_URL_PATTERN.search(page.url)

    def wait_for_manual_login(self, page: Page) -> None:
        """Block on the human, not on a guessed selector: Vanguard's logged-in
        markup can't be verified without a live session, so ask the person doing
        the login to confirm completion themselves."""
        page.goto(self.config.login_url)
        input(
            "\nComplete login (and any MFA/2FA challenge) in the browser window, "
            "then press Enter here to continue... "
        )

    def scrape_positions(self, page: Page) -> list[Position]:
        """Each account is its own accordion (data-testid="account-id:<id>"),
        expanded by clicking "Expand accounts" once up front. Each account's
        holdings live in their own <table>, with category-header rows (e.g.
        "Mutual funds") interspersed among the real holding rows -- see
        config/vanguard.yaml for why column position is resolved dynamically
        instead of hardcoded. The settlement/sweep fund balance renders in a
        separate card rather than this table; it's matched to its account via
        the account id embedded in the card's own link, not DOM nesting (that
        hasn't been confirmed live)."""
        page.goto(self._positions_url())
        self.jittered_delay()

        expand_button = page.locator(self._selector("expand_accounts_button"))
        if expand_button.count() > 0:
            expand_button.first.click()
            self.jittered_delay()

        accounts = page.locator(self._selector("account_container"))
        account_count = accounts.count()
        if account_count == 0:
            raise ValueError(
                "No account containers found on the Vanguard Holdings page; the "
                "page structure may have changed. Check the selectors in "
                "config/vanguard.yaml."
            )

        today = date.today()
        positions: list[Position] = []
        account_info: dict[str, tuple[str, str]] = {}
        seen_account_ids: set[str] = set()

        for i in range(account_count):
            account = accounts.nth(i)
            account_testid = account.get_attribute("data-testid") or ""
            account_id = account_testid.removeprefix("account-id:")
            seen_account_ids.add(account_id)

            heading_locator = account.locator(self._selector("account_heading")).first
            parsed_heading = self._parse_heading(heading_locator.inner_text())
            if parsed_heading is None:
                # No account number in the heading -- observed for defunct/
                # duplicate account entries with no real holdings (e.g.
                # "Sharon E. Gillett — SEP-IRA" alongside a real, numbered
                # "Sharon E. Gillett — SEP-IRA Brokerage Account — ...*").
                # Skip it, including any settlement-fund card that might
                # reference it (see the account_info lookup below).
                continue
            account_name, account_number = parsed_heading
            account_info[account_id] = (account_name, account_number)

            tables = account.locator(self._selector("holdings_table"))
            if tables.count() == 0:
                # An account with no tradeable holdings (e.g. cash-only) has no
                # holdings table at all -- nothing to scrape for it.
                continue
            table = tables.first

            quantity_index = self._column_index(table, "quantity_column_header")
            balance_index = self._column_index(table, "balance_column_header")

            rows = table.locator(self._selector("holding_row"))
            for r in range(rows.count()):
                row = rows.nth(r)
                ticker_locator = row.locator(self._selector("ticker"))
                description_locator = row.locator(self._selector("description"))
                if ticker_locator.count() == 0 or description_locator.count() == 0:
                    continue

                quantity_cell = row.locator(f":scope > :nth-child({quantity_index})")
                balance_cell = row.locator(f":scope > :nth-child({balance_index})")

                positions.append(
                    Position(
                        firm=self.config.firm,
                        account_name=account_name,
                        account_number=account_number,
                        asset_name=description_locator.inner_text().strip(),
                        ticker=ticker_locator.inner_text().strip(),
                        shares=_parse_number(quantity_cell.inner_text()),
                        value=_parse_number(balance_cell.inner_text()),
                        date=today,
                    )
                )

        positions.extend(self._scrape_settlement_funds(page, account_info, seen_account_ids, today))

        return positions

    def _scrape_settlement_funds(
        self,
        page: Page,
        account_info: dict[str, tuple[str, str]],
        seen_account_ids: set[str],
        today: date,
    ) -> list[Position]:
        sections = page.locator(self._selector("settlement_fund_section"))
        positions: list[Position] = []

        for i in range(sections.count()):
            section = sections.nth(i)
            name_link = section.locator(self._selector("settlement_fund_name")).first
            href = name_link.get_attribute("href") or ""
            match = _ACCOUNT_ID_IN_HREF.search(href)
            if match is None:
                raise ValueError(
                    f"Could not find an account id in settlement fund link {href!r}; "
                    f"the page structure may have changed. Check the "
                    f"'settlement_fund_name' selector in config/vanguard.yaml."
                )
            account_id = match.group(1)
            if account_id not in account_info:
                if account_id in seen_account_ids:
                    # Belongs to an account we intentionally skipped (its
                    # heading had no account number) -- skip its settlement
                    # fund too, rather than treating it as a structural bug.
                    continue
                raise ValueError(
                    f"Settlement fund link referenced account id {account_id!r}, which "
                    f"doesn't match any scraped account. Check the selectors in "
                    f"config/vanguard.yaml."
                )
            account_name, account_number = account_info[account_id]

            fund_name = name_link.inner_text().strip()
            ticker = _SETTLEMENT_FUND_TICKERS.get(fund_name.upper())
            if ticker is None:
                raise ValueError(
                    f"Unknown settlement fund {fund_name!r}; add its ticker to "
                    f"_SETTLEMENT_FUND_TICKERS in src/position_tracker/scrapers/vanguard.py."
                )

            balance_locator = section.locator(self._selector("settlement_fund_balance"))
            value = _parse_number(balance_locator.inner_text())

            positions.append(
                Position(
                    firm=self.config.firm,
                    account_name=account_name,
                    account_number=account_number,
                    asset_name=fund_name,
                    ticker=ticker,
                    # The settlement fund's NAV is fixed at $1, so shares == dollars;
                    # no share count is ever shown in this card's markup.
                    shares=value,
                    value=value,
                    date=today,
                )
            )

        return positions

    def _column_index(self, table: Locator, header_key: str) -> int:
        """Return the 1-based position of a header cell among its <tr>'s element
        children, so the same position can be read off each body row -- there's
        no per-cell selector for quantity/balance, only on the header."""
        header = table.locator(self._selector(header_key))
        if header.count() == 0:
            raise ValueError(
                f"Could not find header cell for '{header_key}' in a Vanguard "
                f"holdings table. Check the selectors in config/vanguard.yaml."
            )
        index: int = header.first.evaluate(
            "el => Array.from(el.parentElement.children).indexOf(el) + 1"
        )
        return index

    def _parse_heading(self, text: str) -> tuple[str, str] | None:
        """Split an account accordion heading like
        "Walter Gillett — Traditional IRA Brokerage Account — 12345678*" into
        (account_name, masked_account_number). account_name keeps everything
        before the number ("Walter Gillett — Traditional IRA Brokerage
        Account"), since the account holder's name distinguishes accounts of
        the same type held by different family members. Vanguard's own
        trailing '*' is discarded in favor of masking the digits ourselves.

        Returns None for a heading with no trailing number segment (just
        "Name — Account Type"), observed for defunct/duplicate account
        entries with no real holdings -- callers should skip these rather
        than treat them as an error."""
        parts = _HEADING_SEPARATOR.split(text.strip())
        if len(parts) == 2:
            return None
        if len(parts) < 3:
            raise ValueError(
                f"Could not parse account name/number from heading {text!r}; "
                f"expected 'Name — Account Type — Number*' (or 'Name — Account "
                f"Type' for a numberless account). Check the 'account_heading' "
                f"selector in config/vanguard.yaml."
            )
        account_name = " — ".join(part.strip() for part in parts[:-1])
        digits = re.sub(r"\D", "", parts[-1])
        if not digits:
            raise ValueError(f"Could not find an account number in heading {text!r}")
        return account_name, mask_account_number(digits)

    def _positions_url(self) -> str:
        if not self.config.positions_url:
            raise ValueError("config/vanguard.yaml is missing 'positions_url'")
        return self.config.positions_url

    def _selector(self, key: str) -> str:
        try:
            return self.config.selectors[key]
        except KeyError as exc:
            raise ValueError(
                f"config/vanguard.yaml is missing selector '{key}' under 'selectors:'"
            ) from exc


def _parse_number(text: str) -> float:
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned:
        raise ValueError(f"Could not parse numeric value from {text!r}")
    return float(cleaned)
