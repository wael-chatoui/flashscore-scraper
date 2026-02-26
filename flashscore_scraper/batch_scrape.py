#!/usr/bin/env python3
"""
Batch scrape multiple days and inject all data at once.

Usage:
    python batch_scrape.py --from=-18 --to=1              # Scrape + inject
    python batch_scrape.py --from=-18 --to=1 --scrape-only  # Only scrape to JSON
    python batch_scrape.py --inject-only                   # Inject existing JSONs
"""

import argparse
import asyncio
import glob
import json
import logging
import os
import sys
from datetime import datetime, timedelta

from .config import config, setup_logging
from .sheets import inject_original_formulas, inject_to_google_sheets
from .sort_sheet import sort_sheet_by_date

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for batch scraping."""
    parser = argparse.ArgumentParser(
        prog='batch-scrape',
        description='Batch scrape multiple days and inject all data at once.',
    )
    parser.add_argument('--from', type=int, dest='from_days', help='Start day offset (e.g. -18)')
    parser.add_argument('--to', type=int, dest='to_days', help='End day offset (e.g. 1)')
    parser.add_argument(
        '--scrape-only', action='store_true', help='Only scrape to JSON (skip Sheets injection)'
    )
    parser.add_argument(
        '--inject-only', action='store_true', help='Only inject existing JSONs to Sheets'
    )
    parser.add_argument(
        '--sport',
        choices=['volleyball', 'hockey'],
        default=config.scraper.sport,
        help='Sport to scrape (default: from SPORT env var)',
    )
    return parser


async def scrape_day(days_offset: int, sport: str = 'volleyball') -> list[dict]:
    """Scrape a single day and save to JSON. Returns match data."""
    target_date = datetime.now() + timedelta(days=days_offset)
    date_str = target_date.strftime('%Y-%m-%d')
    display_date = target_date.strftime('%d/%m/%Y')
    file_prefix = 'hockey_matches' if sport == 'hockey' else 'matches'
    json_path = os.path.join(OUTPUT_DIR, f'{file_prefix}_{date_str}.json')

    logger.info('\n%s', '=' * 50)
    logger.info('Scraping %s %s (J%+d)...', sport, display_date, days_offset)
    logger.info('%s', '=' * 50)

    try:
        if sport == 'hockey':
            from .hockey_scraper import scrape_hockey

            match_data = await scrape_hockey(days_offset=days_offset)
        else:
            from .scraper import scrape_flashscore

            match_data = await scrape_flashscore(days_offset=days_offset)
        logger.info('  Found %d matches', len(match_data))

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(match_data, f, indent=2, ensure_ascii=False)
        logger.info('  Saved to %s', json_path)

        return match_data
    except Exception as e:
        logger.error('ERROR scraping %s: %s', display_date, e)
        return []


def load_all_jsons(sport: str = 'volleyball') -> list[dict]:
    """Load all JSON files from output directory."""
    all_data = []
    pattern = 'hockey_matches_*.json' if sport == 'hockey' else 'matches_*.json'
    json_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, pattern)))

    logger.info('Loading %d JSON files...', len(json_files))
    for path in json_files:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        logger.debug('  %s: %d matches', os.path.basename(path), len(data))
        all_data.extend(data)

    return all_data


async def main():
    parser = build_parser()
    args = parser.parse_args()
    from_days = args.from_days
    to_days = args.to_days
    scrape_only = args.scrape_only
    inject_only = args.inject_only
    sport = args.sport
    is_hockey = sport == 'hockey'

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not inject_only:
        if from_days is None or to_days is None:
            parser.error('--from and --to are required when not using --inject-only')

        total_days = to_days - from_days + 1
        logger.info('Batch scrape (%s): %d days (J%+d to J%+d)', sport, total_days, from_days, to_days)
        logger.info('Mode: %s', 'scrape only' if scrape_only else 'scrape + inject')

        # Phase 1: Scrape all days to JSON
        for d in range(from_days, to_days + 1):
            await scrape_day(d, sport)

        logger.info('\n%s', '=' * 50)
        logger.info('All days scraped!')
        logger.info('%s', '=' * 50)

        if scrape_only:
            return

    # Phase 2: Combine and inject
    all_data = load_all_jsons(sport)
    logger.info('Total matches to inject: %d', len(all_data))

    if not all_data:
        logger.info('No data to inject.')
        return

    if not config.google.spreadsheet_id:
        logger.error('SPREADSHEET_ID not configured!')
        sys.exit(1)

    if is_hockey and config.sheets.preset not in ('HOCKEY UND',):
        config.sheets.preset = 'HOCKEY UND'

    logger.info('Injecting all data into Google Sheets (single batch)...')
    inject_to_google_sheets(all_data, config.sheets.start_row)

    preset_name = config.sheets.preset or 'ORIGINAL'
    logger.info('Sorting sheet by date (once)...')
    sort_sheet_by_date(preset_name=preset_name)

    if not is_hockey:
        logger.info('Injecting formulas (after sort)...')
        inject_original_formulas()

    logger.info('Done! Injected %d %s matches total.', len(all_data), sport)


if __name__ == '__main__':
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Interrupted.')
        sys.exit(1)
    except Exception as err:
        logger.error('Fatal error: %s', err)
        sys.exit(1)
