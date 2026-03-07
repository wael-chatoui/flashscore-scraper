"""
Google Sheets Integration

Injects scraped volleyball match data into Google Sheets
"""

import json
import logging
import os
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import config

logger = logging.getLogger(__name__)

# Column mapping - configurable based on actual sheet structure
#
# Actual sheet layout for "SCRAPING OU4":
# - A: Date
# - B-H: Formula columns (averages, computed values) - DO NOT OVERWRITE
# - I: Status/Time (e.g., "Terminé", "20:00")
# - J: Country (PAYS)
# - K: League
# - L: Team A name (EQUIPE A)
# - M: Team A rank (P)
# - N: Team B name (EQUIPE B)
# - O: Team B rank (P)
# - T, U, V: Team A stats (3, 4, 5 sets)
# - AE, AF, AG: Team B stats (3, 4, 5 sets)
# - AJ, AK, AL: H2H stats (3, 4, 5 sets)
#
# Alternative mapping for "CALCUL SET":
# - Team A stats: C, D, E
# - Team B stats: I, J, K
# - H2H stats: O, P, Q

COLUMN_PRESETS = {
    # ORIGINAL spreadsheet structure (Spreadsheet 2 - client's original file)
    # GREEN columns only: A-H (match info), M-O (Team A), X-Z (Team B), AJ-AL (H2H)
    # All other columns contain formulas - DO NOT TOUCH
    'ORIGINAL': {
        'sheetName': 'SCRAPING OU4',
        'matchInfo': {
            'date': 'A',
            'time': 'B',
            'country': 'C',
            'league': 'D',
            'teamA': 'E',
            'rankA': 'F',
            'teamB': 'G',
            'rankB': 'H',
        },
        'teamA': {'set3': 'M', 'set4': 'N', 'set5': 'O'},
        'teamB': {'set3': 'X', 'set4': 'Y', 'set5': 'Z'},
        'h2h': {'set3': 'AJ', 'set4': 'AK', 'set5': 'AL'},
    },
    # Modified spreadsheet structure (Spreadsheet 1 - test/modified version)
    # Sheet columns: A=DATE, I=Status, J=PAYS, K=LEAGUE, L=EQUIPE A, M=Rank A, N=EQUIPE B, O=Rank B
    # Stats: T-V=Team A (3,4,5 sets), AE-AG=Team B (3,4,5 sets), AJ-AL=H2H (3,4,5 sets)
    'SCRAPING OU4': {
        'sheetName': 'SCRAPING OU4',
        'matchInfo': {
            'date': 'A',
            'time': 'I',
            'country': 'J',
            'league': 'K',
            'teamA': 'L',
            'rankA': 'M',
            'teamB': 'N',
            'rankB': 'O',
        },
        'teamA': {'set3': 'T', 'set4': 'U', 'set5': 'V'},
        'teamB': {'set3': 'AE', 'set4': 'AF', 'set5': 'AG'},
        'h2h': {'set3': 'AJ', 'set4': 'AK', 'set5': 'AL'},
    },
    # Hockey Under 4.5/5.5/6 preset
    # GREEN columns only: A-J (match info), O-R (Team A), W-Y (Team B)
    # No H2H section — only per-team last-15 stats
    # set2=<=4, set3=<=5, set4==6, set5=>=7
    'HOCKEY UND': {
        'sheetName': 'SCRAPING UND 5.5/6',
        'matchInfo': {
            'date': 'A',
            'time': 'B',
            'sexe': 'C',
            'country': 'D',
            'league': 'E',
            'teamA': 'F',
            'rankA': 'G',
            'teamB': 'H',
            'rankB': 'I',
            'ecart': 'J',
        },
        'teamA': {'set2': 'O', 'set3': 'P', 'set4': 'Q', 'set5': 'R'},
        'teamB': {'set3': 'W', 'set4': 'X', 'set5': 'Y'},
        'h2h': None,
    },
    # Hockey RAW preset — writes raw total-goal values (15 per team)
    # Columns N-AB: Team A's last 15 match total goals (AM1–AM15)
    # Columns AC-AQ: Team B's last 15 match total goals (BM1–BM15)
    # No H2H, no aggregated stats — the sheet's own formulas handle computation
    'HOCKEY RAW': {
        'sheetName': 'SCRAPING UND 5.5/6',
        'matchInfo': {
            'date': 'A',
            'time': 'B',
            'country': 'C',
            'league': 'D',
            'teamA': 'E',
            'rankA': 'F',
            'teamB': 'G',
            'rankB': 'H',
            'ecart': 'I',
        },
        'teamAScores': {'start': 'N', 'end': 'AB', 'count': 15},
        'teamBScores': {'start': 'AC', 'end': 'AQ', 'count': 15},
        'teamA': None,
        'teamB': None,
        'h2h': None,
    },
    # Alternative mapping based on CSV structure
    'CALCUL SET': {
        'sheetName': 'CALCUL SET',
        'matchInfo': None,  # Visual layout - match info not in simple columns
        'teamA': {'set3': 'C', 'set4': 'D', 'set5': 'E'},
        'teamB': {'set3': 'I', 'set4': 'J', 'set5': 'K'},
        'h2h': {'set3': 'O', 'set4': 'P', 'set5': 'Q'},
    },
}


