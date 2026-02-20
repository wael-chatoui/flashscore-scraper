# CLAUDE.md - Project Guidelines

## Project Overview

FlashScore Volleyball Scraper - A Python tool that scrapes volleyball match data and head-to-head statistics from FlashScore.fr and injects them into Google Sheets.

## Tech Stack

- **Python 3.10+**
- **Playwright** - Browser automation for web scraping
- **Google API Python Client** - Google Sheets integration
- **python-dotenv** - Environment variable management

## Project Structure

```
flashscore-scraper/
├── flashscore_scraper/         # Main Python package
│   ├── __init__.py             # Package marker
│   ├── __main__.py             # python -m flashscore_scraper entry point
│   ├── config.py               # Configuration (dataclass + env vars)
│   ├── scraper.py              # Playwright scraper (async)
│   ├── sheets.py               # Google Sheets integration
│   ├── sort_sheet.py           # Sheet sorting by date
│   ├── main.py                 # CLI entry point
│   ├── batch_scrape.py         # Multi-day batch scraper
│   ├── read_sheet.py           # Utility to inspect Google Sheet
│   ├── test_scraper.py         # Debug test script
│   └── test_sheets.py          # Sheets connectivity test
├── scripts/
│   ├── run_scraper.sh          # Runner script for cron/systemd
│   ├── install_cron.sh         # Install scheduled tasks
│   ├── flashscore-scraper.service  # Systemd service
│   └── flashscore-scraper.timer    # Systemd timer
├── pyproject.toml              # Package definition & dependencies
├── requirements.txt            # Legacy dependency list
├── Dockerfile                  # Docker image (Python/Playwright)
├── docker-compose.yml          # Docker orchestration
├── .env.example                # Environment template
├── credentials.json            # Google service account (gitignored)
├── output/                     # JSON output directory
└── logs/                       # Log files directory
```

## Commands

```bash
# Install (recommended)
pip install -e .
playwright install chromium

# Run from anywhere
flashscore-scraper                                       # Full: scrape + sheets
flashscore-scraper --scrape-only                         # Only scrape, save JSON
flashscore-scraper --sheets-only --json=file.json        # Only inject
flashscore-scraper --days=-2                             # Custom date offset

# Or without pip install, from project root:
python -m flashscore_scraper
python -m flashscore_scraper --scrape-only

# Docker
docker compose up --build
```

## Scheduling (Cron/Systemd)

The scraper can be scheduled to run daily using either cron or systemd:

```bash
# Install systemd timer (recommended) - runs daily at 8:00 AM
./scripts/install_cron.sh systemd

# Or install cron job
./scripts/install_cron.sh cron

# Remove all scheduled tasks
./scripts/install_cron.sh remove

# Check systemd timer status
systemctl --user status flashscore-scraper.timer

# View logs
journalctl --user -u flashscore-scraper.service
cat logs/scraper_$(date +%Y-%m-%d).log

# Run manually
./scripts/run_scraper.sh
```

### Docker Scheduling (Alternative)

```bash
# Start with ofelia scheduler (runs at 1:00 AM daily)
docker compose --profile scheduled up -d
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SPREADSHEET_ID` | Google Sheet ID | (required) |
| `GOOGLE_CREDENTIALS_PATH` | Path to credentials.json | `./credentials.json` |
| `HEADLESS` | Run browser headless | `true` |
| `MAX_MATCHES` | Limit matches (0=unlimited) | `0` |
| `SHEET_PRESET` | Column preset | `SCRAPING OU4` |
| `START_ROW` | Data start row | `2` |

## Code Patterns

### Async/Await
All scraper functions use `async/await` with Playwright's async API:
```python
async def scrape_flashscore(headless: bool = True) -> list[MatchWithStats]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        # ...
```

### TypedDict for Type Hints
```python
class SetStats(TypedDict):
    count3: int
    count4: int
    count5: int
```

### Configuration via Dataclass
```python
@dataclass
class Config:
    google: GoogleConfig
    scraper: ScraperConfig
    sheets: SheetsConfig
```

### Relative Imports
All imports within the package use relative imports:
```python
from .config import config
from .scraper import scrape_flashscore
```

## CSS Selectors (FlashScore)

All CSS selectors are centralized in the `SELECTORS` dict at the top of `flashscore_scraper/scraper.py`.

When FlashScore changes their HTML, update the `SELECTORS` dict only — every Python call and JS `page.evaluate()` reads from it.

The dict is organized by page context:
- `matches` — main volleyball page (match rows, league headers, team names)
- `navigation` — date navigation buttons
- `standings` — league standings table
- `h2h` — head-to-head page (sections, rows, results, show-more button)

A `validate_selectors()` function runs at startup and warns if critical selectors match 0 elements.

---

## Guidelines for Claude

### 0. Communication Style

- When uncertain about requirements, ask clarifying questions before implementing.
- Summarize what you plan to do before making multi-file changes.
- Keep explanations concise unless asked for detail.

### 1. Always Commit Your Changes

**IMPORTANT**: After making any code changes, you MUST commit them yourself. Do not wait for the user to ask.

```bash
# After editing files, always run:
git add -A
git commit -m "Descriptive commit message

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### 2. Commit Message Format

Use clear, descriptive commit messages:
- Start with a verb (Add, Fix, Update, Remove, Refactor)
- Keep first line under 72 characters
- Add details in body if needed
- Always include the Co-Authored-By line

### 3. Before Making Changes

- Read the relevant files first
- Understand the existing patterns
- Check if similar code exists elsewhere

### 4. Code Style

- Use type hints for function parameters and returns
- Follow existing patterns in the codebase
- Use async/await consistently for Playwright operations
- Keep functions focused and single-purpose

### 5. Testing Changes

After making changes, suggest running:
```bash
python -m flashscore_scraper --scrape-only  # Integration test
```

### 6. Don't Overengineer

- Make minimal changes to achieve the goal
- Don't add features that weren't requested
- Don't refactor unrelated code

### 7. Security

- Never commit credentials.json or .env files
- Don't log sensitive data
- Validate external inputs

### 8. Error Handling

- Use try/except for external operations (network, file I/O)
- Log errors with context (URL, match name, etc.)
- Return sensible defaults on failure (e.g., `{'count3': 0, 'count4': 0, 'count5': 0}`)
- When a command or test fails, read the full error output before attempting a fix
- Do not retry the same approach more than twice without asking for guidance
