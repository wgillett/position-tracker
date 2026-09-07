import click

from position_tracker.runner import run_track


@click.command()
@click.argument("firm")
@click.option(
    "--force-login",
    is_flag=True,
    default=False,
    help="Discard any cached session and require a fresh manual login.",
)
def track(firm: str, force_login: bool) -> None:
    """Scrape current positions from FIRM (e.g. fidelity, vanguard) into a CSV."""
    path = run_track(firm.lower(), force_login=force_login)
    click.echo(f"Wrote positions to {path}")


if __name__ == "__main__":
    track()
