#!/usr/bin/env python3
"""
Utility script to read and inspect the Google Sheet structure.

Usage:
    python read_sheet.py                    # Read first sheet
    python read_sheet.py "Sheet Name"       # Read specific sheet
    python read_sheet.py --list             # List all sheet tabs
"""

import os
import sys
import json
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import config


def get_google_sheets_client():
    """Authenticate with Google Sheets API"""
    cred_path = config.google.credentials_path
    credentials = None

    if cred_path and os.path.exists(cred_path):
        credentials = service_account.Credentials.from_service_account_file(
            cred_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
    elif os.getenv('GOOGLE_CREDENTIALS_JSON'):
        cred_info = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
        credentials = service_account.Credentials.from_service_account_info(
            cred_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
    else:
        from google.auth import default
        credentials, _ = default(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])

    return build('sheets', 'v4', credentials=credentials)


def list_sheets(spreadsheet_id: str) -> list[dict]:
    """List all sheet tabs in the spreadsheet"""
    sheets = get_google_sheets_client()
    result = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    sheet_list = []
    for sheet in result.get('sheets', []):
        props = sheet.get('properties', {})
        sheet_list.append({
            'title': props.get('title'),
            'sheetId': props.get('sheetId'),
            'index': props.get('index'),
            'rowCount': props.get('gridProperties', {}).get('rowCount'),
            'columnCount': props.get('gridProperties', {}).get('columnCount')
        })
    return sheet_list


def read_sheet(spreadsheet_id: str, sheet_name: str = None, range_str: str = None) -> dict[str, Any]:
    """Read data from a sheet"""
    sheets = get_google_sheets_client()

    # If no sheet name, get the first one
    if not sheet_name:
        sheet_list = list_sheets(spreadsheet_id)
        if sheet_list:
            sheet_name = sheet_list[0]['title']
        else:
            raise ValueError("No sheets found in spreadsheet")

    # Build range
    if range_str:
        full_range = f"'{sheet_name}'!{range_str}"
    else:
        full_range = f"'{sheet_name}'!A1:BZ100"  # Read first 100 rows, columns A-BZ

    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=full_range
    ).execute()

    return {
        'sheet_name': sheet_name,
        'range': result.get('range'),
        'values': result.get('values', [])
    }


def col_letter(index: int) -> str:
    """Convert column index (0-based) to letter (A, B, ..., Z, AA, AB, ...)"""
    result = ""
    while index >= 0:
        result = chr(index % 26 + ord('A')) + result
        index = index // 26 - 1
    return result


def print_sheet_structure(data: dict[str, Any], max_rows: int = 20) -> None:
    """Print sheet structure in a readable format"""
    values = data.get('values', [])

    print(f"\n{'='*60}")
    print(f"Sheet: {data['sheet_name']}")
    print(f"Range: {data['range']}")
    print(f"Total rows: {len(values)}")
    print(f"{'='*60}\n")

    if not values:
        print("(empty sheet)")
        return

    # Find max columns
    max_cols = max(len(row) for row in values) if values else 0

    # Print header row with column letters
    print("     ", end="")
    for col_idx in range(min(max_cols, 50)):  # Limit to 50 columns
        print(f"{col_letter(col_idx):>12}", end="")
    print("\n" + "-" * (5 + min(max_cols, 50) * 12))

    # Print rows
    for row_idx, row in enumerate(values[:max_rows]):
        print(f"{row_idx + 1:4} |", end="")
        for col_idx in range(min(max_cols, 50)):
            val = row[col_idx] if col_idx < len(row) else ""
            # Truncate long values
            val_str = str(val)[:10] if val else ""
            print(f"{val_str:>12}", end="")
        print()

    if len(values) > max_rows:
        print(f"\n... ({len(values) - max_rows} more rows)")


def main():
    if not config.google.spreadsheet_id:
        print("ERROR: SPREADSHEET_ID not configured!")
        print("Set it in .env file or as environment variable")
        sys.exit(1)

    spreadsheet_id = config.google.spreadsheet_id
    args = sys.argv[1:]

    print(f"Spreadsheet ID: {spreadsheet_id}")

    # List sheets mode
    if '--list' in args:
        print("\nAvailable sheets:")
        print("-" * 60)
        for sheet in list_sheets(spreadsheet_id):
            print(f"  - {sheet['title']}")
            print(f"      Rows: {sheet['rowCount']}, Columns: {sheet['columnCount']}")
        return

    # Read specific sheet or first sheet
    sheet_name = None
    for arg in args:
        if not arg.startswith('--'):
            sheet_name = arg
            break

    # Check for --all flag to read all sheets
    if '--all' in args:
        for sheet in list_sheets(spreadsheet_id):
            data = read_sheet(spreadsheet_id, sheet['title'])
            print_sheet_structure(data)
    else:
        data = read_sheet(spreadsheet_id, sheet_name)
        print_sheet_structure(data)


if __name__ == '__main__':
    main()
