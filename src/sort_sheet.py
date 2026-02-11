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
    Sort Google Sheet by date column using the native Sheets API SortRange request.
    This sorts in-place, preserving all formulas and formatting.

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

    # Get the numeric sheet ID needed for batchUpdate
    sheet_id = get_sheet_id(sheets, spreadsheet_id, target_sheet)

    # Get sheet dimensions to know the data range
    sheet_meta = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=[f"'{target_sheet}'"],
        includeGridData=False
    ).execute()
    grid_props = sheet_meta['sheets'][0]['properties']['gridProperties']
    row_count = grid_props['rowCount']
    col_count = grid_props['columnCount']

    sort_order = 'DESCENDING' if descending else 'ASCENDING'

    # Use native SortRange request - sorts in-place, preserves formulas
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            'requests': [{
                'sortRange': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 1,  # skip header row
                        'endRowIndex': row_count,
                        'startColumnIndex': 0,
                        'endColumnIndex': col_count
                    },
                    'sortSpecs': [{
                        'dimensionIndex': date_col_index,
                        'sortOrder': sort_order
                    }]
                }
            }]
        }
    ).execute()

    print("Done! Sheet sorted by date (formulas preserved).")


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