# ---------------------------------------------------------------------------
# Helpers — use numeric sheetId (gridRange) instead of sheet name in ranges.
# Sheet names with special characters (e.g. '/' in "SCRAPING UND 5.5/6")
# break the Google Sheets API range parser regardless of quoting.
# ---------------------------------------------------------------------------


def _col_to_index(col_letter: str) -> int:
    """Convert column letter (A, B, ..., Z, AA, AB, ...) to 0-based index."""
    result = 0
    for char in col_letter.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1


def _get_sheet_props(sheets, spreadsheet_id: str, sheet_name: str) -> dict:
    """Get sheet properties by name without using range notation.

    Returns the 'properties' dict: sheetId, title, gridProperties, etc.
    """
    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id, includeGridData=False).execute()
    for sheet in meta.get('sheets', []):
        props = sheet['properties']
        if props['title'] == sheet_name:
            return props
    raise ValueError(f"Sheet '{sheet_name}' not found")


def _read_values(
    sheets,
    spreadsheet_id: str,
    sheet_id: int,
    start_col: str,
    end_col: str | None = None,
    start_row: int | None = None,
    major_dimension: str = 'COLUMNS',
) -> list:
    """Read cell values using sheetId-based gridRange.

    Avoids putting sheet names in API URLs/ranges, which breaks when
    names contain special characters (e.g. '/' in 'SCRAPING UND 5.5/6').
    """
    end_col = end_col or start_col
    grid_range: dict[str, int] = {
        'sheetId': sheet_id,
        'startColumnIndex': _col_to_index(start_col),
        'endColumnIndex': _col_to_index(end_col) + 1,
    }
    if start_row is not None:
        grid_range['startRowIndex'] = start_row - 1  # 0-based

    result = (
        sheets.spreadsheets()
        .values()
        .batchGetByDataFilter(
            spreadsheetId=spreadsheet_id,
            body={
                'dataFilters': [{'gridRange': grid_range}],
                'majorDimension': major_dimension,
            },
        )
        .execute()
    )

    matches = result.get('valueRanges', [])
    if matches:
        return matches[0].get('valueRange', {}).get('values', [])
    return []


def _write_values(
    sheets,
    spreadsheet_id: str,
    sheet_id: int,
    data: list[dict],
    value_input_option: str = 'USER_ENTERED',
) -> None:
    """Write cell values using sheetId-based gridRange.

    Each item in data must have:
        start_col, end_col: column letters (e.g. 'A', 'H')
        start_row: 1-indexed row number
        values: 2D list of values
    """
    filter_data = []
    for d in data:
        grid_range = {
            'sheetId': sheet_id,
            'startColumnIndex': _col_to_index(d['start_col']),
            'endColumnIndex': _col_to_index(d['end_col']) + 1,
            'startRowIndex': d['start_row'] - 1,  # 0-based
        }
        filter_data.append(
            {
                'dataFilter': {'gridRange': grid_range},
                'values': d['values'],
                'majorDimension': d.get('major_dimension', 'ROWS'),
            }
        )

    sheets.spreadsheets().values().batchUpdateByDataFilter(
        spreadsheetId=spreadsheet_id,
        body={
            'valueInputOption': value_input_option,
            'data': filter_data,
        },
    ).execute()


