#!/usr/bin/env python3
"""
FlashScore Volleyball Scraper - Main Entry Point

Usage:
    python main.py                     # Full mode: scrape tomorrow's matches (J+1) + sheets
    python main.py --today             # Scrape today's matches (J+0)
    python main.py --days=-2           # Scrape matches from 2 days ago (J-2)
    python main.py --days=2            # Scrape matches 2 days from now (J+2)
    python main.py --scrape-only       # Only scrape, save to JSON
    python main.py --sheets-only --json=file.json  # Only inject to sheets from JSON
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

from config import config
from scraper import scrape_flashscore
from sheets import inject_to_google_sheets
from sort_sheet import sort_sheet_by_date


def print_summary(match_data: list[dict[str, Any]]) -> None:
    """Print summary of scraped data"""
    print('\n' + '=' * 50)
    print('SUMMARY')
    print('=' * 50)
    print(f'Total matches: {len(match_data)}')

    # Group by country/league
    by_league: dict[str, int] = {}
    for m in match_data:
        key = f"{m.get('country', '')} - {m.get('league', '')}"
        by_league[key] = by_league.get(key, 0) + 1

    print('\nMatches by league:')
    for league, count in by_league.items():
        print(f'  {league}: {count}')

    # Sample match
    if match_data:
        sample = match_data[0]
        print('\nSample match:')
        print(f"  {sample.get('teamA', '')} vs {sample.get('teamB', '')}")
        print(f"  Date: {sample.get('date', '')} {sample.get('time', '')}")
        team_a_stats = sample.get('teamAStats', {})
        team_b_stats = sample.get('teamBStats', {})
        h2h_stats = sample.get('h2hStats', {})
        print(f"  Team A sets: 3={team_a_stats.get('count3', 0)}, 4={team_a_stats.get('count4', 0)}, 5={team_a_stats.get('count5', 0)}")
        print(f"  Team B sets: 3={team_b_stats.get('count3', 0)}, 4={team_b_stats.get('count4', 0)}, 5={team_b_stats.get('count5', 0)}")
        print(f"  H2H sets: 3={h2h_stats.get('count3', 0)}, 4={h2h_stats.get('count4', 0)}, 5={h2h_stats.get('count5', 0)}")


async def main() -> None:
    """Main entry point"""
    args = sys.argv[1:]
    scrape_only = '--scrape-only' in args
    sheets_only = '--sheets-only' in args
    scrape_today = '--today' in args

    # Parse --days=N argument for custom offset
    days_offset = 1  # Default: tomorrow (J+1)
    for arg in args:
        if arg.startswith('--days='):
            try:
                days_offset = int(arg.split('=', 1)[1])
            except ValueError:
                print(f'Invalid --days value: {arg}')
                sys.exit(1)
            break

    # --today is shorthand for --days=0
    if scrape_today:
        days_offset = 0

    target_date = datetime.now() + timedelta(days=days_offset)

    # Parse --json=file.json argument
    json_file = None
    for arg in args:
        if arg.startswith('--json='):
            json_file = arg.split('=', 1)[1]
            break

    print('=' * 50)
    print('FlashScore Volleyball Scraper')
    print('=' * 50)
    print(f"Run time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    offset_label = 'today' if days_offset == 0 else f'J{days_offset:+d}'
    print(f"Target date: {target_date.strftime('%d/%m/%Y')} ({offset_label})")
    mode = 'Scrape only' if scrape_only else 'Sheets only' if sheets_only else 'Full (scrape + sheets)'
    print(f'Mode: {mode}')
    print('=' * 50)

    match_data: list[dict[str, Any]] = []

    # Step 1: Scrape data (unless sheets-only mode)
    if not sheets_only:
        print(f"\n[1/3] Scraping FlashScore volleyball matches for {target_date.strftime('%d/%m/%Y')}...\n")

        match_data = await scrape_flashscore(days_offset=days_offset)

        print(f'\nScraped {len(match_data)} matches')

        # Save to JSON file (in output dir if exists, otherwise current dir)
        # Use target date in filename (the date of the matches, not today)
        output_dir = './output' if os.path.exists('./output') else '.'
        output_file = os.path.join(output_dir, f"matches_{target_date.strftime('%Y-%m-%d')}.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(match_data, f, indent=2, ensure_ascii=False)
        print(f'Data saved to {output_file}')

        if scrape_only:
            print('\n--scrape-only flag set. Skipping Google Sheets injection.')
            print_summary(match_data)
            return

    # Step 2: Inject to Google Sheets (unless scrape-only mode)
    if not scrape_only:
        print('\n[2/3] Injecting data into Google Sheets...\n')

        # Load from JSON if sheets-only mode
        if sheets_only and json_file:
            with open(json_file, 'r', encoding='utf-8') as f:
                match_data = json.load(f)
            print(f'Loaded {len(match_data)} matches from {json_file}')

        if not match_data:
            print('No match data to inject. Run with scrape first or provide --json=file.json')
            return

        if not config.google.spreadsheet_id:
            print('ERROR: SPREADSHEET_ID not configured!')
            print('Please set SPREADSHEET_ID in .env file or environment variable')
            print('\nYour scraped data has been saved to JSON file.')
            return

        inject_to_google_sheets(match_data, config.sheets.start_row)

        # Sort sheet by date after injection
        print('\n[3/3] Sorting sheet by date...\n')
        sort_sheet_by_date(descending=True)

    print_summary(match_data)
    print('\nDone!')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as err:
        print(f'Fatal error: {err}')
        sys.exit(1)
