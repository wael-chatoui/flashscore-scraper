#!/usr/bin/env python3
"""
FlashScore Volleyball Scraper - Main Entry Point

Usage:
    flashscore-scraper                                # Full mode: scrape today's matches + sheets
    flashscore-scraper --today                        # Scrape today's matches (J+0)
    flashscore-scraper --days=-2                      # Scrape matches from 2 days ago (J-2)
    flashscore-scraper --days=2                       # Scrape matches 2 days from now (J+2)
    flashscore-scraper --scrape-only                  # Only scrape, save to JSON
    flashscore-scraper --sheets-only --json=file.json # Only inject to sheets from JSON

    # Or: python -m flashscore_scraper [args]
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

from .config import config
from .sheets import inject_original_formulas, inject_to_google_sheets
from .sort_sheet import sort_sheet_by_date


def print_summary(match_data: list[dict[str, Any]], sport: str = 'volleyball') -> None:
    """Print summary of scraped data"""
    print('\n' + '=' * 50)
    print('SUMMARY')
    print('=' * 50)
    print(f'Total matches: {len(match_data)}')

    # Group by country/league
    by_league: dict[str, int] = {}
    for m in match_data:
        key = f'{m.get("country", "")} - {m.get("league", "")}'
        by_league[key] = by_league.get(key, 0) + 1

    print('\nMatches by league:')
    for league, count in by_league.items():
        print(f'  {league}: {count}')

    # Sample match
    if match_data:
        sample = match_data[0]
        print('\nSample match:')
        print(f'  {sample.get("teamA", "")} vs {sample.get("teamB", "")}')
        print(f'  Date: {sample.get("date", "")} {sample.get("time", "")}')
        team_a_stats = sample.get('teamAStats', {})
        team_b_stats = sample.get('teamBStats', {})
        c3, c4, c5 = (team_a_stats.get(k, 0) for k in ('count3', 'count4', 'count5'))
        if sport == 'hockey':
            print(f'  Team A goals: <=5={c3}, =6={c4}, >=7={c5}')
        else:
            print(f'  Team A sets: 3={c3}, 4={c4}, 5={c5}')
        c3, c4, c5 = (team_b_stats.get(k, 0) for k in ('count3', 'count4', 'count5'))
        if sport == 'hockey':
            print(f'  Team B goals: <=5={c3}, =6={c4}, >=7={c5}')
        else:
            print(f'  Team B sets: 3={c3}, 4={c4}, 5={c5}')
        if sport != 'hockey':
            h2h_stats = sample.get('h2hStats', {})
            c3, c4, c5 = (h2h_stats.get(k, 0) for k in ('count3', 'count4', 'count5'))
            print(f'  H2H sets: 3={c3}, 4={c4}, 5={c5}')


async def main() -> None:
    """Main entry point"""
    args = sys.argv[1:]
    scrape_only = '--scrape-only' in args
    sheets_only = '--sheets-only' in args
    scrape_today = '--today' in args

    # Parse --sport=hockey|volleyball argument
    sport = config.scraper.sport  # default from env/config
    for arg in args:
        if arg.startswith('--sport='):
            sport = arg.split('=', 1)[1]
            break
    is_hockey = sport == 'hockey'

    # Parse --days=N argument for custom offset
    days_offset = 0  # Default: today (J+0)
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

    sport_label = 'Hockey' if is_hockey else 'Volleyball'
    print('=' * 50)
    print(f'FlashScore {sport_label} Scraper')
    print('=' * 50)
    print(f'Run time: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}')
    offset_label = 'today' if days_offset == 0 else f'J{days_offset:+d}'
    print(f'Target date: {target_date.strftime("%d/%m/%Y")} ({offset_label})')
    mode = (
        'Scrape only' if scrape_only else 'Sheets only' if sheets_only else 'Full (scrape + sheets)'
    )
    print(f'Mode: {mode}')
    print('=' * 50)

    match_data: list[dict[str, Any]] = []

    # Step 1: Scrape data (unless sheets-only mode)
    if not sheets_only:
        date_str = target_date.strftime('%d/%m/%Y')
        print(f'\n[1/4] Scraping FlashScore {sport_label.lower()} matches for {date_str}...\n')

        if is_hockey:
            from .hockey_scraper import scrape_hockey

            match_data = await scrape_hockey(days_offset=days_offset)
        else:
            from .scraper import scrape_flashscore

            match_data = await scrape_flashscore(days_offset=days_offset)

        print(f'\nScraped {len(match_data)} matches')

        # Save to JSON file in output/ at project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, 'output')
        os.makedirs(output_dir, exist_ok=True)
        file_prefix = 'hockey_matches' if is_hockey else 'matches'
        output_file = os.path.join(
            output_dir, f'{file_prefix}_{target_date.strftime("%Y-%m-%d")}.json'
        )
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(match_data, f, indent=2, ensure_ascii=False)
        print(f'Data saved to {output_file}')

        if scrape_only:
            print('\n--scrape-only flag set. Skipping Google Sheets injection.')
            print_summary(match_data, sport)
            return

    # Step 2: Inject to Google Sheets (unless scrape-only mode)
    if not scrape_only:
        print('\n[2/4] Injecting data into Google Sheets...\n')

        # Load from JSON if sheets-only mode
        if sheets_only and json_file:
            with open(json_file, encoding='utf-8') as f:
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

        # Hockey uses HOCKEY UND preset by default
        if is_hockey and config.sheets.preset not in ('HOCKEY UND',):
            config.sheets.preset = 'HOCKEY UND'

        inject_to_google_sheets(match_data, config.sheets.start_row)

        # Sort sheet by date after injection
        print('\n[3/4] Sorting sheet by date...\n')
        sort_sheet_by_date(preset_name=config.sheets.preset or 'ORIGINAL')

        # Inject formulas AFTER sorting (skip for hockey — client has own formulas)
        if not is_hockey:
            print('\n[4/4] Injecting formulas...\n')
            inject_original_formulas()
        else:
            print('\n[4/4] Skipping formula injection (hockey).\n')

    print_summary(match_data, sport)
    print('\nDone!')


def cli() -> None:
    """Console script entry point for `flashscore-scraper` command."""
    try:
        asyncio.run(main())
    except Exception as err:
        print(f'Fatal error: {err}')
        sys.exit(1)


if __name__ == '__main__':
    cli()
