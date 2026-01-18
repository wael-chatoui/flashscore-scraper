/**
 * Configuration for FlashScore Volleyball Scraper
 *
 * Set these values via environment variables or modify directly
 */

const config = {
  // Google Sheets configuration
  google: {
    // Your Google Sheet ID (from the URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)
    spreadsheetId: process.env.SPREADSHEET_ID || '',

    // Path to Google service account credentials JSON file
    // Download from Google Cloud Console > APIs & Services > Credentials
    credentialsPath: process.env.GOOGLE_CREDENTIALS_PATH || './credentials.json'
  },

  // Scraper configuration
  scraper: {
    // Run browser in headless mode (set to false for debugging)
    headless: process.env.HEADLESS !== 'false',

    // Delay between match requests (ms)
    requestDelay: parseInt(process.env.REQUEST_DELAY, 10) || 1000,

    // Maximum matches to process (0 = unlimited)
    maxMatches: parseInt(process.env.MAX_MATCHES, 10) || 0
  },

  // Google Sheets tab and row configuration
  sheets: {
    // Column preset: 'TRI BASE OU 4' (from brief) or 'CALCUL SET' (from CSV)
    preset: process.env.SHEET_PRESET || 'TRI BASE OU 4',

    // Sheet tab name (overrides preset default)
    tabName: process.env.SHEET_TAB_NAME || '',

    // Starting row for data injection (1-indexed, 2 = after header row)
    startRow: parseInt(process.env.START_ROW, 10) || 2
  }
};

export default config;
