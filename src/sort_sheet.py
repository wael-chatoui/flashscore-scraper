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


def parse_date(date_str: str):
    """Parse date string in various formats to datetime object."""
    from datetime import datetime

    if not date_str:
        return None

    # Clean up the string (remove trailing quotes/apostrophes)
    date_str = date_str.strip().rstrip("'\"")

    # Try various formats
    formats = [
        '%d/%m/%Y',   # 21/01/2026
        '%d/%m/%y',   # 21/01/26 or 22/1/26
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def format_date(dt) -> str:
    """Format datetime to DD/MM/YYYY."""
    if dt is None:
        return ''
    return dt.strftime('%d/%m/%Y')


def sort_sheet_by_date(descending: bool = False, sheet_name: str = None) -> None:
    """
    Sort Google Sheet by date column.
    Reads all data, sorts by parsed date values, and rewrites.

    Args:
        descending: Sort newest first if True
        sheet_name: Override sheet name
    """
    spreadsheet_id = get_spreadsheet_id()
    sheets = get_google_sheets_client()

    # Use ORIGINAL preset for SPREADSHEET_ID_2
    preset = COLUMN_PRESETS['ORIGINAL']
    target_sheet = sheet_name or 'TRI BASE O/U 4'

    # Get date column index from preset (column A)
    date_col = preset['matchInfo']['date']
    date_col_index = col_to_index(date_col)

    print(f"Sorting '{target_sheet}' by column {date_col} ({'descending' if descending else 'ascending'})...")
    print(f"  Spreadsheet: SPREADSHEET_ID_2")

    # Read all data
    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{target_sheet}'"
    ).execute()

    values = result.get('values', [])
    if len(values) < 2:
        print("No data to sort")
        return

    # Separate header and data rows
    header = values[0]
    data_rows = values[1:]

    print(f"  Rows to sort: {len(data_rows)}")

    # Sort data rows by parsed date
    def sort_key(row):
        if len(row) > date_col_index:
            dt = parse_date(row[date_col_index])
            if dt:
                return (dt.year, dt.month, dt.day)
        return (0, 0, 0)

    sorted_rows = sorted(data_rows, key=sort_key, reverse=descending)

    # Standardize date format to DD/MM/YYYY
    for row in sorted_rows:
        if len(row) > date_col_index and row[date_col_index]:
            dt = parse_date(row[date_col_index])
            if dt:
                row[date_col_index] = format_date(dt)

    # Combine header with sorted data
    all_rows = [header] + sorted_rows

    # Write back to sheet
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{target_sheet}'!A1",
        valueInputOption='RAW',
        body={'values': all_rows}
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
