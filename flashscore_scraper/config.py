"""
Configuration for FlashScore Volleyball Scraper

Set these values via environment variables or modify directly
"""

import logging
import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env file from parent directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))


@dataclass
class GoogleConfig:
    """Google Sheets configuration"""

    # Your Google Sheet ID (from the URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)
    spreadsheet_id: str = field(default_factory=lambda: os.getenv('SPREADSHEET_ID', ''))

    # Separate spreadsheet for hockey (optional — falls back to SPREADSHEET_ID)
    hockey_spreadsheet_id: str = field(
        default_factory=lambda: os.getenv('HOCKEY_SPREADSHEET_ID', '')
    )

    # Separate spreadsheet for football (optional — falls back to SPREADSHEET_ID)
    football_spreadsheet_id: str = field(
        default_factory=lambda: os.getenv('FOOTBALL_SPREADSHEET_ID', '')
    )

    # Unified all-sports log spreadsheet (optional)
    all_sports_log_spreadsheet_id: str = field(
        default_factory=lambda: os.getenv('ALL_SPORTS_LOG_SPREADSHEET_ID', '')
    )

    # Tab name for the all-sports log (default: Sheet1)
    all_sports_log_tab_name: str = field(
        default_factory=lambda: os.getenv('ALL_SPORTS_LOG_SHEET_TAB', 'Sheet1')
    )

    # Path to Google service account credentials JSON file
    # Download from Google Cloud Console > APIs & Services > Credentials
    credentials_path: str = field(
        default_factory=lambda: os.getenv(
            'GOOGLE_CREDENTIALS_PATH',
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'credentials.json'
            ),
        )
    )


@dataclass
class ScraperConfig:
    """Scraper configuration"""

    # Sport to scrape: 'volleyball' or 'hockey'
    sport: str = field(default_factory=lambda: os.getenv('SPORT', 'volleyball'))

    # Run browser in headless mode (no visible window)
    headless: bool = field(
        default_factory=lambda: os.getenv('HEADLESS', 'true').lower() in ('true', '1', 'yes')
    )

    # Delay between match requests (ms)
    request_delay: int = field(default_factory=lambda: int(os.getenv('REQUEST_DELAY', '1000')))

    # Maximum matches to process (0 = unlimited)
    max_matches: int = field(default_factory=lambda: int(os.getenv('MAX_MATCHES', '0')))


@dataclass
class SheetsConfig:
    """Google Sheets tab and row configuration"""

    # Column preset: 'ORIGINAL', 'SCRAPING OU4', or 'CALCUL SET'
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


class _LogFormatter(logging.Formatter):
    """Custom formatter: show level prefix for WARNING+, plain message for INFO/DEBUG."""

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno >= logging.WARNING:
            self._style._fmt = '%(levelname)s: %(message)s'
        else:
            self._style._fmt = '%(message)s'
        return super().format(record)


def setup_logging() -> None:
    """Configure the ``flashscore_scraper`` logger hierarchy.

    Call once from each entry point (cli, batch main, etc.).
    """
    root_logger = logging.getLogger('flashscore_scraper')
    if root_logger.handlers:
        return  # already configured

    root_logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_LogFormatter())

    root_logger.addHandler(handler)


# Global config instance
config = Config()
