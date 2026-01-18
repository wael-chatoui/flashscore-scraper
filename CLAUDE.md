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
scriping-sports/
├── src/
│   ├── __init__.py       # Package marker
│   ├── config.py         # Configuration (dataclass + env vars)
│   ├── scraper.py        # Playwright scraper (async)
│   ├── sheets.py         # Google Sheets integration
│   ├── main.py           # CLI entry point
│   └── test_scraper.py   # Debug test script
├── requirements.txt      # Python dependencies
├── Dockerfile            # Docker image (Python/Playwright)
├── docker-compose.yml    # Docker orchestration
├── .env.example          # Environment template
├── credentials.json      # Google service account (gitignored)
└── output/               # JSON output directory
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run scraper (from src/ directory)
cd src && python main.py                    # Full: scrape + sheets
cd src && python main.py --scrape-only      # Only scrape, save JSON
cd src && python main.py --sheets-only --json=file.json  # Only inject

# Test with visible browser
cd src && python test_scraper.py

# Docker
docker compose up --build
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SPREADSHEET_ID` | Google Sheet ID | (required) |
| `GOOGLE_CREDENTIALS_PATH` | Path to credentials.json | `./credentials.json` |
| `HEADLESS` | Run browser headless | `true` |
| `MAX_MATCHES` | Limit matches (0=unlimited) | `0` |
| `SHEET_PRESET` | Column preset | `TRI BASE OU 4` |
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

## Important CSS Selectors (FlashScore)

- `.event__match` - Match row
- `.event__participant--home` / `--away` - Team names
- `.h2h__section` - H2H section container
- `.h2h__row` - Individual H2H match
- `.h2h__result` - Score (e.g., "3-1")
- `button.wclButtonLink--h2h` - "Show more" button

---

## Guidelines for Claude

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
cd src && python test_scraper.py  # For scraper changes
cd src && python main.py --scrape-only  # For integration test
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
