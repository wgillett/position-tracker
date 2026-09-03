from pathlib import Path
from typing import cast

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, StorageState, ViewportSize, sync_playwright

from position_tracker import keychain
from position_tracker.csv_writer import output_path, write_positions_csv
from position_tracker.firm_config import load_firm_config
from position_tracker.scrapers import SCRAPERS
from position_tracker.scrapers.base import FirmScraper
from position_tracker.settings import Settings, load_settings

# Wide enough that firms' data grids (e.g. Fidelity's ag-Grid positions table)
# render every column instead of horizontally virtualizing off-screen ones.
_VIEWPORT: ViewportSize = {"width": 2400, "height": 1400}


def run_track(firm: str, settings: Settings | None = None) -> Path:
    settings = settings or load_settings()

    scraper_cls = SCRAPERS.get(firm)
    if scraper_cls is None:
        supported = ", ".join(sorted(SCRAPERS))
        raise SystemExit(f"Unknown firm '{firm}'. Supported firms: {supported}")

    config = load_firm_config(firm, settings.config_dir)
    scraper = scraper_cls(config, settings)

    session_state = keychain.load_session(firm, settings.session_ttl_seconds)
    storage_state = cast(StorageState, session_state) if session_state is not None else None

    with sync_playwright() as playwright:
        headless = session_state is not None
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=storage_state, viewport=_VIEWPORT)
        page = context.new_page()

        try:
            logged_in = _check_logged_in(scraper, page) if session_state is not None else False

            if logged_in is None and headless:
                # Headless reuse can be rejected outright by a site's bot defenses
                # (seen in practice as net::ERR_HTTP2_PROTOCOL_ERROR against
                # Fidelity) even with a still-valid cached session. Retry the same
                # session visibly before concluding it actually needs a fresh login.
                print("Headless session reuse failed; retrying the same session visibly.")
                context.close()
                browser.close()
                browser = playwright.chromium.launch(headless=False)
                context = browser.new_context(storage_state=storage_state, viewport=_VIEWPORT)
                page = context.new_page()
                logged_in = _check_logged_in(scraper, page)

            if not logged_in:
                scraper.wait_for_manual_login(page)
                keychain.save_session(firm, dict(context.storage_state()))

            positions = scraper.scrape_positions(page)
        except Exception as exc:
            raise SystemExit(f"Failed to scrape {firm}: {exc}") from exc
        finally:
            browser.close()

    if not positions:
        raise SystemExit(f"No positions found for {firm}; refusing to write an empty CSV.")

    path = output_path(firm, settings.output_dir)
    write_positions_csv(positions, path)
    return path


def _check_logged_in(scraper: FirmScraper, page: Page) -> bool | None:
    """True/False if the check succeeded, or None if the check itself failed
    (e.g. a headless connection rejected by the site's bot defenses) rather
    than definitively answering whether the session is valid."""
    try:
        return scraper.is_logged_in(page)
    except PlaywrightError:
        return None
