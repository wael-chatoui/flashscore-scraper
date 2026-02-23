#!/usr/bin/env python3
"""
Sort Google Sheet data by date column.

Usage:
    python sort_sheet.py                    # Sort by date (ascending)
    python sort_sheet.py --desc             # Sort by date (descending)
    python sort_sheet.py --sheet "Name"     # Sort specific sheet tab
"""

import os
import sys

from .sheets import COLUMN_PRESETS, get_google_sheets_client


def get_spreadsheet_id() -> str:
    """Get SPREADSHEET_ID from environment"""
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    if not spreadsheet_id:
        raise ValueError('SPREADSHEET_ID not configured. Set it in .env')
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


def normalize_dates(sheets, spreadsheet_id: str, sheet_name: str, date_col: str) -> None:
    """
    Re-write date column with USER_ENTERED so text dates become real date values.
    This ensures SortRange sorts chronologically, not alphabetically.
    Only touches column A (date column), preserves all other columns/formulas.
    """
    result = (
        sheets.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!{date_col}2:{date_col}",
            majorDimension='COLUMNS',
        )
        .execute()
    )
    values = result.get('values', [[]])
    if not values or not values[0]:
        return

    col_values = values[0]
    # Write back only the date column with USER_ENTERED to convert text→date
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!{date_col}2:{date_col}{len(col_values) + 1}",
        valueInputOption='USER_ENTERED',
        body={'values': [[v] for v in col_values]},
    ).execute()
    print(f'  Normalized {len(col_values)} date values in column {date_col}')


def delete_blank_rows(
    sheets, spreadsheet_id: str, sheet_id: int, sheet_name: str, date_col: str
) -> None:
    """Delete rows where the date column and all match info columns (A-H) are empty."""
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A2:H", majorDimension='ROWS')
        .execute()
    )
    rows = result.get('values', [])

    # Find blank row ranges (where A-H are all empty), work bottom-up
    blank_ranges = []
    i = len(rows) - 1
    while i >= 0:
        row = rows[i]
        is_blank = not any(cell.strip() for cell in row) if row else True
        if is_blank:
            end = i
            while i >= 0:
                row = rows[i]
                is_blank = not any(cell.strip() for cell in row) if row else True
                if not is_blank:
                    break
                i -= 1
            start = i + 1
            # +2 because rows are 0-indexed from row 2
            blank_ranges.append((start + 2, end + 2))
        else:
            i -= 1

    if not blank_ranges:
        print('  No blank rows to delete')
        return

    total_deleted = sum(end - start + 1 for start, end in blank_ranges)
    print(f'  Deleting {total_deleted} blank rows in {len(blank_ranges)} range(s)')

    # Build delete requests (already bottom-up so indices stay valid)
    requests = []
    for start_row, end_row in blank_ranges:
        requests.append(
            {
                'deleteDimension': {
                    'range': {
                        'sheetId': sheet_id,
                        'dimension': 'ROWS',
                        'startIndex': start_row - 1,  # 0-indexed
                        'endIndex': end_row,  # exclusive
                    }
                }
            }
        )

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={'requests': requests}
    ).execute()


def sort_sheet_by_date(
    descending: bool = False,
    sheet_name: str = None,
    preset_name: str = 'ORIGINAL',
    spreadsheet_id: str = None,
) -> None:
    """
    Sort Google Sheet by date column using the native Sheets API SortRange request.
    This sorts in-place, preserving all formulas and formatting.

    Steps:
    1. Delete blank rows (empty A-H) to avoid gaps
    2. Normalize dates in column A (text → real date values) for correct sort
    3. Sort using native SortRange API

    Args:
        descending: Sort newest first if True
        sheet_name: Override sheet name
        preset_name: Column preset key (default: 'ORIGINAL')
        spreadsheet_id: Override spreadsheet ID
    """
    spreadsheet_id = spreadsheet_id or get_spreadsheet_id()
    sheets = get_google_sheets_client()

    preset = COLUMN_PRESETS.get(preset_name, COLUMN_PRESETS['ORIGINAL'])
    target_sheet = sheet_name or preset['sheetName']

    # Get date column index from preset (column A)
    date_col = preset['matchInfo']['date']
    date_col_index = col_to_index(date_col)

    order = 'descending' if descending else 'ascending'
    print(f"Sorting '{target_sheet}' by column {date_col} ({order})...")
    print(f'  Spreadsheet: {spreadsheet_id[:8]}...')

    # Get the numeric sheet ID needed for batchUpdate
    sheet_id = get_sheet_id(sheets, spreadsheet_id, target_sheet)

    # Step 1: Delete blank rows
    print('  Cleaning up blank rows...')
    delete_blank_rows(sheets, spreadsheet_id, sheet_id, target_sheet, date_col)

    # Step 2: Normalize dates so text dates become real date serial values
    print('  Normalizing dates for correct sort order...')
    normalize_dates(sheets, spreadsheet_id, target_sheet, date_col)

    # Step 3: Get updated sheet dimensions after deletions
    sheet_meta = (
        sheets.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, ranges=[f"'{target_sheet}'"], includeGridData=False)
        .execute()
    )
    grid_props = sheet_meta['sheets'][0]['properties']['gridProperties']
    row_count = grid_props['rowCount']
    col_count = grid_props['columnCount']

    sort_order = 'DESCENDING' if descending else 'ASCENDING'

    # Step 4: Sort using native SortRange - preserves formulas
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            'requests': [
                {
                    'sortRange': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 1,  # skip header row
                            'endRowIndex': row_count,
                            'startColumnIndex': 0,
                            'endColumnIndex': col_count,
                        },
                        'sortSpecs': [{'dimensionIndex': date_col_index, 'sortOrder': sort_order}],
                    }
                }
            ]
        },
    ).execute()

    print('Done! Sheet sorted by date (formulas preserved).')


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
