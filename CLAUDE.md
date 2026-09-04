# Goal

Retrieve balances from personal accounts at institutions such as Fidelity and Vanguard, using web scraping, since APIs are not available.

# Features

## Financial Firms

Start with just Fidelity and Vanguard. Abstract out firm-specific logic (e.g., website URLs) into config files and separate modules so that the code can easily be generalized to handle new firms.

## Security

Top priority, since a mistake could put family finances at risk.
Handle sensitive data like credentials, session tokens, and account numbers carefully and never check these values into source control or write them to a plaintext local file. The one exception is the OS keychain (via the `keyring` package): credentials and session tokens may be stored there, since it is not a plain file that could be committed or casually read.

## Compliance

Be respectful of the websites we scrape from, to avoid getting into trouble with terms-of-service rules. Log in as infrequently as possible and reuse existing sessions, stored in the OS keychain, across `track` invocations. Session TTL can be up to one hour (firms may time out sessions faster than that). If no valid cached session exists, fall back to a headful (visible) Playwright browser so the user can complete login and any MFA/2FA challenge manually; capture the resulting session into the keychain afterward.
Try to avoid triggering bot detection. Use randomized/jittered delays between page hits, in the 2–5 second range per page.

# Tech

- Python 3.14 - the most recent stable release
  - use a .python-version pin to ensure stability
- uv - project management
  - configure the project via pyproject.toml
- click - CLI
- pyyaml - configuration
- pydantic-settings - typed, validated configuration
- keyring - OS keychain access for credentials and session tokens
- hatchling - build backend
- Playwright - web scraping library
- ruff - linting
- mypy - type checking
- pytest - testing
- pre-commit — runs formatters/linters automatically on commit
- invoke - Python task execution library and command-line tool
- start with the most recent stable versions of all libraries and set up uv.lock for stability

# Design

Create a CLI Python-based app that scrapes balances from personal financial accounts.

## CLI command

`track <firm>`

Work with the user to log into the firm's website, then pull down positions from all accounts on the firm's website and store the data in a single CSV with the following columns:
- firm
- account_name
- account_number - masked to the last 4 digits, e.g., ...1234
- asset_name - e.g., Fidelity® Government Money Market Fund
- ticker - e.g., SPAXX
- shares - number of shares
- value - in dollars
- date - date on which the data was pulled

### Configuration

Use a "config" directory at project root level to store config files. Each firm gets a config file `<firm>.yaml`. It's OK to check these files in given that they are not sensitive and this project is not trying to support reuse by others.

### Error handling

If there are any errors during the scraping, fail immediately and print out an informative error message.

### CSV output file

- Create a brand-new CSV file each time named `<firm>_positions_<timestamp>.csv`, where timestamp is ISO 8601 basic format, e.g.,20260903T143027Z. If a file with that name already exists, overwrite the existing file.
- Put the file in an output directory configured via pydantic-settings. If the output directory is not configured, fail and print an error guiding the user how to set the config.

## Testing

Strategy:
1. Unit tests (fast, no browser): parsing/extraction logic, Pydantic settings/config validation, CLI argument handling, session/cookie storage logic
2. Playwright tests against fixtures/mocks

Structure:
- pytest + pytest-playwright plugin provides the page/browser fixtures.
- Separate test dirs: tests/unit/, tests/scraping/ (fixture-driven Playwright), tests/live/ (manual-only, excluded from default pytest run via markers)

Live-site tests must be explicit, opt-in, human-run check rather than something automated, to avoid security risks and triggering bot detection.