# ---------------------------------------------------------------------------


def _build_original_formulas(start_row: int, end_row: int) -> list[dict]:
    """Build formula data for ORIGINAL preset computed columns.

    Returns dicts with start_col/end_col/start_row/values for _write_values.
    Covers columns I, L, P-V (Team A), W, AA-AG (Team B), AI, AM-AS (H2H).
    """
    rows = range(start_row, end_row + 1)
    formula_data = []

    # Column I: ECART (rank difference)
    formula_data.append(
        {
            'start_col': 'I',
            'end_col': 'I',
            'start_row': start_row,
            'values': [[f'=F{r}-H{r}'] for r in rows],
        }
    )

    # Column L: N;TOTAL SET A
    formula_data.append(
        {
            'start_col': 'L',
            'end_col': 'L',
            'start_row': start_row,
            'values': [[f'=M{r}*3+N{r}*4+O{r}*5'] for r in rows],
        }
    )

    # Columns P-V: Team A derived stats
    formula_data.append(
        {
            'start_col': 'P',
            'end_col': 'V',
            'start_row': start_row,
            'values': [
                [
                    f'=N{r}+O{r}',  # P: 4+
                    f'=M{r}+N{r}+O{r}',  # Q: TOTAL MATCH
                    f'=IF(Q{r}=0;"";L{r}/Q{r})',  # R: MOY SET MATCH A
                    f'=IF(Q{r}=0;"";M{r}/Q{r})',  # S: MOY 3 SET A
                    f'=IF(Q{r}=0;"";N{r}/Q{r})',  # T: MOY 4 SET A
                    f'=IF(Q{r}=0;"";O{r}/Q{r})',  # U: MOY 5 SET A
                    f'=IF(Q{r}=0;"";P{r}/Q{r})',  # V: MOY 4+
                ]
                for r in rows
            ],
        }
    )

    # Column W: N;TOTAL SET B
    formula_data.append(
        {
            'start_col': 'W',
            'end_col': 'W',
            'start_row': start_row,
            'values': [[f'=X{r}*3+Y{r}*4+Z{r}*5'] for r in rows],
        }
    )

    # Columns AA-AG: Team B derived stats
    formula_data.append(
        {
            'start_col': 'AA',
            'end_col': 'AG',
            'start_row': start_row,
            'values': [
                [
                    f'=Y{r}+Z{r}',  # AA: 4+
                    f'=X{r}+Y{r}+Z{r}',  # AB: TOTAL MATCH B
                    f'=IF(AB{r}=0;"";W{r}/AB{r})',  # AC: MOY SET MATCH B
                    f'=IF(AB{r}=0;"";X{r}/AB{r})',  # AD: MOY 3 B
                    f'=IF(AB{r}=0;"";Y{r}/AB{r})',  # AE: MOY 4 B
                    f'=IF(AB{r}=0;"";Z{r}/AB{r})',  # AF: MOY 5 B
                    f'=IF(AB{r}=0;"";AA{r}/AB{r})',  # AG: MOY 4+ B
                ]
                for r in rows
            ],
        }
    )

    # Column AI: H2H N.TOTAL SET
    formula_data.append(
        {
            'start_col': 'AI',
            'end_col': 'AI',
            'start_row': start_row,
            'values': [[f'=AJ{r}*3+AK{r}*4+AL{r}*5'] for r in rows],
        }
    )

    # Columns AM-AS: H2H derived stats
    formula_data.append(
        {
            'start_col': 'AM',
            'end_col': 'AS',
            'start_row': start_row,
            'values': [
                [
                    f'=AK{r}+AL{r}',  # AM: 4+
                    f'=AJ{r}+AK{r}+AL{r}',  # AN: TOTAL H2H
                    f'=IF(AN{r}=0;"";AI{r}/AN{r})',  # AO: MOY H2H SET
                    f'=IF(AN{r}=0;"";AJ{r}/AN{r})',  # AP: MOY H2H 3 SET
                    f'=IF(AN{r}=0;"";AK{r}/AN{r})',  # AQ: MOY H2H 4 SET
                    f'=IF(AN{r}=0;"";AL{r}/AN{r})',  # AR: MOY H2H 5 SET
                    f'=IF(AN{r}=0;"";AM{r}/AN{r})',  # AS: MOY H2H 4+ SET
                ]
                for r in rows
            ],
        }
    )

    # Columns AU-BA: MG (Moyenne Générale) — combined averages
    formula_data.append(
        {
            'start_col': 'AU',
            'end_col': 'BA',
            'start_row': start_row,
            'values': [
                [
                    f'=AVERAGE(L{r};W{r};AI{r})',  # AU: MG BUT
                    f'=AVERAGE(R{r};AC{r};AO{r})',  # AV: MG SET
                    f'=AVERAGE(S{r};AD{r};AP{r})',  # AW: MG 3
                    f'=AVERAGE(T{r};AE{r};AQ{r})',  # AX: MG 4
                    f'=AVERAGE(U{r};AF{r};AR{r})',  # AY: MG 5
                    f'=AVERAGE(V{r};AG{r};AS{r})',  # AZ: MG 4+
                    f'=AW{r}+AX{r}',  # BA: MG 4-
                ]
                for r in rows
            ],
        }
    )

    # Columns BC-BF: Ratios and Filters
    formula_data.append(
        {
            'start_col': 'BC',
            'end_col': 'BF',
            'start_row': start_row,
            'values': [
                [
                    f'=IF(AY{r}=0;"";AW{r}/AY{r})',  # BC: RATIO U
                    f'=IF(AW{r}=0;"";AY{r}/AW{r})',  # BD: RATIO O
                    f'=IF(AY{r}=0;"";AX{r}/AY{r})',  # BE: Filtre U
                    f'=IF(AW{r}=0;"";AX{r}/AW{r})',  # BF: Filtre 0+
                ]
                for r in rows
            ],
        }
    )

    return formula_data


