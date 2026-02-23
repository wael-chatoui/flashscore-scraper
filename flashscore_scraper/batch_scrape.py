#!/usr/bin/env python3
"""
Batch scrape multiple days and inject all data at once.

Usage:
    python batch_scrape.py --from=-18 --to=1              # Scrape + inject
    python batch_scrape.py --from=-18 --to=1 --scrape-only  # Only scrape to JSON
    python batch_scrape.py --inject-only                   # Inject existing JSONs
"""

import asyncio
import glob
import json
import os
import sys
from datetime import datetime, timedelta

from .config import config
from .sheets import inject_original_formulas, inject_to_google_sheets
from .sort_sheet import sort_sheet_by_date

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')


def parse_args():
    args = sys.argv[1:]
    from_days = None
    to_days = None
    scrape_only = '--scrape-only' in args
    inject_only = '--inject-only' in args

    # Parse --sport=hockey|volleyball
    sport = config.scraper.sport
    for arg in args:
        if arg.startswith('--sport='):
            sport = arg.split('=', 1)[1]
        elif arg.startswith('--from='):
            from_days = int(arg.split('=', 1)[1])
        elif arg.startswith('--to='):
            to_days = int(arg.split('=', 1)[1])

    return from_days, to_days, scrape_only, inject_only, sport


async def scrape_day(days_offset: int, sport: str = 'volleyball') -> list[dict]:
    """Scrape a single day and save to JSON. Returns match data."""
    target_date = datetime.now() + timedelta(days=days_offset)
    date_str = target_date.strftime('%Y-%m-%d')
    display_date = target_date.strftime('%d/%m/%Y')
    file_prefix = 'hockey_matches' if sport == 'hockey' else 'matches'
    json_path = os.path.join(OUTPUT_DIR, f'{file_prefix}_{date_str}.json')

    print(f'\n{"=" * 50}')
    print(f'Scraping {sport} {display_date} (J{days_offset:+d})...')
    print(f'{"=" * 50}')

    try:
        if sport == 'hockey':
            from .hockey_scraper import scrape_hockey

            match_data = await scrape_hockey(days_offset=days_offset)
        else:
            from .scraper import scrape_flashscore

            match_data = await scrape_flashscore(days_offset=days_offset)
        print(f'  Found {len(match_data)} matches')

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(match_data, f, indent=2, ensure_ascii=False)
        print(f'  Saved to {json_path}')

        return match_data
    except Exception as e:
        print(f'  ERROR scraping {display_date}: {e}')
        return []


def load_all_jsons(sport: str = 'volleyball') -> list[dict]:
    """Load all JSON files from output directory."""
    all_data = []
    pattern = 'hockey_matches_*.json' if sport == 'hockey' else 'matches_*.json'
    json_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, pattern)))

    print(f'\nLoading {len(json_files)} JSON files...')
    for path in json_files:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        print(f'  {os.path.basename(path)}: {len(data)} matches')
        all_data.extend(data)

    return all_data


async def main():
    from_days, to_days, scrape_only, inject_only, sport = parse_args()
    is_hockey = sport == 'hockey'

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not inject_only:
        if from_days is None or to_days is None:
            print('Usage: python batch_scrape.py --from=-18 --to=1 [--sport=hockey]')
            sys.exit(1)

        total_days = to_days - from_days + 1
        print(f'Batch scrape ({sport}): {total_days} days (J{from_days:+d} to J{to_days:+d})')
        print(f'Mode: {"scrape only" if scrape_only else "scrape + inject"}')

        # Phase 1: Scrape all days to JSON
        for d in range(from_days, to_days + 1):
            await scrape_day(d, sport)

        print(f'\n{"=" * 50}')
        print('All days scraped!')
        print(f'{"=" * 50}')

        if scrape_only:
            return

    # Phase 2: Combine and inject
    all_data = load_all_jsons(sport)
    print(f'\nTotal matches to inject: {len(all_data)}')

    if not all_data:
        print('No data to inject.')
        return

    if not config.google.spreadsheet_id:
        print('ERROR: SPREADSHEET_ID not configured!')
        sys.exit(1)

    if is_hockey and config.sheets.preset not in ('HOCKEY UND',):
        config.sheets.preset = 'HOCKEY UND'

    print('\nInjecting all data into Google Sheets (single batch)...')
    inject_to_google_sheets(all_data, config.sheets.start_row)

    preset_name = config.sheets.preset or 'ORIGINAL'
    print('\nSorting sheet by date (once)...')
    sort_sheet_by_date(preset_name=preset_name)

    if not is_hockey:
        print('\nInjecting formulas (after sort)...')
        inject_original_formulas()

    print(f'\nDone! Injected {len(all_data)} {sport} matches total.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nInterrupted.')
        sys.exit(1)
    except Exception as err:
        print(f'Fatal error: {err}')
        sys.exit(1)
