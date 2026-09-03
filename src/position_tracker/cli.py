import click

from position_tracker.runner import run_track


@click.command()
@click.argument("firm")
def track(firm: str) -> None:
    """Scrape current positions from FIRM (e.g. fidelity, vanguard) into a CSV."""
    path = run_track(firm.lower())
    click.echo(f"Wrote positions to {path}")


if __name__ == "__main__":
    track()
