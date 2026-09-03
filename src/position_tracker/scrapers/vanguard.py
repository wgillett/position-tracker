from playwright.sync_api import Page

from position_tracker.models import Position
from position_tracker.scrapers.base import FirmScraper


class VanguardScraper(FirmScraper):
    def is_logged_in(self, page: Page) -> bool:
        raise NotImplementedError("Vanguard login detection not yet implemented")

    def wait_for_manual_login(self, page: Page) -> None:
        raise NotImplementedError("Vanguard manual login flow not yet implemented")

    def scrape_positions(self, page: Page) -> list[Position]:
        raise NotImplementedError("Vanguard position scraping not yet implemented")
