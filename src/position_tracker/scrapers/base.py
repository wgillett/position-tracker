import random
import time
from abc import ABC, abstractmethod

from playwright.sync_api import Page

from position_tracker.firm_config import FirmConfig
from position_tracker.models import Position
from position_tracker.settings import Settings


class FirmScraper(ABC):
    """Base class for a single institution's scraping logic.

    Firm-specific website behavior lives entirely in subclasses; everything
    else (session reuse, delays, CSV output) is handled by the runner.
    """

    def __init__(self, config: FirmConfig, settings: Settings) -> None:
        self.config = config
        self.settings = settings
        self.ignored_accounts: list[str] = []
        """Account names skipped during scraping (e.g. a "view" with no account
        number of its own), populated by scrape_positions for the runner to report."""

    @abstractmethod
    def is_logged_in(self, page: Page) -> bool:
        """Return True if the current page shows an authenticated session."""

    @abstractmethod
    def wait_for_manual_login(self, page: Page) -> None:
        """Navigate to the login page and block until the user has completed
        login (including any MFA/2FA challenge) in the visible browser."""

    @abstractmethod
    def scrape_positions(self, page: Page) -> list[Position]:
        """Navigate to each account and return every holding found."""

    def jittered_delay(self) -> None:
        time.sleep(random.uniform(self.settings.min_delay_seconds, self.settings.max_delay_seconds))
