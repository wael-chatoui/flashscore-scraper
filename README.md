# FlashScore Scraper

A Python CLI tool that scrapes volleyball and hockey match data from [FlashScore.fr](https://www.flashscore.fr) and injects them into Google Sheets.

Collects match info, league rankings, and head-to-head statistics daily — runs unattended on a VPS via Docker and a cron scheduler.

## Features

- **Volleyball**: scrapes matches, league standings, and H2H set statistics (3/4/5-set counts)
- **Hockey**: scrapes matches, league standings, and H2H goal statistics
- **Google Sheets integration**: injects data into configurable column presets, deduplicates by date, sorts, and rebuilds formulas
- **Batch mode**: scrape multiple days in a single run
- **Scheduling**: systemd timer, cron, or Docker + ofelia

## Quick Start

### Prerequisites

- Python 3.10+
- A Google Cloud service account with Sheets API access
- A `credentials.json` file for the service account

### Install

```bash
pip install -e .
playwright install chromium
```

### Configure

```bash
cp .env.example .env
# Edit .env — set SPREADSHEET_ID at minimum
```

### Run

```bash
# Full pipeline: scrape + inject to Google Sheets
flashscore-scraper

# Scrape only (saves JSON to output/)
flashscore-scraper --scrape-only

# Inject an existing JSON file into Sheets
flashscore-scraper --sheets-only --json=output/matches_2026-02-25.json

# Scrape a different date (days offset from tomorrow)
flashscore-scraper --days=-2

# Scrape hockey instead of volleyball
flashscore-scraper --sport=hockey

# Batch scrape multiple days
python -m flashscore_scraper.batch_scrape --from=-7 --to=0
```

## Configuration

Set these in `.env` or as environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SPREADSHEET_ID` | Google Sheet ID | *required* |
| `GOOGLE_CREDENTIALS_PATH` | Path to `credentials.json` | `./credentials.json` |
| `SPORT` | `volleyball` or `hockey` | `volleyball` |
| `HEADLESS` | Run browser headless | `true` |
| `REQUEST_DELAY` | Delay between requests (ms) | `1000` |
| `MAX_MATCHES` | Limit matches per run (0 = all) | `0` |
| `SHEET_PRESET` | Column layout preset | `SCRAPING OU4` |
| `START_ROW` | First data row in the sheet | `2` |

### Column Presets

The `SHEET_PRESET` variable controls how data maps to sheet columns:

- **`ORIGINAL`** — Full layout with computed formula columns
- **`SCRAPING OU4`** — Default scraping layout
- **`CALCUL SET`** — Alternative mapping
- **`HOCKEY UND`** — Hockey-specific layout (auto-selected for hockey)

## Docker

```bash
# One-off run
docker compose up --build

# With daily scheduler (runs at 1:00 AM UTC)
docker compose --profile scheduled up -d
```

## Scheduling

### Systemd (recommended for Linux)

```bash
./scripts/install_cron.sh systemd   # Install timer (daily at 1:00 AM)
./scripts/install_cron.sh remove    # Remove
```

### Cron

```bash
./scripts/install_cron.sh cron      # Install cron job
```

## Project Structure

```
flashscore_scraper/
├── main.py              # CLI entry point and pipeline orchestration
├── config.py            # Configuration (dataclasses + env vars)
├── base_scraper.py      # Shared scraper logic (browser, navigation, standings)
├── scraper.py           # Volleyball-specific H2H scraping
├── hockey_scraper.py    # Hockey-specific H2H scraping
├── sheets.py            # Google Sheets injection and formulas
├── sort_sheet.py        # Sheet sorting by date
├── batch_scrape.py      # Multi-day batch scraper
└── read_sheet.py        # Sheet inspection utility
scripts/
├── run_scraper.sh       # Runner script for cron/systemd
├── install_cron.sh      # Scheduler installer
└── debug/               # Debug and test scripts
```

## How It Works

1. **Scrape** — Launches headless Chromium via Playwright, navigates FlashScore.fr to the target date, extracts all matches with league/country metadata
2. **Rankings** — For each league found, fetches the standings page and attaches team ranks
3. **H2H Stats** — For each match, visits the head-to-head page and counts set distributions (volleyball) or goal thresholds (hockey)
4. **Save JSON** — Writes results to `output/` as a dated JSON file
5. **Inject** — Deduplicates by date, writes data to Google Sheets using the configured column preset
6. **Sort** — Sorts the sheet chronologically and rebuilds computed formulas

## CI/CD

Pushing to `main` triggers a GitHub Actions pipeline:

1. **Lint** — `ruff check` + `ruff format --check`
2. **Test** — `pytest`
3. **Deploy** — SSH to production VPS, pull, rebuild Docker containers

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Lint
ruff check .
ruff format --check .

# Test
pytest

# Pre-commit hooks
pre-commit install
```

## License

Private project.
