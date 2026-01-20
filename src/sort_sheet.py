#!/usr/bin/env python3
"""
Sort Google Sheet data by date column.
Targets SPREADSHEET_ID_2 (client's original spreadsheet).

Usage:
    python sort_sheet.py                    # Sort by date (ascending)
    python sort_sheet.py --desc             # Sort by date (descending)
    python sort_sheet.py --sheet "Name"     # Sort specific sheet tab
"""

import os
import sys
from sheets import get_google_sheets_client, COLUMN_PRESETS
from config import config


def get_spreadsheet_id() -> str:
    """Get SPREADSHEET_ID_2 (client's original spreadsheet)"""
    spreadsheet_id = os.getenv('SPREADSHEET_ID_2')
    if not spreadsheet_id:
        raise ValueError('SPREADSHEET_ID_2 not configured. Set it in .env')
    return spreadsheet_id


def get_sheet_id(sheets_service, spreadsheet_id: str, sheet_name: str) -> int:
    """Get the numeric sheet ID from sheet name"""
    result = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    for sheet in result.get('sheets', []):
        props = sheet.get('properties', {})
        if props.get('title') == sheet_name:
            return props.get('sheetId')

    raise ValueError(f"Sheet '{sheet_name}' not found")


def col_to_index(col_letter: str) -> int:
    """Convert column letter (A, B, ..., Z, AA, AB, ...) to 0-based index"""
    result = 0
    for char in col_letter.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1


def sort_sheet_by_date(descending: bool = False, sheet_name: str = None) -> None:
    """
    Sort Google Sheet by date column using native Sheets API sort.
    Preserves formulas and only reorders rows.

    Args:
        descending: Sort newest first if True
        sheet_name: Override sheet name
    """
    spreadsheet_id = get_spreadsheet_id()
    sheets = get_google_sheets_client()

    # Use ORIGINAL preset for SPREADSHEET_ID_2
    preset = COLUMN_PRESETS['ORIGINAL']
    target_sheet = sheet_name or preset['sheetName']

    sheet_id = get_sheet_id(sheets, spreadsheet_id, target_sheet)

    # Get date column index from preset (column A)
    date_col = preset['matchInfo']['date']
    date_col_index = col_to_index(date_col)

    # Get sheet dimensions
    sheet_metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=[f"'{target_sheet}'"],
        includeGridData=False
    ).execute()

    sheet_props = sheet_metadata['sheets'][0]['properties']['gridProperties']
    row_count = sheet_props.get('rowCount', 1000)
    col_count = sheet_props.get('columnCount', 50)

    # Start from row 2 (skip header), 0-indexed
    start_row = 1

    print(f"Sorting '{target_sheet}' by column {date_col} ({'descending' if descending else 'ascending'})...")
    print(f"  Spreadsheet: SPREADSHEET_ID_2")
    print(f"  Sheet ID: {sheet_id}")
    print(f"  Date column: {date_col} (index {date_col_index})")
    print(f"  Rows: {start_row + 1} to {row_count}")

    # Sort request
    sort_request = {
        'requests': [{
            'sortRange': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': start_row,
                    'endRowIndex': row_count,
                    'startColumnIndex': 0,
                    'endColumnIndex': col_count
                },
                'sortSpecs': [{
                    'dimensionIndex': date_col_index,
                    'sortOrder': 'DESCENDING' if descending else 'ASCENDING'
                }]
            }
        }]
    }

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=sort_request
    ).execute()

    print("Done! Sheet sorted by date.")


def main():
    args = sys.argv[1:]

    if '--help' in args or '-h' in args:
        print(__doc__)
        return

    descending = '--desc' in args or '--descending' in args

    sheet_name = None
    for i, arg in enumerate(args):
        if arg == '--sheet' and i + 1 < len(args):
            sheet_name = args[i + 1]
            break

    sort_sheet_by_date(descending=descending, sheet_name=sheet_name)


if __name__ == '__main__':
    main()
