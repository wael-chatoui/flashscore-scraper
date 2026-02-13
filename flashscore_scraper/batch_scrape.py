#!/usr/bin/env python3
"""
Batch scrape multiple days and inject all data at once.

Usage:
    python batch_scrape.py --from=-18 --to=1              # Scrape + inject
    python batch_scrape.py --from=-18 --to=1 --scrape-only  # Only scrape to JSON
    python batch_scrape.py --inject-only                   # Inject existing JSONs
"""

import asyncio
import json
import os
import sys
import glob
from datetime import datetime, timedelta

from .config import config
from .scraper import scrape_flashscore
from .sheets import inject_to_google_sheets, inject_original_formulas
from .sort_sheet import sort_sheet_by_date


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')


def parse_args():
    args = sys.argv[1:]
    from_days = None
    to_days = None
    scrape_only = '--scrape-only' in args
    inject_only = '--inject-only' in args

    for arg in args:
        if arg.startswith('--from='):
            from_days = int(arg.split('=', 1)[1])
        elif arg.startswith('--to='):
            to_days = int(arg.split('=', 1)[1])

    return from_days, to_days, scrape_only, inject_only


async def scrape_day(days_offset: int) -> list[dict]:
    """Scrape a single day and save to JSON. Returns match data."""
    target_date = datetime.now() + timedelta(days=days_offset)
    date_str = target_date.strftime('%Y-%m-%d')
    display_date = target_date.strftime('%d/%m/%Y')
    json_path = os.path.join(OUTPUT_DIR, f'matches_{date_str}.json')

    print(f'\n{"="*50}')
    print(f'Scraping {display_date} (J{days_offset:+d})...')
    print(f'{"="*50}')

    try:
        match_data = await scrape_flashscore(days_offset=days_offset)
        print(f'  Found {len(match_data)} matches')

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(match_data, f, indent=2, ensure_ascii=False)
        print(f'  Saved to {json_path}')

        return match_data
    except Exception as e:
        print(f'  ERROR scraping {display_date}: {e}')
        return []


def load_all_jsons() -> list[dict]:
    """Load all JSON files from output directory."""
    all_data = []
    json_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, 'matches_*.json')))

    print(f'\nLoading {len(json_files)} JSON files...')
    for path in json_files:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f'  {os.path.basename(path)}: {len(data)} matches')
        all_data.extend(data)

    return all_data


async def main():
    from_days, to_days, scrape_only, inject_only = parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not inject_only:
        if from_days is None or to_days is None:
            print('Usage: python batch_scrape.py --from=-18 --to=1')
            sys.exit(1)

        total_days = to_days - from_days + 1
        print(f'Batch scrape: {total_days} days (J{from_days:+d} to J{to_days:+d})')
        print(f'Mode: {"scrape only" if scrape_only else "scrape + inject"}')

        # Phase 1: Scrape all days to JSON
        for d in range(from_days, to_days + 1):
            await scrape_day(d)

        print(f'\n{"="*50}')
        print('All days scraped!')
        print(f'{"="*50}')

        if scrape_only:
            return

    # Phase 2: Combine and inject
    all_data = load_all_jsons()
    print(f'\nTotal matches to inject: {len(all_data)}')

    if not all_data:
        print('No data to inject.')
        return

    if not config.google.spreadsheet_id:
        print('ERROR: SPREADSHEET_ID not configured!')
        sys.exit(1)

    print('\nInjecting all data into Google Sheets (single batch)...')
    inject_to_google_sheets(all_data, config.sheets.start_row)

    print('\nSorting sheet by date (once)...')
    sort_sheet_by_date()

    print('\nInjecting formulas (after sort)...')
    inject_original_formulas()

    print(f'\nDone! Injected {len(all_data)} matches total.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nInterrupted.')
        sys.exit(1)
    except Exception as err:
        print(f'Fatal error: {err}')
        sys.exit(1)