def get_column_preset() -> dict:
    """Get active preset from config or default"""
    preset_name = config.sheets.preset or 'ORIGINAL'
    return COLUMN_PRESETS.get(preset_name, COLUMN_PRESETS['ORIGINAL'])


def get_google_sheets_client():
    """Authenticate with Google Sheets API"""
    cred_path = config.google.credentials_path
    credentials = None

    if cred_path and os.path.exists(cred_path):
        credentials = service_account.Credentials.from_service_account_file(
            cred_path, scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
    elif os.getenv('GOOGLE_CREDENTIALS_JSON'):
        # Support inline JSON credentials (useful for Docker/cloud)
        cred_info = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
        credentials = service_account.Credentials.from_service_account_info(
            cred_info, scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
    else:
        # Fall back to application default credentials
        from google.auth import default

        credentials, _ = default(scopes=['https://www.googleapis.com/auth/spreadsheets'])

    return build('sheets', 'v4', credentials=credentials)


def find_next_empty_row(sheets, spreadsheet_id: str, sheet_id: int, col: str = 'A') -> int:
    """Find the first empty row in the given column (1-indexed)."""
    values = _read_values(sheets, spreadsheet_id, sheet_id, col, major_dimension='COLUMNS')
    # Length of the column data = last row with content
    return len(values[0]) + 1 if values and values[0] else 2


def _delete_rows_by_date(sheets, spreadsheet_id: str, sheet_id: int, target_date: str) -> int:
    """Delete all rows where column A matches target_date.

    Works bottom-up so that row indices stay valid during deletion.
    Returns the number of deleted rows.
    """
    values = _read_values(sheets, spreadsheet_id, sheet_id, 'A', major_dimension='COLUMNS')
    if not values or not values[0]:
        return 0

    col_a = values[0]

    # Find matching row indices (0-based in col_a, but row 0 = header)
    matching_rows = []
    for i in range(1, len(col_a)):  # skip header at index 0
        cell = str(col_a[i]).strip()
        if cell == target_date:
            matching_rows.append(i + 1)  # convert to 1-indexed sheet row

    if not matching_rows:
        return 0

    # Build delete requests bottom-up (so indices stay valid)
    requests = []
    for row in sorted(matching_rows, reverse=True):
        requests.append(
            {
                'deleteDimension': {
                    'range': {
                        'sheetId': sheet_id,
                        'dimension': 'ROWS',
                        'startIndex': row - 1,  # 0-indexed
                        'endIndex': row,  # exclusive
                    }
                }
            }
        )

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={'requests': requests}
    ).execute()

    return len(matching_rows)


def inject_to_google_sheets(
    match_data: list[dict[str, Any]],
    start_row: int = 2,
    spreadsheet_id: str | None = None,
) -> None:
    """
    Inject scraped data into Google Sheets (only GREEN columns).
    Deduplicates by date: if rows for the same date already exist, they are
    deleted first so re-running replaces rather than duplicates.

    Args:
        match_data: Array of match objects from scraper
        start_row: Minimum starting row (default: 2, assuming row 1 has headers)
        spreadsheet_id: Override spreadsheet ID (e.g. for hockey's separate sheet)
    """
    spreadsheet_id = spreadsheet_id or config.google.spreadsheet_id
    if not spreadsheet_id:
        raise ValueError('SPREADSHEET_ID not configured. Set it in .env or environment variable.')

    sheets = get_google_sheets_client()
    preset = get_column_preset()
    sheet_name = config.sheets.tab_name or preset['sheetName']

    # Filter out matches with empty team names (defensive guard)
    original_count = len(match_data)
    match_data = [m for m in match_data if m.get('teamA', '').strip() and m.get('teamB', '').strip()]
    filtered = original_count - len(match_data)
    if filtered:
        logger.warning('Filtered out %d matches with empty team names', filtered)

    logger.info('Injecting %d matches into "%s"...', len(match_data), sheet_name)
    logger.info('Using column preset: %s', config.sheets.preset or 'ORIGINAL')

    # Resolve sheet name → numeric sheetId (avoids '/' issues in ranges)
    sheet_props = _get_sheet_props(sheets, spreadsheet_id, sheet_name)
    sheet_id = sheet_props['sheetId']

    # Deduplicate: delete existing rows for the same date(s)
    dates_in_batch = {m.get('date', '') for m in match_data if m.get('date')}
    total_deleted = 0
    for date_str in dates_in_batch:
        deleted = _delete_rows_by_date(sheets, spreadsheet_id, sheet_id, date_str)
        total_deleted += deleted
    if total_deleted:
        dates = ', '.join(sorted(dates_in_batch))
        logger.info('Dedup: removed %d existing rows for date(s) %s', total_deleted, dates)

    # Find the next empty row to append after existing data
    next_empty = find_next_empty_row(sheets, spreadsheet_id, sheet_id)
    start_row = max(start_row, next_empty)
    end_row = start_row + len(match_data) - 1
    logger.info('Writing to rows %d-%d (appending after existing data)', start_row, end_row)

    # Ensure sheet has enough rows (deleteDimension can shrink the grid)
    sheet_props = _get_sheet_props(sheets, spreadsheet_id, sheet_name)
    current_rows = sheet_props['gridProperties']['rowCount']
    if end_row > current_rows:
        rows_to_add = end_row - current_rows
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                'requests': [
                    {
                        'appendDimension': {
                            'sheetId': sheet_id,
                            'dimension': 'ROWS',
                            'length': rows_to_add,
                        }
                    }
                ]
            },
        ).execute()
        logger.info(
            'Expanded sheet by %d rows (was %d, now %d)',
            rows_to_add,
            current_rows,
            end_row,
        )

    write_data = []

    # Match info - handle contiguous columns (A-H for ORIGINAL, or A + I-O for modified)
    if preset.get('matchInfo'):
        match_info = preset['matchInfo']

        # Check if match info columns are contiguous (ORIGINAL preset: A-H)
        has_sexe = 'sexe' in match_info
        if match_info['time'] == 'B':
            # Contiguous A-based block (ORIGINAL / HOCKEY UND)
            row_values = []
            for m in match_data:
                row = [
                    m.get('date', ''),
                    m.get('time', ''),
                ]
                if has_sexe:
                    row.append(m.get('sexe', ''))
                row.extend([
                    m.get('country', ''),
                    m.get('league', ''),
                    m.get('teamA', ''),
                    m.get('rankA', ''),
                    m.get('teamB', ''),
                    m.get('rankB', ''),
                ])
                # Append ecart (rank difference) if the preset has an ecart column
                if 'ecart' in match_info:
                    rank_a = m.get('rankA', '')
                    rank_b = m.get('rankB', '')
                    try:
                        ecart = int(rank_a) - int(rank_b) if rank_a and rank_b else ''
                    except (ValueError, TypeError):
                        ecart = ''
                    row.append(ecart)
                row_values.append(row)

            col_from = match_info['date']
            col_to = match_info.get('ecart', match_info['rankB'])
            write_data.append(
                {
                    'start_col': col_from,
                    'end_col': col_to,
                    'start_row': start_row,
                    'values': row_values,
                }
            )
        else:
            # Modified preset - Date column (A) separate, then I-O
            date_values = [[m.get('date', '')] for m in match_data]
            date_col = match_info['date']
            write_data.append(
                {
                    'start_col': date_col,
                    'end_col': date_col,
                    'start_row': start_row,
                    'values': date_values,
                }
            )

            # Time through RankB columns (I-O) - contiguous block
            match_info_values = [
                [
                    m.get('time', ''),
                    m.get('country', ''),
                    m.get('league', ''),
                    m.get('teamA', ''),
                    m.get('rankA', ''),
                    m.get('teamB', ''),
                    m.get('rankB', ''),
                ]
                for m in match_data
            ]
            col_from = match_info['time']
            col_to = match_info['rankB']
            write_data.append(
                {
                    'start_col': col_from,
                    'end_col': col_to,
                    'start_row': start_row,
                    'values': match_info_values,
                }
            )

    # Raw score columns (HOCKEY RAW preset: 15 total-goal values per team)
    if preset.get('teamAScores'):
        score_count = preset['teamAScores']['count']
        team_a_score_values = [
            (m.get('teamAScores', []) + [''] * score_count)[:score_count]
            for m in match_data
        ]
        write_data.append(
            {
                'start_col': preset['teamAScores']['start'],
                'end_col': preset['teamAScores']['end'],
                'start_row': start_row,
                'values': team_a_score_values,
            }
        )

    if preset.get('teamBScores'):
        score_count = preset['teamBScores']['count']
        team_b_score_values = [
            (m.get('teamBScores', []) + [''] * score_count)[:score_count]
            for m in match_data
        ]
        write_data.append(
            {
                'start_col': preset['teamBScores']['start'],
                'end_col': preset['teamBScores']['end'],
                'start_row': start_row,
                'values': team_b_score_values,
            }
        )

    # Team A stats — aggregated counts (0 = no data available, keeps formulas working)
    if preset.get('teamA'):
        has_set2_a = 'set2' in preset['teamA']
        team_a_values = [
            [
                *(
                    [m.get('teamAStats', {}).get('count2', 0)]
                    if has_set2_a
                    else []
                ),
                m.get('teamAStats', {}).get('count3', 0),
                m.get('teamAStats', {}).get('count4', 0),
                m.get('teamAStats', {}).get('count5', 0),
            ]
            for m in match_data
        ]
        write_data.append(
            {
                'start_col': preset['teamA'].get('set2', preset['teamA']['set3']),
                'end_col': preset['teamA']['set5'],
                'start_row': start_row,
                'values': team_a_values,
            }
        )

    # Team B stats — aggregated counts (0 = no data available, keeps formulas working)
    if preset.get('teamB'):
        has_set2_b = 'set2' in preset['teamB']
        team_b_values = [
            [
                *(
                    [m.get('teamBStats', {}).get('count2', 0)]
                    if has_set2_b
                    else []
                ),
                m.get('teamBStats', {}).get('count3', 0),
                m.get('teamBStats', {}).get('count4', 0),
                m.get('teamBStats', {}).get('count5', 0),
            ]
            for m in match_data
        ]
        write_data.append(
            {
                'start_col': preset['teamB'].get('set2', preset['teamB']['set3']),
                'end_col': preset['teamB']['set5'],
                'start_row': start_row,
                'values': team_b_values,
            }
        )

    # H2H stats (skip when preset has no h2h, e.g. hockey)
    if preset.get('h2h'):
        h2h_values = [
            [
                m.get('h2hStats', {}).get('count3', 0),
                m.get('h2hStats', {}).get('count4', 0),
                m.get('h2hStats', {}).get('count5', 0),
            ]
            for m in match_data
        ]
        write_data.append(
            {
                'start_col': preset['h2h']['set3'],
                'end_col': preset['h2h']['set5'],
                'start_row': start_row,
                'values': h2h_values,
            }
        )

    # Batch write all values (won't touch other columns)
    _write_values(sheets, spreadsheet_id, sheet_id, write_data)

    logger.info('Successfully injected %d matches', len(match_data))
    logger.info('Columns updated:')
    if preset.get('matchInfo'):
        mi = preset['matchInfo']
        logger.info('  - Date: %s', mi['date'])
        last_col = mi.get('ecart', mi['rankB'])
        logger.info(
            '  - Match info: %s-%s (time, country, league, teams, ranks)',
            mi['time'],
            last_col,
        )
    if preset.get('teamAScores'):
        logger.info(
            '  - Team A raw scores: %s-%s (%d cols)',
            preset['teamAScores']['start'],
            preset['teamAScores']['end'],
            preset['teamAScores']['count'],
        )
    if preset.get('teamBScores'):
        logger.info(
            '  - Team B raw scores: %s-%s (%d cols)',
            preset['teamBScores']['start'],
            preset['teamBScores']['end'],
            preset['teamBScores']['count'],
        )
    if preset.get('teamA'):
        logger.info(
            '  - Team A stats: %s-%s',
            preset['teamA'].get('set2', preset['teamA']['set3']),
            preset['teamA']['set5'],
        )
    if preset.get('teamB'):
        logger.info(
            '  - Team B stats: %s-%s',
            preset['teamB'].get('set2', preset['teamB']['set3']),
            preset['teamB']['set5'],
        )
    if preset.get('h2h'):
        logger.info(
            '  - H2H stats: %s-%s',
            preset['h2h']['set3'],
            preset['h2h']['set5'],
        )


