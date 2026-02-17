"""
Google Sheets Integration

Injects scraped volleyball match data into Google Sheets
"""

import os
import json
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import config

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
            'date': 'A', 'time': 'B', 'country': 'C', 'league': 'D',
            'teamA': 'E', 'rankA': 'F', 'teamB': 'G', 'rankB': 'H'
        },
        'teamA': {'set3': 'M', 'set4': 'N', 'set5': 'O'},
        'teamB': {'set3': 'X', 'set4': 'Y', 'set5': 'Z'},
        'h2h': {'set3': 'AJ', 'set4': 'AK', 'set5': 'AL'}
    },
    # Modified spreadsheet structure (Spreadsheet 1 - test/modified version)
    # Sheet columns: A=DATE, I=Status, J=PAYS, K=LEAGUE, L=EQUIPE A, M=Rank A, N=EQUIPE B, O=Rank B
    # Stats: T-V=Team A (3,4,5 sets), AE-AG=Team B (3,4,5 sets), AJ-AL=H2H (3,4,5 sets)
    'SCRAPING OU4': {
        'sheetName': 'SCRAPING OU4',
        'matchInfo': {
            'date': 'A', 'time': 'I', 'country': 'J', 'league': 'K',
            'teamA': 'L', 'rankA': 'M', 'teamB': 'N', 'rankB': 'O'
        },
        'teamA': {'set3': 'T', 'set4': 'U', 'set5': 'V'},
        'teamB': {'set3': 'AE', 'set4': 'AF', 'set5': 'AG'},
        'h2h': {'set3': 'AJ', 'set4': 'AK', 'set5': 'AL'}
    },
    # Alternative mapping based on CSV structure
    'CALCUL SET': {
        'sheetName': 'CALCUL SET',
        'matchInfo': None,  # Visual layout - match info not in simple columns
        'teamA': {'set3': 'C', 'set4': 'D', 'set5': 'E'},
        'teamB': {'set3': 'I', 'set4': 'J', 'set5': 'K'},
        'h2h': {'set3': 'O', 'set4': 'P', 'set5': 'Q'}
    }
}


