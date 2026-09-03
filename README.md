# position-tracker

Pull balances from personal financial accounts via web scraping (Fidelity, Vanguard), since these institutions don't offer APIs. See [CLAUDE.md](CLAUDE.md) for the full design spec.

## Setup

```
uv sync
uv run playwright install chromium
```

## Usage

Set the output directory, then run `track` for a firm:

```
export POSITION_TRACKER_OUTPUT_DIR=~/finances/positions
uv run track fidelity
```

The first run (or after the session expires) opens a visible browser window for you to log in, including any MFA step. The session is then cached in your OS keychain and reused until it expires.

## Development

```
uv run invoke check   # lint, typecheck, test
uv run pytest tests/unit tests/scraping   # skips tests/live by default
```

`tests/live/` contains manual, opt-in tests that hit the real institution websites. Run them explicitly and only when you mean to:

```
uv run pytest tests/live -m live
```
