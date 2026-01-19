"""
Google Sheets Integration

Injects scraped volleyball match data into Google Sheets
"""

import os
import json
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import config

# Column mapping - configurable based on actual sheet structure
#
# Actual sheet layout for "TRI BASE O/U 4":
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
    # Corrected mapping based on actual sheet structure
    # Sheet columns: A=DATE, I=Status, J=PAYS, K=LEAGUE, L=EQUIPE A, M=Rank A, N=EQUIPE B, O=Rank B
    # Stats: T-V=Team A (3,4,5 sets), AE-AG=Team B (3,4,5 sets), AJ-AL=H2H (3,4,5 sets)
    'TRI BASE OU 4': {
        'sheetName': 'TRI BASE O/U 4',
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


def get_column_preset() -> dict:
    """Get active preset from config or default"""
    preset_name = config.sheets.preset or 'TRI BASE OU 4'
    return COLUMN_PRESETS.get(preset_name, COLUMN_PRESETS['TRI BASE OU 4'])


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


def inject_to_google_sheets(match_data: list[dict[str, Any]], start_row: int = 2) -> None:
    """
    Inject scraped data into Google Sheets (only GREEN columns)

    Args:
        match_data: Array of match objects from scraper
        start_row: Starting row (default: 2, assuming row 1 has headers)
    """
    if not config.google.spreadsheet_id:
        raise ValueError('SPREADSHEET_ID not configured. Set it in .env or environment variable.')

    sheets = get_google_sheets_client()
    spreadsheet_id = config.google.spreadsheet_id
    preset = get_column_preset()
    sheet_name = config.sheets.tab_name or preset['sheetName']

    print(f'Injecting {len(match_data)} matches into "{sheet_name}"...')
    print(f"Using column preset: {config.sheets.preset or 'TRI BASE OU 4'}")

    value_ranges = []
    end_row = start_row + len(match_data) - 1

    # Match info - handle both contiguous and non-contiguous columns
    if preset.get('matchInfo'):
        match_info = preset['matchInfo']

        # Date column (A) - separate because B-H have formulas
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