def _build_original_formulas(sheet_name: str, start_row: int, end_row: int) -> list[dict]:
    """Build formula value_ranges for ORIGINAL preset computed columns.

    Covers columns I, L, P-V (Team A), W, AA-AG (Team B), AI, AM-AS (H2H).
    """
    rows = range(start_row, end_row + 1)
    formula_ranges = []

    # Column I: ECART (rank difference)
    formula_ranges.append({
        'range': f"'{sheet_name}'!I{start_row}:I{end_row}",
        'values': [[f'=F{r}-H{r}'] for r in rows]
    })

    # Column L: N;TOTAL SET A
    formula_ranges.append({
        'range': f"'{sheet_name}'!L{start_row}:L{end_row}",
        'values': [[f'=M{r}*3+N{r}*4+O{r}*5'] for r in rows]
    })

    # Columns P-V: Team A derived stats
    formula_ranges.append({
        'range': f"'{sheet_name}'!P{start_row}:V{end_row}",
        'values': [
            [
                f'=N{r}+O{r}',                    # P: 4+
                f'=M{r}+N{r}+O{r}',               # Q: TOTAL MATCH
                f'=IF(Q{r}=0;"";L{r}/Q{r})',       # R: MOY SET MATCH A
                f'=IF(Q{r}=0;"";M{r}/Q{r})',       # S: MOY 3 SET A
                f'=IF(Q{r}=0;"";N{r}/Q{r})',       # T: MOY 4 SET A
                f'=IF(Q{r}=0;"";O{r}/Q{r})',       # U: MOY 5 SET A
                f'=IF(Q{r}=0;"";P{r}/Q{r})',       # V: MOY 4+
            ]
            for r in rows
        ]
    })

    # Column W: N;TOTAL SET B
    formula_ranges.append({
        'range': f"'{sheet_name}'!W{start_row}:W{end_row}",
        'values': [[f'=X{r}*3+Y{r}*4+Z{r}*5'] for r in rows]
    })

    # Columns AA-AG: Team B derived stats
    formula_ranges.append({
        'range': f"'{sheet_name}'!AA{start_row}:AG{end_row}",
        'values': [
            [
                f'=Y{r}+Z{r}',                      # AA: 4+
                f'=X{r}+Y{r}+Z{r}',                 # AB: TOTAL MATCH B
                f'=IF(AB{r}=0;"";W{r}/AB{r})',       # AC: MOY SET MATCH B
                f'=IF(AB{r}=0;"";X{r}/AB{r})',       # AD: MOY 3 B
                f'=IF(AB{r}=0;"";Y{r}/AB{r})',       # AE: MOY 4 B
                f'=IF(AB{r}=0;"";Z{r}/AB{r})',       # AF: MOY 5 B
                f'=IF(AB{r}=0;"";AA{r}/AB{r})',      # AG: MOY 4+ B
            ]
            for r in rows
        ]
    })

    # Column AI: H2H N.TOTAL SET
    formula_ranges.append({
        'range': f"'{sheet_name}'!AI{start_row}:AI{end_row}",
        'values': [[f'=AJ{r}*3+AK{r}*4+AL{r}*5'] for r in rows]
    })

    # Columns AM-AS: H2H derived stats
    formula_ranges.append({
        'range': f"'{sheet_name}'!AM{start_row}:AS{end_row}",
        'values': [
            [
                f'=AK{r}+AL{r}',                      # AM: 4+
                f'=AJ{r}+AK{r}+AL{r}',                # AN: TOTAL H2H
                f'=IF(AN{r}=0;"";AI{r}/AN{r})',        # AO: MOY H2H SET
                f'=IF(AN{r}=0;"";AJ{r}/AN{r})',        # AP: MOY H2H 3 SET
                f'=IF(AN{r}=0;"";AK{r}/AN{r})',        # AQ: MOY H2H 4 SET
                f'=IF(AN{r}=0;"";AL{r}/AN{r})',        # AR: MOY H2H 5 SET
                f'=IF(AN{r}=0;"";AM{r}/AN{r})',        # AS: MOY H2H 4+ SET
            ]
            for r in rows
        ]
    })

    # Columns AU-BA: MG (Moyenne Générale) — combined averages
    formula_ranges.append({
        'range': f"'{sheet_name}'!AU{start_row}:BA{end_row}",
        'values': [
            [
                f'=AVERAGE(L{r};W{r};AI{r})',              # AU: MG BUT (avg total sets)
                f'=AVERAGE(R{r};AC{r};AO{r})',             # AV: MG SET (avg MOY SET)
                f'=AVERAGE(S{r};AD{r};AP{r})',             # AW: MG 3 (avg 3-set %)
                f'=AVERAGE(T{r};AE{r};AQ{r})',             # AX: MG 4 (avg 4-set %)
                f'=AVERAGE(U{r};AF{r};AR{r})',             # AY: MG 5 (avg 5-set %)
                f'=AVERAGE(V{r};AG{r};AS{r})',             # AZ: MG 4+ (avg 4+ %)
                f'=AW{r}+AX{r}',                           # BA: MG 4- (3-set + 4-set %)
            ]
            for r in rows
        ]
    })

    # Columns BC-BF: Ratios and Filters
    formula_ranges.append({
        'range': f"'{sheet_name}'!BC{start_row}:BF{end_row}",
        'values': [
            [
                f'=IF(AY{r}=0;"";AW{r}/AY{r})',            # BC: RATIO U (3-set/5-set)
                f'=IF(AW{r}=0;"";AY{r}/AW{r})',            # BD: RATIO O (5-set/3-set)
                f'=IF(AY{r}=0;"";AX{r}/AY{r})',            # BE: Filtre U (4-set/5-set)
                f'=IF(AW{r}=0;"";AX{r}/AW{r})',            # BF: Filtre 0+ (4-set/3-set)
            ]
            for r in rows
        ]
    })

    return formula_ranges


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
            cred_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
    elif os.getenv('GOOGLE_CREDENTIALS_JSON'):
        # Support inline JSON credentials (useful for Docker/cloud)
        cred_info = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
        credentials = service_account.Credentials.from_service_account_info(
            cred_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
    else:
        # Fall back to application default credentials
        from google.auth import default
        credentials, _ = default(scopes=['https://www.googleapis.com/auth/spreadsheets'])

    return build('sheets', 'v4', credentials=credentials)


def find_next_empty_row(sheets, spreadsheet_id: str, sheet_name: str, col: str = 'A') -> int:
    """Find the first empty row in the given column (1-indexed)."""
    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!{col}:{col}",
        majorDimension='COLUMNS'
    ).execute()
    values = result.get('values', [[]])
    # Length of the column data = last row with content
    return len(values[0]) + 1 if values and values[0] else 2


