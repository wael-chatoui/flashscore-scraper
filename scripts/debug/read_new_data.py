#!/usr/bin/env python3
"""Read columns A-H from the sheet to verify injected data"""

import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

creds = service_account.Credentials.from_service_account_file(
    os.environ.get('GOOGLE_CREDENTIALS_PATH', '/app/credentials.json'),
    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'],
)
sheets = build('sheets', 'v4', credentials=creds)
sid = os.environ['SPREADSHEET_ID']

# Read columns A through H, first 80 rows
result = (
    sheets.spreadsheets()
    .values()
    .get(spreadsheetId=sid, range="'SCRAPING OU4'!A1:H80", majorDimension='ROWS')
    .execute()
)

rows = result.get('values', [])
for i, row in enumerate(rows):
    row += [''] * (8 - len(row))
    # Format nicely
    print(
        f'Row {i + 1:3d}: A={row[0]:12s} B={row[1]:8s} C={row[2]:15s} D={row[3]:25s} E={row[4]:25s} F={row[5]:5s} G={row[6]:25s} H={row[7]:5s}'
    )
