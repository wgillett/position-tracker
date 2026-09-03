import csv
from datetime import UTC, datetime
from pathlib import Path

from position_tracker.models import Position

FIELDNAMES = [
    "firm",
    "account_name",
    "account_number",
    "asset_name",
    "ticker",
    "shares",
    "value",
    "date",
]


def output_path(firm: str, output_dir: Path, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return output_dir / f"{firm}_positions_{timestamp}.csv"


def write_positions_csv(positions: list[Position], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for position in positions:
            row = position.model_dump(mode="json")
            writer.writerow(row)