def _delete_rows_by_date(sheets, spreadsheet_id: str, sheet_name: str, target_date: str) -> int:
    """Delete all rows where column A matches target_date.

    Works bottom-up so that row indices stay valid during deletion.
    Returns the number of deleted rows.
    """
    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:A",
        majorDimension='COLUMNS'
    ).execute()
    values = result.get('values', [[]])
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

    # Get numeric sheet ID
    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_id = None
    for sheet in meta.get('sheets', []):
        if sheet['properties']['title'] == sheet_name:
            sheet_id = sheet['properties']['sheetId']
            break
    if sheet_id is None:
        raise ValueError(f"Sheet '{sheet_name}' not found")

    # Build delete requests bottom-up (so indices stay valid)
    requests = []
    for row in sorted(matching_rows, reverse=True):
        requests.append({
            'deleteDimension': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'ROWS',
                    'startIndex': row - 1,  # 0-indexed
                    'endIndex': row          # exclusive
                }
            }
        })

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={'requests': requests}
    ).execute()

    return len(matching_rows)


def inject_to_google_sheets(match_data: list[dict[str, Any]], start_row: int = 2) -> None:
    """
    Inject scraped data into Google Sheets (only GREEN columns).
    Deduplicates by date: if rows for the same date already exist, they are
    deleted first so re-running replaces rather than duplicates.

    Args:
        match_data: Array of match objects from scraper
        start_row: Minimum starting row (default: 2, assuming row 1 has headers)
    """
    if not config.google.spreadsheet_id:
        raise ValueError('SPREADSHEET_ID not configured. Set it in .env or environment variable.')

    sheets = get_google_sheets_client()
    spreadsheet_id = config.google.spreadsheet_id
    preset = get_column_preset()
    sheet_name = config.sheets.tab_name or preset['sheetName']

    print(f'Injecting {len(match_data)} matches into "{sheet_name}"...')
    print(f"Using column preset: {config.sheets.preset or 'ORIGINAL'}")

    # Deduplicate: delete existing rows for the same date(s)
    dates_in_batch = {m.get('date', '') for m in match_data if m.get('date')}
    total_deleted = 0
    for date_str in dates_in_batch:
        deleted = _delete_rows_by_date(sheets, spreadsheet_id, sheet_name, date_str)
        total_deleted += deleted
    if total_deleted:
        print(f'Dedup: removed {total_deleted} existing rows for date(s) {", ".join(sorted(dates_in_batch))}')

    # Find the next empty row to append after existing data
    next_empty = find_next_empty_row(sheets, spreadsheet_id, sheet_name)
    start_row = max(start_row, next_empty)
    end_row = start_row + len(match_data) - 1
    print(f'Writing to rows {start_row}-{end_row} (appending after existing data)')

    # Ensure sheet has enough rows (deleteDimension can shrink the grid)
    meta = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=[f"'{sheet_name}'"],
        includeGridData=False
    ).execute()
    sheet_props = meta['sheets'][0]['properties']
    sheet_id = sheet_props['sheetId']
    current_rows = sheet_props['gridProperties']['rowCount']
    if end_row > current_rows:
        rows_to_add = end_row - current_rows
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [{
                'appendDimension': {
                    'sheetId': sheet_id,
                    'dimension': 'ROWS',
                    'length': rows_to_add
                }
            }]}
        ).execute()
        print(f'Expanded sheet by {rows_to_add} rows (was {current_rows}, now {end_row})')

    value_ranges = []

    # Match info - handle contiguous columns (A-H for ORIGINAL, or A + I-O for modified)
    if preset.get('matchInfo'):
        match_info = preset['matchInfo']

        # Check if match info columns are contiguous (ORIGINAL preset: A-H)
        # For ORIGINAL: date=A, time=B, country=C, league=D, teamA=E, rankA=F, teamB=G, rankB=H
        if match_info['time'] == 'B':
            # ORIGINAL preset - all match info is contiguous A-H
            match_info_values = [
                [
                    m.get('date', ''),
                    m.get('time', ''),
                    m.get('country', ''),
                    m.get('league', ''),
                    m.get('teamA', ''),
                    m.get('rankA', ''),
                    m.get('teamB', ''),
                    m.get('rankB', '')
                ]
                for m in match_data
            ]
            value_ranges.append({
                'range': f"'{sheet_name}'!{match_info['date']}{start_row}:{match_info['rankB']}{end_row}",
                'values': match_info_values
            })
        else:
            # Modified preset - Date column (A) separate, then I-O
            date_values = [[m.get('date', '')] for m in match_data]
            value_ranges.append({
                'range': f"'{sheet_name}'!{match_info['date']}{start_row}:{match_info['date']}{end_row}",
                'values': date_values
            })

            # Time through RankB columns (I-O) - contiguous block
            match_info_values = [
                [
                    m.get('time', ''),
                    m.get('country', ''),
                    m.get('league', ''),
                    m.get('teamA', ''),
                    m.get('rankA', ''),
                    m.get('teamB', ''),
                    m.get('rankB', '')
                ]
                for m in match_data
            ]
            value_ranges.append({
                'range': f"'{sheet_name}'!{match_info['time']}{start_row}:{match_info['rankB']}{end_row}",
                'values': match_info_values
            })

    # Team A stats (0 = no data available, keeps formulas working)
    team_a_values = [
        [
            m.get('teamAStats', {}).get('count3', 0),
            m.get('teamAStats', {}).get('count4', 0),
            m.get('teamAStats', {}).get('count5', 0)
        ]
        for m in match_data
    ]
    value_ranges.append({
        'range': f"'{sheet_name}'!{preset['teamA']['set3']}{start_row}:{preset['teamA']['set5']}{end_row}",
        'values': team_a_values
    })

    # Team B stats (0 = no data available, keeps formulas working)
    team_b_values = [
        [
            m.get('teamBStats', {}).get('count3', 0),
            m.get('teamBStats', {}).get('count4', 0),
            m.get('teamBStats', {}).get('count5', 0)
        ]
        for m in match_data
    ]
    value_ranges.append({
        'range': f"'{sheet_name}'!{preset['teamB']['set3']}{start_row}:{preset['teamB']['set5']}{end_row}",
        'values': team_b_values
    })

    # H2H stats (0 = no H2H history between teams, keeps formulas working)
    h2h_values = [
        [
            m.get('h2hStats', {}).get('count3', 0),
            m.get('h2hStats', {}).get('count4', 0),
            m.get('h2hStats', {}).get('count5', 0)
        ]
        for m in match_data
    ]
    value_ranges.append({
        'range': f"'{sheet_name}'!{preset['h2h']['set3']}{start_row}:{preset['h2h']['set5']}{end_row}",
        'values': h2h_values
    })

    # Batch update all values (won't touch other columns)
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            'valueInputOption': 'USER_ENTERED',
            'data': value_ranges
        }
    ).execute()

    print(f'Successfully injected {len(match_data)} matches')
    print('Columns updated:')
    if preset.get('matchInfo'):
        mi = preset['matchInfo']
        print(f"  - Date: {mi['date']}")
        print(f"  - Match info: {mi['time']}-{mi['rankB']} (time, country, league, teams, ranks)")
    print(f"  - Team A stats: {preset['teamA']['set3']}-{preset['teamA']['set5']}")
    print(f"  - Team B stats: {preset['teamB']['set3']}-{preset['teamB']['set5']}")
    print(f"  - H2H stats: {preset['h2h']['set3']}-{preset['h2h']['set5']}")


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

    last_row = find_next_empty_row(sheets, spreadsheet_id, sheet_name) - 1
    if last_row < 2:
        print('No data rows found, skipping formula injection.')
        return

    print(f'Injecting formulas for rows 2-{last_row} in "{sheet_name}"...')

    formula_ranges = _build_original_formulas(sheet_name, 2, last_row)

    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            'valueInputOption': 'USER_ENTERED',
            'data': formula_ranges
        }
    ).execute()

    print(f'Formulas injected: I, L, P-V, W, AA-AG, AI, AM-AS, AU-BA, BC-BF (rows 2-{last_row})')
