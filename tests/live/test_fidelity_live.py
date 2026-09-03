"""Manual, opt-in helper for keeping config/fidelity.yaml selectors up to date.

Reuses a cached session from the keychain when one is still valid (same as
`track`), so repeated runs while tuning selectors don't force a fresh login
each time. Falls back to a visible, manual login only when the cached session
is missing or stale.

Reports which configured selectors match the live positions page, lists every
`data-testid` attribute found, and -- if the account/holding selectors don't
match -- scans for class names and ids that look related, dumping the most
promising container's outerHTML.

Never writes page content to disk, and only prints digit-redacted HTML to the
terminal -- balances and account numbers should never appear verbatim, even
in scrollback.

Run explicitly (never part of the default suite or CI):
    uv run pytest -m live tests/live/test_fidelity_live.py -s
"""

import re
from typing import cast

import pytest
from playwright.sync_api import Page, StorageState, ViewportSize, sync_playwright

from position_tracker import keychain
from position_tracker.firm_config import load_firm_config
from position_tracker.scrapers.fidelity import FidelityScraper
from position_tracker.settings import load_settings

pytestmark = pytest.mark.live

# Wide enough that Fidelity's ag-Grid positions table renders every column
# instead of horizontally virtualizing off-screen ones out of the DOM.
_VIEWPORT: ViewportSize = {"width": 2400, "height": 1400}

_DIGITS = re.compile(r"\d")
_RELEVANT_KEYWORD = re.compile(
    r"row|cell|position|holding|grid|symbol|quantity|value|table", re.IGNORECASE
)


def _redact(text: str) -> str:
    """Blank out digits so balances/account numbers never hit the terminal verbatim."""
    return _DIGITS.sub("#", text)


def test_fidelity_selector_inspection() -> None:
    settings = load_settings()
    config = load_firm_config("fidelity", settings.config_dir)
    scraper = FidelityScraper(config, settings)

    session_state = keychain.load_session("fidelity", settings.session_ttl_seconds)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        storage_state = cast(StorageState, session_state) if session_state is not None else None
        context = browser.new_context(storage_state=storage_state, viewport=_VIEWPORT)
        page = context.new_page()

        if session_state is not None and scraper.is_logged_in(page):
            print("\nReused cached session from the keychain -- no login needed.")
        else:
            print(f"\nOpening {config.login_url}")
            print("Please log in and complete any MFA/2FA challenge in the browser window.")
            scraper.wait_for_manual_login(page)
            print("Login detected. Saving session to the keychain for future runs.")
            keychain.save_session("fidelity", dict(context.storage_state()))
            page.goto(scraper._positions_url())

        scraper.jittered_delay()

        testids: list[str] = page.eval_on_selector_all(
            "[data-testid]",
            "els => [...new Set(els.map(e => e.getAttribute('data-testid')))].sort()",
        )
        print(f"\n{len(testids)} distinct data-testid values found on the positions page:")
        for testid in testids:
            print(f"  {testid}")

        print("\nMatch counts for selectors currently configured in config/fidelity.yaml:")
        for name, selector in config.selectors.items():
            count = page.locator(selector).count()
            status = "OK" if count > 0 else "NO MATCH"
            print(f"  [{status:8s}] {name:25s} {selector!r:55s} -> {count}")

        account_row_selector = config.selectors.get("account_row")
        position_row_selector = config.selectors.get("position_row")
        row_selectors = [s for s in (account_row_selector, position_row_selector) if s]

        if row_selectors and all(page.locator(s).count() > 0 for s in row_selectors):
            print("\nAccount and position row selectors both matched.")
            assert account_row_selector is not None
            assert position_row_selector is not None
            print("Dumping a sample account row (digits redacted):")
            _dump_row_samples(page, [account_row_selector])
            _report_position_row_variants(
                page,
                position_row_selector,
                config.selectors.get("quantity"),
                config.selectors.get("market_value"),
            )
        else:
            print("\n'account_row' and/or 'position_row' did not both match.")
            print("Scanning for likely grid-related class names and ids instead...")
            _report_relevant_attributes(page)
            if not _dump_row_samples(page, [".posweb-row-account", ".posweb-row-position"]):
                grid_candidates = [
                    "[role='grid']",
                    "[role='table']",
                    "table",
                    "[data-testid='grid-top']",
                ]
                _dump_first_matching_container(page, grid_candidates)

        browser.close()


