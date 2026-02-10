#!/usr/bin/env python3
"""
Test Google Sheets connectivity for all configured spreadsheets.

Usage:
    python test_sheets.py
"""

import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))


def get_sheets_client():
    cred_path = os.getenv('GOOGLE_CREDENTIALS_PATH', './credentials.json')
    # Resolve relative to project root
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


def main():
    spreadsheets = {
        'SPREADSHEET_ID':   os.getenv('SPREADSHEET_ID', ''),
        'SPREADSHEET_ID_2': os.getenv('SPREADSHEET_ID_2', ''),
        'SPREADSHEET_ID_3': os.getenv('SPREADSHEET_ID_3', ''),
    }

    print("Testing Google Sheets connectivity...\n")
    client = get_sheets_client()

    all_ok = True
    for name, sid in spreadsheets.items():
        if not test_spreadsheet(client, name, sid):
            all_ok = False
        print()

    if all_ok:
        print("All spreadsheets OK.")
    else:
        print("Some spreadsheets FAILED. Check credentials and sharing permissions.")
        sys.exit(1)


if __name__ == '__main__':
    main()
