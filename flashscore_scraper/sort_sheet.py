#!/usr/bin/env python3
"""
Sort Google Sheet data by date column.

Usage:
    python sort_sheet.py                    # Sort by date (ascending)
    python sort_sheet.py --desc             # Sort by date (descending)
    python sort_sheet.py --sheet "Name"     # Sort specific sheet tab
"""

import logging
import os
import re
import sys

from .sheets import (
    COLUMN_PRESETS,
    _col_to_index,
    _get_sheet_props,
    _read_values,
    _write_values,
    get_google_sheets_client,
)

logger = logging.getLogger(__name__)


def _index_to_col(index: int) -> str:
    """Convert 0-based column index to letter (inverse of _col_to_index)."""
    result = ''
    index += 1  # convert to 1-based
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord('A') + remainder) + result
    return result


def get_spreadsheet_id() -> str:
    """Get SPREADSHEET_ID from environment"""
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    if not spreadsheet_id:
        raise ValueError('SPREADSHEET_ID not configured. Set it in .env')
    return spreadsheet_id


# Keep col_to_index as a public alias (used by tests)
col_to_index = _col_to_index


def _clean_date(value: str) -> str:
    """Fix common date issues: trailing quotes, 2-digit years.

    '04/02/26"' → '04/02/2026'
    '27/02/2026' → '27/02/2026' (unchanged)
    """
    v = value.strip().rstrip('"')
    # Convert 2-digit year to 4-digit: dd/mm/yy → dd/mm/20yy
    m = re.match(r'^(\d{2}/\d{2}/)(\d{2})$', v)
    if m:
        v = m.group(1) + '20' + m.group(2)
    return v


def normalize_dates(sheets, spreadsheet_id: str, sheet_id: int, date_col: str) -> None:
    """
    Re-write date column with USER_ENTERED so text dates become real date values.
    This ensures SortRange sorts chronologically, not alphabetically.
    Only touches column A (date column), preserves all other columns/formulas.
    Also fixes trailing quotes and 2-digit years from earlier scraping runs.
    """
    values = _read_values(
        sheets,
        spreadsheet_id,
        sheet_id,
        date_col,
        start_row=2,
        major_dimension='COLUMNS',
    )
    if not values or not values[0]:
        return

    col_values = values[0]
    cleaned = [_clean_date(v) for v in col_values]
    fixed = sum(1 for old, new in zip(col_values, cleaned) if old != new)
    if fixed:
        logger.info('  Fixed %d malformed dates (trailing quotes / 2-digit years)', fixed)
    # Write back only the date column with USER_ENTERED to convert text→date
    _write_values(
        sheets,
        spreadsheet_id,
        sheet_id,
        [
            {
                'start_col': date_col,
                'end_col': date_col,
                'start_row': 2,
                'values': [[v] for v in cleaned],
            }
        ],
    )
    logger.info('  Normalized %d date values in column %s', len(cleaned), date_col)


def delete_blank_rows(
    sheets, spreadsheet_id: str, sheet_id: int, date_col: str, preset_name: str = 'ORIGINAL',
) -> None:
    """Delete rows that are blank or incomplete (date only, no team names).

    A row is considered deletable if:
    - All cells in the read range are empty (fully blank), OR
    - It has a date but both team name columns are empty (incomplete).
    """
    preset = COLUMN_PRESETS.get(preset_name, COLUMN_PRESETS['ORIGINAL'])
    match_info = preset.get('matchInfo') or {}

    # Determine team column indices (relative to start of read range, which is col A = 0)
    team_a_col = match_info.get('teamA', 'E')
    team_b_col = match_info.get('teamB', 'G')
    team_a_idx = _col_to_index(team_a_col)
    team_b_idx = _col_to_index(team_b_col)
    date_idx = _col_to_index(date_col)

    # Extend read range to cover team columns (may be beyond H)
    max_col_idx = max(7, team_a_idx, team_b_idx)  # 7 = column H (0-based)
    end_col = _index_to_col(max_col_idx)

    rows = _read_values(
        sheets,
        spreadsheet_id,
        sheet_id,
        'A',
        end_col,
        start_row=2,
        major_dimension='ROWS',
    )

    def _cell(row: list, idx: int) -> str:
        return row[idx].strip() if idx < len(row) else ''

    def _is_deletable(row: list | None) -> bool:
        """True if row is fully blank or has a date but no team names."""
        if not row:
            return True
        if not any(cell.strip() for cell in row):
            return True
        # Incomplete: date present but both team columns empty
        return bool(_cell(row, date_idx)) and not _cell(row, team_a_idx) and not _cell(row, team_b_idx)

    # Find deletable row ranges, work bottom-up
    blank_ranges = []
    i = len(rows) - 1
    while i >= 0:
        if _is_deletable(rows[i]):
            end = i
            while i >= 0 and _is_deletable(rows[i]):
                i -= 1
            start = i + 1
            # +2 because rows are 0-indexed from row 2
            blank_ranges.append((start + 2, end + 2))
        else:
            i -= 1

    if not blank_ranges:
        logger.info('  No blank/incomplete rows to delete')
        return

    total_deleted = sum(end - start + 1 for start, end in blank_ranges)
    logger.info('  Deleting %d blank/incomplete rows in %d range(s)', total_deleted, len(blank_ranges))

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
    date_col_index = _col_to_index(date_col)

    order = 'descending' if descending else 'ascending'
    logger.info("Sorting '%s' by column %s (%s)...", target_sheet, date_col, order)
    logger.info('  Spreadsheet: %s...', spreadsheet_id[:8])

    # Resolve sheet name → numeric sheetId
    sheet_props = _get_sheet_props(sheets, spreadsheet_id, target_sheet)
    sheet_id = sheet_props['sheetId']

    # Step 1: Delete blank rows
    logger.info('  Cleaning up blank rows...')
    delete_blank_rows(sheets, spreadsheet_id, sheet_id, date_col, preset_name)

    # Step 2: Normalize dates so text dates become real date serial values
    logger.info('  Normalizing dates for correct sort order...')
    normalize_dates(sheets, spreadsheet_id, sheet_id, date_col)

    # Step 3: Get updated sheet dimensions after deletions
    sheet_props = _get_sheet_props(sheets, spreadsheet_id, target_sheet)
    row_count = sheet_props['gridProperties']['rowCount']
    col_count = sheet_props['gridProperties']['columnCount']

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
                        'sortSpecs': [
                            {
                                'dimensionIndex': date_col_index,
                                'sortOrder': sort_order,
                            }
                        ],
                    }
                }
            ]
        },
    ).execute()

    logger.info('Done! Sheet sorted by date (formulas preserved).')


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
