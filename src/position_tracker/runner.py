from pathlib import Path
from typing import cast

import click
from playwright.sync_api import StorageState, ViewportSize, sync_playwright

from position_tracker import keychain
from position_tracker.csv_writer import output_path, write_positions_csv
from position_tracker.firm_config import load_firm_config
from position_tracker.scrapers import SCRAPERS
from position_tracker.settings import Settings, load_settings

# Wide enough that firms' data grids (e.g. Fidelity's ag-Grid positions table)
# render every column instead of horizontally virtualizing off-screen ones.
_VIEWPORT: ViewportSize = {"width": 2400, "height": 1400}


def run_track(firm: str, settings: Settings | None = None, *, force_login: bool = False) -> Path:
    settings = settings or load_settings()

    scraper_cls = SCRAPERS.get(firm)
    if scraper_cls is None:
        supported = ", ".join(sorted(SCRAPERS))
        raise SystemExit(f"Unknown firm '{firm}'. Supported firms: {supported}")

    config = load_firm_config(firm, settings.config_dir)
    scraper = scraper_cls(config, settings)

    if force_login:
        keychain.clear_session(firm)

    session_state = (
        None if force_login else keychain.load_session(firm, settings.session_ttl_seconds)
    )
    storage_state = cast(StorageState, session_state) if session_state is not None else None

    # Always run visibly. Headless session reuse was rejected outright by
    # Fidelity's bot defenses (net::ERR_HTTP2_PROTOCOL_ERROR) even with a
    # valid cached session -- retrying automated connection attempts risks
    # looking more suspicious, not less, so we don't try headless at all.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(storage_state=storage_state, viewport=_VIEWPORT)
        page = context.new_page()

        try:
            logged_in = scraper.is_logged_in(page) if session_state is not None else False

            if not logged_in:
                scraper.wait_for_manual_login(page)
                keychain.save_session(firm, dict(context.storage_state()))

            positions = scraper.scrape_positions(page)
        except Exception as exc:
            raise SystemExit(f"Failed to scrape {firm}: {exc}") from exc
        finally:
            browser.close()

    if scraper.ignored_accounts:
        ignored = ", ".join(scraper.ignored_accounts)
        click.echo(f"Ignored accounts with no account number: {ignored}")

    if not positions:
        raise SystemExit(f"No positions found for {firm}; refusing to write an empty CSV.")

    path = output_path(firm, settings.output_dir)
    write_positions_csv(positions, path)
    return path
