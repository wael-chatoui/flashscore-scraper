"""
Configuration for FlashScore Volleyball Scraper

Set these values via environment variables or modify directly
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env file from parent directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))


@dataclass
class GoogleConfig:
    """Google Sheets configuration"""
    # Your Google Sheet ID (from the URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)
    spreadsheet_id: str = field(default_factory=lambda: os.getenv('SPREADSHEET_ID', ''))

    # Path to Google service account credentials JSON file
    # Download from Google Cloud Console > APIs & Services > Credentials
    credentials_path: str = field(default_factory=lambda: os.getenv(
        'GOOGLE_CREDENTIALS_PATH',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'credentials.json')
    ))


@dataclass
class ScraperConfig:
    """Scraper configuration"""
    # Delay between match requests (ms)
    request_delay: int = field(default_factory=lambda: int(os.getenv('REQUEST_DELAY', '1000')))

    # Maximum matches to process (0 = unlimited)
    max_matches: int = field(default_factory=lambda: int(os.getenv('MAX_MATCHES', '0')))


@dataclass
class SheetsConfig:
    """Google Sheets tab and row configuration"""
    # Column preset: 'ORIGINAL' (client's original), 'TRI BASE OU 4' (test), or 'CALCUL SET' (from CSV)
    preset: str = field(default_factory=lambda: os.getenv('SHEET_PRESET', 'ORIGINAL'))

    # Sheet tab name (overrides preset default)
    tab_name: str = field(default_factory=lambda: os.getenv('SHEET_TAB_NAME', ''))

    # Starting row for data injection (1-indexed, 2 = after header row)
    start_row: int = field(default_factory=lambda: int(os.getenv('START_ROW', '2')))


@dataclass
class Config:
    """Main configuration"""
    google: GoogleConfig = field(default_factory=GoogleConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    sheets: SheetsConfig = field(default_factory=SheetsConfig)


# Global config instance
config = Config()
