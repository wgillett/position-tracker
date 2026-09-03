from datetime import date

from pydantic import BaseModel


class Position(BaseModel):
    """A single holding in a single account, as scraped from a firm's website."""

    firm: str
    account_name: str
    account_number: str
    """Masked to the last 4 digits, e.g. '...1234'. Never store the full number."""
    asset_name: str
    ticker: str
    shares: float
    value: float
    date: date


def mask_account_number(full_account_number: str) -> str:
    last_four = full_account_number.strip()[-4:]
    return f"...{last_four}"
