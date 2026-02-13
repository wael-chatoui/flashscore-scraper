#!/usr/bin/env python3
"""
Test Google Sheets connectivity and validate headers against active preset.

Usage:
    python test_sheets.py
"""

import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

from .sheets import COLUMN_PRESETS


def col_to_index(col: str) -> int:
    """Convert column letter (A, B, ..., AZ) to 0-based index."""
    result = 0
    for c in col.upper():
        result = result * 26 + (ord(c) - ord('A') + 1)
    return result - 1


def get_sheets_client():
    cred_path = os.getenv('GOOGLE_CREDENTIALS_PATH', './credentials.json')
    if not os.path.isabs(cred_path):
        cred_path = os.path.join(os.path.dirname(__file__), '..', cred_path)
    credentials = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    return build('sheets', 'v4', credentials=credentials)


def test_spreadsheet(client, name: str, spreadsheet_id: str) -> bool:
    """Test connectivity to a spreadsheet. Returns True on success."""
    if not spreadsheet_id:
        print(f"  [{name}] SKIP - not set")
        return True

    try:
        result = client.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        title = result.get('properties', {}).get('title', '???')
        sheets = [s['properties']['title'] for s in result.get('sheets', [])]
        print(f"  [{name}] OK")
        print(f"    Title: {title}")
        print(f"    ID:    {spreadsheet_id}")
        print(f"    Tabs:  {', '.join(sheets)}")
        return True
    except Exception as e:
        print(f"  [{name}] FAIL")
        print(f"    ID:    {spreadsheet_id}")
        print(f"    Error: {e}")
        return False


def test_headers(client, spreadsheet_id: str, preset_name: str) -> bool:
    """Read header row and check columns the scraper writes to."""
    preset = COLUMN_PRESETS.get(preset_name)
    if not preset:
        fallback = 'ORIGINAL'
        print(f"\n  WARN: Preset '{preset_name}' not found, falling back to '{fallback}'")
        print(f"  Available: {', '.join(COLUMN_PRESETS.keys())}")
        preset = COLUMN_PRESETS[fallback]
        preset_name = fallback

    sheet_name = preset['sheetName']

    # Read header row
    try:
        result = client.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1:BZ1"
        ).execute()
    except Exception as e:
        print(f"\n  FAIL: Cannot read tab '{sheet_name}': {e}")
        return False

    headers = result.get('values', [[]])[0]

    def get_header(col: str) -> str:
        idx = col_to_index(col)
        if idx < len(headers):
            return headers[idx] or '(empty)'
        return '(out of range)'

    print(f"\n  Headers check for preset '{preset_name}' on tab '{sheet_name}':")
    print(f"  {'Column':<8} {'Purpose':<22} {'Header found'}")
    print(f"  {'-'*8} {'-'*22} {'-'*20}")

    # Collect all target columns with their purpose
    targets = []

    if preset.get('matchInfo'):
        mi = preset['matchInfo']
        labels = {'date': 'Date', 'time': 'Time', 'country': 'Country',
                  'league': 'League', 'teamA': 'Team A', 'rankA': 'Rank A',
                  'teamB': 'Team B', 'rankB': 'Rank B'}
        for key, col in mi.items():
            targets.append((col, f"Match: {labels[key]}", get_header(col)))

    for group, label in [('teamA', 'Team A'), ('teamB', 'Team B'), ('h2h', 'H2H')]:
        for set_key, col in preset[group].items():
            set_num = set_key.replace('set', '')
            targets.append((col, f"{label}: {set_num} sets", get_header(col)))

    ok = True
    for col, purpose, header in targets:
        print(f"  {col:<8} {purpose:<22} {header}")

    # Print full header map for reference
    print(f"\n  Full header row ({len(headers)} columns):")
    for i, h in enumerate(headers):
        if not h:
            continue
        col = ''
        idx = i
        while idx >= 0:
            col = chr(idx % 26 + ord('A')) + col
            idx = idx // 26 - 1
        print(f"    {col:>3}: {h}")

    return ok


def main():
    spreadsheets = {
        'SPREADSHEET_ID':   os.getenv('SPREADSHEET_ID', ''),
    }

    preset_name = os.getenv('SHEET_PRESET', 'ORIGINAL')

    print("Testing Google Sheets connectivity...\n")
    client = get_sheets_client()

    all_ok = True
    for name, sid in spreadsheets.items():
        if not test_spreadsheet(client, name, sid):
            all_ok = False
        print()

    # Header validation on main spreadsheet
    main_sid = spreadsheets['SPREADSHEET_ID']
    if main_sid:
        print(f"{'='*60}")
        print(f"Header validation (SPREADSHEET_ID, preset: {preset_name})")
        print(f"{'='*60}")
        test_headers(client, main_sid, preset_name)

    print()
    if all_ok:
        print("All connectivity tests OK.")
    else:
        print("Some tests FAILED. Check credentials and sharing permissions.")
        sys.exit(1)

    print("\nReview the header mapping above to confirm columns are correct.")


if __name__ == '__main__':
    main()
