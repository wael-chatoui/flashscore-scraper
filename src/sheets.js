import { google } from 'googleapis';
import { readFileSync, existsSync } from 'fs';
import config from './config.js';

/**
 * Column mapping - configurable based on actual sheet structure
 *
 * From the PDF brief (tab "TRI BASE OU 4"):
 * - Match info: A-H (Date, Time, Country, League, Team A, Rank A, Team B, Rank B)
 * - Team A stats: M, N, O (3, 4, 5 sets)
 * - Team B stats: X, Y, Z (3, 4, 5 sets)
 * - H2H stats: AJ, AK, AL (3, 4, 5 sets)
 *
 * From the CSV analysis (tab "CALCUL SET"):
 * - Team A stats: C, D, E
 * - Team B stats: I, J, K
 * - H2H stats: O, P, Q
 */
const COLUMN_PRESETS = {
  // Original mapping from PDF brief
  'TRI BASE OU 4': {
    sheetName: 'TRI BASE O/U 4',
    matchInfo: { date: 'A', time: 'B', country: 'C', league: 'D', teamA: 'E', rankA: 'F', teamB: 'G', rankB: 'H' },
    teamA: { set3: 'M', set4: 'N', set5: 'O' },
    teamB: { set3: 'X', set4: 'Y', set5: 'Z' },
    h2h: { set3: 'AJ', set4: 'AK', set5: 'AL' }
  },
  // Alternative mapping based on CSV structure
  'CALCUL SET': {
    sheetName: 'CALCUL SET',
    matchInfo: null, // Visual layout - match info not in simple columns
    teamA: { set3: 'C', set4: 'D', set5: 'E' },
    teamB: { set3: 'I', set4: 'J', set5: 'K' },
    h2h: { set3: 'O', set4: 'P', set5: 'Q' }
  }
};

// Get active preset from config or default
function getColumnPreset() {
  const presetName = config.sheets?.preset || 'TRI BASE OU 4';
  return COLUMN_PRESETS[presetName] || COLUMN_PRESETS['TRI BASE OU 4'];
}

/**
 * Authenticate with Google Sheets API
 */
async function getGoogleSheetsClient() {
  let auth;
  const credPath = config.google.credentialsPath;

  if (credPath && existsSync(credPath)) {
    const credentials = JSON.parse(readFileSync(credPath, 'utf8'));
    auth = new google.auth.GoogleAuth({
      credentials,
      scopes: ['https://www.googleapis.com/auth/spreadsheets']
    });
  } else if (process.env.GOOGLE_CREDENTIALS_JSON) {
    // Support inline JSON credentials (useful for Docker/cloud)
    const credentials = JSON.parse(process.env.GOOGLE_CREDENTIALS_JSON);
    auth = new google.auth.GoogleAuth({
      credentials,
      scopes: ['https://www.googleapis.com/auth/spreadsheets']
    });
  } else {
    auth = new google.auth.GoogleAuth({
      scopes: ['https://www.googleapis.com/auth/spreadsheets']
    });
  }

  return google.sheets({ version: 'v4', auth });
}

/**
 * Inject scraped data into Google Sheets (only GREEN columns)
 * @param {Array} matchData - Array of match objects from scraper
 * @param {number} startRow - Starting row (default: 2, assuming row 1 has headers)
 */
export async function injectToGoogleSheets(matchData, startRow = 2) {
  if (!config.google.spreadsheetId) {
    throw new Error('SPREADSHEET_ID not configured. Set it in .env or environment variable.');
  }

  const sheets = await getGoogleSheetsClient();
  const spreadsheetId = config.google.spreadsheetId;
  const preset = getColumnPreset();
  const sheetName = config.sheets?.tabName || preset.sheetName;

  console.log(`Injecting ${matchData.length} matches into "${sheetName}"...`);
  console.log(`Using column preset: ${config.sheets?.preset || 'TRI BASE OU 4'}`);

  const valueRanges = [];

  // Match info (A-H) - only if preset supports it
  if (preset.matchInfo) {
    const { date, time, country, league, teamA, rankA, teamB, rankB } = preset.matchInfo;
    const matchInfoValues = matchData.map(m => [
      m.date || '',
      m.time || '',
      m.country || '',
      m.league || '',
      m.teamA || '',
      m.rankA || '',
      m.teamB || '',
      m.rankB || ''
    ]);
    valueRanges.push({
      range: `'${sheetName}'!${date}${startRow}:${rankB}${startRow + matchData.length - 1}`,
      values: matchInfoValues
    });
  }

  // Team A stats
  const teamAValues = matchData.map(m => [
    m.teamAStats?.count3 ?? 0,
    m.teamAStats?.count4 ?? 0,
    m.teamAStats?.count5 ?? 0
  ]);
  valueRanges.push({
    range: `'${sheetName}'!${preset.teamA.set3}${startRow}:${preset.teamA.set5}${startRow + matchData.length - 1}`,
    values: teamAValues
  });

  // Team B stats
  const teamBValues = matchData.map(m => [
    m.teamBStats?.count3 ?? 0,
    m.teamBStats?.count4 ?? 0,
    m.teamBStats?.count5 ?? 0
  ]);
  valueRanges.push({
    range: `'${sheetName}'!${preset.teamB.set3}${startRow}:${preset.teamB.set5}${startRow + matchData.length - 1}`,
    values: teamBValues
  });

  // H2H stats
  const h2hValues = matchData.map(m => [
    m.h2hStats?.count3 ?? 0,
    m.h2hStats?.count4 ?? 0,
    m.h2hStats?.count5 ?? 0
  ]);
  valueRanges.push({
    range: `'${sheetName}'!${preset.h2h.set3}${startRow}:${preset.h2h.set5}${startRow + matchData.length - 1}`,
    values: h2hValues
  });

  // Batch update all values (won't touch other columns)
  await sheets.spreadsheets.values.batchUpdate({
    spreadsheetId,
    requestBody: {
      valueInputOption: 'USER_ENTERED',
      data: valueRanges
    }
  });

  console.log(`Successfully injected ${matchData.length} matches`);
  console.log('Columns updated:');
  if (preset.matchInfo) console.log(`  - Match info: ${preset.matchInfo.date}-${preset.matchInfo.rankB}`);
  console.log(`  - Team A stats: ${preset.teamA.set3}-${preset.teamA.set5}`);
  console.log(`  - Team B stats: ${preset.teamB.set3}-${preset.teamB.set5}`);
  console.log(`  - H2H stats: ${preset.h2h.set3}-${preset.h2h.set5}`);
}

export default { injectToGoogleSheets };
