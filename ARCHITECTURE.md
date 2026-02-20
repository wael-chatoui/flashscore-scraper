# Architecture

## Overview

FlashScore Volleyball Scraper is a Python CLI tool that scrapes volleyball match data and head-to-head statistics from FlashScore.fr, then injects them into Google Sheets with computed formulas.

## Module Map

```
flashscore_scraper/
├── main.py           CLI orchestrator (arg parsing, workflow sequencing)
├── __main__.py       python -m entry point → asyncio.run(main())
├── config.py         Configuration system (dataclasses + .env)
├── scraper.py        Playwright browser automation (async)
├── sheets.py         Google Sheets API (inject, dedup, formulas)
├── sort_sheet.py     Sheet sorting + blank row cleanup
├── batch_scrape.py   Multi-day scraping over date ranges
├── read_sheet.py     Utility: inspect sheet structure
├── test_scraper.py   Debug: scrape without sheets
├── test_sheets.py    Debug: validate sheets connectivity
├── debug_h2h.py      Debug: verify H2H extraction
└── read_new_data.py  Debug: check injected columns
```

## Data Flow

```
                        ┌───────────────────┐
                        │   main.py (CLI)    │
                        └─────────┬─────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                    ▼
        [1. Scrape]        [2. Inject]          [3. Sort + Formulas]
              │                   │                    │
        scraper.py          sheets.py           sort_sheet.py
              │                   │              sheets.py
              ▼                   ▼                    ▼
       FlashScore.fr      Google Sheets API     Google Sheets API
              │                   │                    │
              ▼                   ▼                    ▼
     output/*.json         Write cell data      SortRange + formulas
```

### Step 1: Scraping (`scraper.py`)

1. Launch headless Chromium via Playwright
2. Navigate to FlashScore.fr volleyball page
3. Click date navigation buttons to reach target date
4. Extract matches via `page.evaluate()` (JS in browser context)
5. For each match's league, scrape standings for team rankings
6. For each match, navigate to H2H page and extract set statistics
7. Return `list[MatchWithStats]`, save to JSON

### Step 2: Injection (`sheets.py`)

1. Delete existing rows with matching dates (deduplication)
2. Map match data to column positions using the active preset
3. Batch-write match info, Team A stats, Team B stats, H2H stats
4. Ensure sheet has enough rows before writing

### Step 3: Sort + Formulas (`sort_sheet.py`, `sheets.py`)

1. Delete blank rows (columns A-H all empty)
2. Normalize date text → date serial values
3. Sort entire sheet by column A ascending
4. Inject computed formulas (ORIGINAL preset only): ECART, MG, Ratios

## Key Data Types

```python
class SetStats(TypedDict):
    count3: int    # Matches ending in 3 sets (3-0)
    count4: int    # Matches ending in 4 sets (3-1)
    count5: int    # Matches ending in 5 sets (3-2)

class Match(TypedDict):
    date: str      # DD/MM/YYYY
    time: str
    country: str
    league: str
    teamA: str
    rankA: str
    teamB: str
    rankB: str
    matchUrl: str

class MatchStats(TypedDict):
    teamAStats: SetStats
    teamBStats: SetStats
    h2hStats: SetStats

class MatchWithStats(Match, MatchStats):
    pass
```

## Configuration

Loaded from `.env` via `config.py` dataclasses:

```
Config
├── GoogleConfig     → spreadsheet_id, credentials_path
├── ScraperConfig    → request_delay (ms), max_matches
└── SheetsConfig     → preset, tab_name, start_row
```

**Column presets** (`sheets.py`) define different spreadsheet layouts:
- `ORIGINAL` — Full layout with computed formulas (AU-BF)
- `SCRAPING OU4` — Modified test layout
- `CALCUL SET` — Minimal CSV-style layout

## CSS Selectors

All FlashScore selectors live in the `SELECTORS` dict at the top of `scraper.py`, organized by page context (`matches`, `navigation`, `standings`, `h2h`). A `validate_selectors()` function warns at startup if critical selectors match nothing.

## Entry Points

| Command | What it does |
|---------|-------------|
| `flashscore-scraper` | Full run: scrape + inject + sort + formulas |
| `flashscore-scraper --scrape-only` | Scrape to JSON only |
| `flashscore-scraper --sheets-only --json=file.json` | Inject from JSON |
| `flashscore-scraper --days=-2` | Scrape a specific date offset |
| `python -m flashscore_scraper.batch_scrape --from=-7 --to=0` | Multi-day batch |

## Deployment

- **Local**: `pip install -e . && playwright install chromium`
- **Systemd timer**: `./scripts/install_cron.sh systemd` (daily at 1:00 AM UTC)
- **Cron**: `./scripts/install_cron.sh cron`
- **Docker**: `docker compose up --build` (with optional ofelia scheduler)

### Production VPS

| Detail | Value |
|--------|-------|
| Host | `root@76.13.46.236` (srv1332492) |
| OS | Ubuntu 24.04.3 LTS |
| RAM | 3.8 GB |
| Disk | 48 GB (50% used) |
| Docker | 29.2.1 + Compose v5.0.2 |
| Project path | `/root/flashscore-scraper` |
| Branch | `main` |
| Schedule | Daily 1:00 AM UTC via ofelia |

**Containers:**
- `flashscore-volleyball-scraper` — runs the scraper, exits after completion
- `flashscore-scheduler` — ofelia daemon, triggers scraper container daily

**Config files (on VPS only, not in git):**
- `.env` — SPREADSHEET_ID, SHEET_PRESET, etc.
- `credentials.json` — Google service account key

**Docker image:** Based on `mcr.microsoft.com/playwright/python:v1.49.0-noble`
- Installs package via `pip install .`
- Installs Chromium via `playwright install chromium`
- Runs as non-root `scraper` user

**Output:** JSON files in `/root/flashscore-scraper/output/` (one per day)

**Deploy:**
```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && git pull && docker compose --profile scheduled up -d --build"
```

**Logs:**
```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose logs --tail=50 scraper"
```