def inject_original_formulas() -> None:
    """Inject formulas for ORIGINAL preset computed columns.

    Must be called AFTER sorting so that row references in IF() formulas
    match the final row positions. Covers all data rows (2 through last).
    """
    preset_name = config.sheets.preset or 'ORIGINAL'
    if preset_name != 'ORIGINAL':
        return

    spreadsheet_id = config.google.spreadsheet_id
    if not spreadsheet_id:
        return

    sheets = get_google_sheets_client()
    preset = get_column_preset()
    sheet_name = config.sheets.tab_name or preset['sheetName']

    sheet_props = _get_sheet_props(sheets, spreadsheet_id, sheet_name)
    sheet_id = sheet_props['sheetId']

    last_row = find_next_empty_row(sheets, spreadsheet_id, sheet_id) - 1
    if last_row < 2:
        logger.info('No data rows found, skipping formula injection.')
        return

    logger.info('Injecting formulas for rows 2-%d in "%s"...', last_row, sheet_name)

    formula_data = _build_original_formulas(2, last_row)
    _write_values(sheets, spreadsheet_id, sheet_id, formula_data)

    logger.info(
        'Formulas injected: I, L, P-V, W, AA-AG, AI, AM-AS, AU-BA, BC-BF (rows 2-%d)',
        last_row,
    )
