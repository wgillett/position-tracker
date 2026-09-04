"""Manual, opt-in end-to-end check of the real VanguardScraper.

Reuses a cached session from the keychain when one is still valid (same as
`track`), falling back to a visible manual login otherwise. Then runs the
actual scrape_positions() and prints a summary with every dollar/share value
omitted -- only account names, masked account numbers, tickers, and asset
names are safe to print, since digit-redaction would otherwise mangle the
numbers we actually care to sanity-check by eye (real vs. garbled).

Run explicitly (never part of the default suite or CI):
    uv run pytest -m live tests/live/test_vanguard_live.py -s
"""

from typing import cast

import pytest
from playwright.sync_api import StorageState, ViewportSize, sync_playwright

from position_tracker import keychain
from position_tracker.firm_config import load_firm_config
from position_tracker.scrapers.vanguard import VanguardScraper
from position_tracker.settings import load_settings

pytestmark = pytest.mark.live

_VIEWPORT: ViewportSize = {"width": 2400, "height": 1400}


def test_vanguard_scrape_positions() -> None:
    settings = load_settings()
    config = load_firm_config("vanguard", settings.config_dir)
    scraper = VanguardScraper(config, settings)

    session_state = keychain.load_session("vanguard", settings.session_ttl_seconds)

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
            keychain.save_session("vanguard", dict(context.storage_state()))

        positions = scraper.scrape_positions(page)

        print(f"\n{len(positions)} position(s) scraped:")
        for p in positions:
            print(f"  [{p.account_name} {p.account_number}] {p.ticker} -- {p.asset_name}")

        browser.close()