def _report_relevant_attributes(page: Page) -> None:
    """Print class names and ids across the whole page that look row/grid-related,
    since the positions grid apparently doesn't expose data-testid at the row level."""
    classes: list[str] = page.evaluate(
        """() => {
            const tokens = new Set();
            document.querySelectorAll('*').forEach(el => {
                el.classList.forEach(c => tokens.add(c));
            });
            return [...tokens].sort();
        }"""
    )
    ids: list[str] = page.evaluate(
        "() => [...new Set([...document.querySelectorAll('[id]')].map(e => e.id))].sort()"
    )

    relevant_classes = [c for c in classes if _RELEVANT_KEYWORD.search(c)]
    relevant_ids = [i for i in ids if _RELEVANT_KEYWORD.search(i)]

    print(f"\n{len(relevant_classes)} class names matching row/grid/position-like keywords:")
    for c in relevant_classes:
        print(f"  .{c}")
    print(f"\n{len(relevant_ids)} ids matching the same keywords:")
    for i in relevant_ids:
        print(f"  #{i}")


def _dump_row_samples(page: Page, row_selectors: list[str]) -> bool:
    """Fidelity's positions grid is ag-Grid: accounts and their holdings are flat,
    sibling `.ag-row` elements (not nested containers), distinguished by a marker
    class like `.posweb-row-account` / `.posweb-row-position`. Dump one full
    example of each such row (digits redacted) to see the real cell structure.
    Returns True if at least one sample was found and printed."""
    found_any = False
    for selector in row_selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            html: str = locator.first.evaluate("el => el.outerHTML")
            print(f"\nFirst row matching {selector!r} (digits redacted, truncated to 10000 chars):")
            print(_redact(html)[:10000])
            found_any = True
        else:
            print(f"\nNo rows matched {selector!r}.")
    return found_any


def _report_position_row_variants(
    page: Page,
    position_row_selector: str,
    quantity_selector: str | None,
    value_selector: str | None,
) -> None:
    """Not every position row necessarily carries the same cells (e.g. a cash/core
    position row might have no quantity or market-value column). Split rows into
    'complete' (has both quantity and market_value) vs not, report the split and
    the extra classes seen on incomplete rows (for special-casing in the
    scraper), and dump one full example of each."""
    rows = page.locator(position_row_selector)
    row_count = rows.count()

    complete_html: str | None = None
    incomplete_html: str | None = None
    incomplete_classes: set[str] = set()
    complete_count = 0

    for i in range(row_count):
        row = rows.nth(i)
        has_quantity = quantity_selector is not None and row.locator(quantity_selector).count() > 0
        has_value = value_selector is not None and row.locator(value_selector).count() > 0
        if has_quantity and has_value:
            complete_count += 1
            if complete_html is None:
                complete_html = row.evaluate("el => el.outerHTML")
        else:
            if incomplete_html is None:
                incomplete_html = row.evaluate("el => el.outerHTML")
            row_classes: list[str] = row.evaluate("el => [...el.classList]")
            incomplete_classes.update(row_classes)

    incomplete_count = row_count - complete_count
    print(f"\n{complete_count} of {row_count} position rows have both quantity and market_value.")
    print(f"{incomplete_count} are missing one or both (e.g. cash/core positions).")

    if incomplete_classes:
        print("\nClasses seen on rows missing quantity/value (for special-casing):")
        for c in sorted(incomplete_classes):
            print(f"  .{c}")

    if complete_html:
        print("\nA complete position row (digits redacted, truncated to 10000 chars):")
        print(_redact(complete_html)[:10000])
    if incomplete_html:
        print("\nAn incomplete position row (digits redacted, truncated to 10000 chars):")
        print(_redact(incomplete_html)[:10000])


def _dump_first_matching_container(page: Page, candidates: list[str]) -> None:
    """Print the digit-redacted outerHTML of the first candidate that matches,
    truncated to keep terminal output manageable, so real selectors for the
    positions grid can be worked out without exposing balances/account numbers."""
    for candidate in candidates:
        locator = page.locator(candidate)
        if locator.count() > 0:
            html: str = locator.first.evaluate("el => el.outerHTML")
            print(f"\nFound candidate container {candidate!r}")
            print("(digits redacted, truncated to 6000 chars):")
            print(_redact(html)[:6000])
            return

    print("No likely grid container found automatically either.")
    print("If you can, share sanitized HTML instead: in the browser, right-click the")
    print("holdings table -> Inspect, select its container in devtools, right-click it")
    print("-> Copy -> Copy outerHTML, then find-and-replace all digits with '#' before")
    print("sharing it back so account numbers and balances aren't exposed.")
