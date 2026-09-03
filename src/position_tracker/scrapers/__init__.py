from position_tracker.scrapers.base import FirmScraper
from position_tracker.scrapers.fidelity import FidelityScraper
from position_tracker.scrapers.vanguard import VanguardScraper

SCRAPERS: dict[str, type[FirmScraper]] = {
    "fidelity": FidelityScraper,
    "vanguard": VanguardScraper,
}

__all__ = ["FirmScraper", "SCRAPERS"]
