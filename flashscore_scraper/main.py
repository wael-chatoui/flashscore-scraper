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

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any

from .config import config, setup_logging
from .sheets import inject_original_formulas, inject_to_google_sheets
from .sort_sheet import sort_sheet_by_date

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog='flashscore-scraper',
        description='Scrape volleyball/hockey matches from FlashScore and inject into Sheets.',
    )
    parser.add_argument(
        '--scrape-only', action='store_true', help='Only scrape, save to JSON (skip Sheets)'
    )
    parser.add_argument(
        '--sheets-only', action='store_true', help='Only inject to Sheets from JSON'
    )
    parser.add_argument('--today', action='store_true', help="Scrape today's matches (J+0)")
    parser.add_argument(
        '--days', type=int, default=0, help='Day offset from today (e.g. -2 for 2 days ago)'
    )
    parser.add_argument(
        '--sport',
        choices=['volleyball', 'hockey', 'football'],
        default=config.scraper.sport,
        help='Sport to scrape (default: from SPORT env var)',
    )
    parser.add_argument('--json', dest='json_file', help='JSON file to inject (with --sheets-only)')
    return parser


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
        if sport in ('hockey', 'football'):
            a_scores = sample.get('teamAScores', [])
            b_scores = sample.get('teamBScores', [])
            print(f'  Team A scores ({len(a_scores)}): {a_scores[:5]}...')
            print(f'  Team B scores ({len(b_scores)}): {b_scores[:5]}...')
        else:
            team_a_stats = sample.get('teamAStats', {})
            team_b_stats = sample.get('teamBStats', {})
            c3, c4, c5 = (team_a_stats.get(k, 0) for k in ('count3', 'count4', 'count5'))
            print(f'  Team A sets: 3={c3}, 4={c4}, 5={c5}')
            c3, c4, c5 = (team_b_stats.get(k, 0) for k in ('count3', 'count4', 'count5'))
            print(f'  Team B sets: 3={c3}, 4={c4}, 5={c5}')
            h2h_stats = sample.get('h2hStats', {})
            c3, c4, c5 = (h2h_stats.get(k, 0) for k in ('count3', 'count4', 'count5'))
            print(f'  H2H sets: 3={c3}, 4={c4}, 5={c5}')


async def main() -> None:
    """Main entry point"""
    parser = build_parser()
    args = parser.parse_args()

    scrape_only = args.scrape_only
    sheets_only = args.sheets_only
    sport = args.sport
    is_hockey = sport == 'hockey'
    is_football = sport == 'football'
    days_offset = 0 if args.today else args.days
    json_file = args.json_file
    target_date = datetime.now() + timedelta(days=days_offset)

    sport_label = 'Hockey' if is_hockey else 'Football' if is_football else 'Volleyball'
    logger.info('=' * 50)
    logger.info('FlashScore %s Scraper', sport_label)
    logger.info('=' * 50)
    logger.info('Run time: %s', datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
    offset_label = 'today' if days_offset == 0 else f'J{days_offset:+d}'
    logger.info('Target date: %s (%s)', target_date.strftime('%d/%m/%Y'), offset_label)
    mode = (
        'Scrape only' if scrape_only else 'Sheets only' if sheets_only else 'Full (scrape + sheets)'
    )
    logger.info('Mode: %s', mode)
    logger.info('=' * 50)

    match_data: list[dict[str, Any]] = []

    # Step 1: Scrape data (unless sheets-only mode)
    if not sheets_only:
        date_str = target_date.strftime('%d/%m/%Y')
        logger.info('\n[1/4] Scraping FlashScore %s matches for %s...\n', sport_label.lower(), date_str)

        if is_hockey:
            from .hockey_scraper import scrape_hockey

            match_data = await scrape_hockey(days_offset=days_offset)
        elif is_football:
            from .football_scraper import scrape_football

            match_data = await scrape_football(days_offset=days_offset)
        else:
            from .scraper import scrape_flashscore

            match_data = await scrape_flashscore(days_offset=days_offset)

        logger.info('Scraped %d matches', len(match_data))

        # Save to JSON file in output/ at project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, 'output')
        os.makedirs(output_dir, exist_ok=True)
        file_prefix = 'hockey_matches' if is_hockey else 'football_matches' if is_football else 'matches'
        output_file = os.path.join(
            output_dir, f'{file_prefix}_{target_date.strftime("%Y-%m-%d")}.json'
        )
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(match_data, f, indent=2, ensure_ascii=False)
        logger.info('Data saved to %s', output_file)

        if scrape_only:
            logger.info('--scrape-only flag set. Skipping Google Sheets injection.')
            print_summary(match_data, sport)
            return

    # Step 2: Inject to Google Sheets (unless scrape-only mode)
    if not scrape_only:
        logger.info('\n[2/4] Injecting data into Google Sheets...\n')

        # Load from JSON if sheets-only mode
        if sheets_only and json_file:
            with open(json_file, encoding='utf-8') as f:
                match_data = json.load(f)
            logger.info('Loaded %d matches from %s', len(match_data), json_file)

        if not match_data:
            logger.info('No match data to inject. Run with scrape first or provide --json=file.json')
            return

        if not config.google.spreadsheet_id:
            logger.error('SPREADSHEET_ID not configured!')
            logger.error('Please set SPREADSHEET_ID in .env file or environment variable')
            logger.info('Your scraped data has been saved to JSON file.')
            return

        # Hockey uses HOCKEY RAW preset and separate spreadsheet
        if is_hockey and config.sheets.preset not in ('HOCKEY RAW',):
            config.sheets.preset = 'HOCKEY RAW'
        # Football uses FOOTBALL preset and separate spreadsheet
        if is_football and config.sheets.preset not in ('FOOTBALL',):
            config.sheets.preset = 'FOOTBALL'

        override_sheet_id = None
        if is_hockey:
            override_sheet_id = config.google.hockey_spreadsheet_id
        elif is_football:
            override_sheet_id = config.google.football_spreadsheet_id

        inject_to_google_sheets(
            match_data, config.sheets.start_row, spreadsheet_id=override_sheet_id
        )

        # Sort sheet by date after injection
        logger.info('\n[3/4] Sorting sheet by date...\n')
        sort_sheet_by_date(
            descending=True,
            preset_name=config.sheets.preset or 'ORIGINAL',
            spreadsheet_id=override_sheet_id,
        )

        # Inject formulas AFTER sorting (skip for hockey/football — client has own formulas)
        if not is_hockey and not is_football:
            logger.info('\n[4/4] Injecting formulas...\n')
            inject_original_formulas()
        else:
            logger.info('\n[4/4] Skipping formula injection (%s).\n', sport)

    print_summary(match_data, sport)
    logger.info('Done!')


def cli() -> None:
    """Console script entry point for `flashscore-scraper` command."""
    setup_logging()
    try:
        asyncio.run(main())
    except Exception as err:
        logger.error('Fatal error: %s', err)
        sys.exit(1)


if __name__ == '__main__':
    cli()
