#!/usr/bin/env python3
"""
One-time setup: write header row to the all-sports log spreadsheet
and verify the sheet is accessible.

Usage:
    python -m flashscore_scraper.scripts.setup_all_sports_log
    # or from project root:
    python scripts/setup_all_sports_log.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from flashscore_scraper.config import config
from flashscore_scraper.sheets import (
    ALL_SPORTS_LOG_HEADER,
    _LOG_LAST_COL,
    _get_sheet_props,
    _write_values,
    get_google_sheets_client,
)

SPREADSHEET_ID = config.google.all_sports_log_spreadsheet_id
TAB_NAME = config.google.all_sports_log_tab_name


def main() -> None:
    if not SPREADSHEET_ID:
        print('ERROR: ALL_SPORTS_LOG_SPREADSHEET_ID is not set in .env')
        sys.exit(1)

    print(f'Connecting to spreadsheet: {SPREADSHEET_ID}')
    print(f'Tab: {TAB_NAME}')

    sheets = get_google_sheets_client()

    # List available tabs
    meta = sheets.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID, includeGridData=False
    ).execute()
    tabs = [s['properties']['title'] for s in meta.get('sheets', [])]
    print(f'Available tabs: {tabs}')

    if TAB_NAME not in tabs:
        print(f'ERROR: tab "{TAB_NAME}" not found.')
        print(f'Please set ALL_SPORTS_LOG_SHEET_TAB to one of: {tabs}')
        sys.exit(1)

    sheet_props = _get_sheet_props(sheets, SPREADSHEET_ID, TAB_NAME)
    sheet_id = sheet_props['sheetId']

    print(f'Writing {len(ALL_SPORTS_LOG_HEADER)} column headers (A–{_LOG_LAST_COL})...')
    _write_values(
        sheets,
        SPREADSHEET_ID,
        sheet_id,
        [
            {
                'start_col': 'A',
                'end_col': _LOG_LAST_COL,
                'start_row': 1,
                'values': [ALL_SPORTS_LOG_HEADER],
            }
        ],
    )

    print('Done! Header row written:')
    for i, col in enumerate(ALL_SPORTS_LOG_HEADER):
        print(f'  {i + 1:>2}. {col}')


if __name__ == '__main__':
    main()
