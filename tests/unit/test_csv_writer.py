from datetime import UTC, date, datetime
from pathlib import Path

from position_tracker.csv_writer import output_path, write_positions_csv
from position_tracker.models import Position


def test_output_path_uses_iso8601_basic_timestamp(tmp_path: Path) -> None:
    now = datetime(2026, 9, 3, 14, 30, 27, tzinfo=UTC)
    path = output_path("fidelity", tmp_path, now=now)
    assert path == tmp_path / "fidelity_positions_20260903T143027Z.csv"


def test_write_positions_csv_roundtrip(tmp_path: Path) -> None:
    positions = [
        Position(
            firm="fidelity",
            account_name="Individual",
            account_number="...1234",
            asset_name="Fidelity® Government Money Market Fund",
            ticker="SPAXX",
            shares=100.5,
            value=100.5,
            date=date(2026, 9, 3),
        )
    ]
    path = tmp_path / "out.csv"
    write_positions_csv(positions, path)

    content = path.read_text()
    lines = content.strip().splitlines()
    assert lines[0] == "firm,account_name,account_number,asset_name,ticker,shares,value,date"
    assert "SPAXX" in lines[1]
    assert "...1234" in lines[1]


def test_write_positions_csv_overwrites_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    path.write_text("stale content")

    write_positions_csv([], path)

    content = path.read_text()
    assert "stale content" not in content
