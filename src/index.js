import { scrapeFlashScore } from './scraper.js';
import { injectToGoogleSheets } from './sheets.js';
import config from './config.js';

async function main() {
  const args = process.argv.slice(2);
  const scrapeOnly = args.includes('--scrape-only');
  const sheetsOnly = args.includes('--sheets-only');
  const jsonFile = args.find(a => a.startsWith('--json='))?.split('=')[1];

  console.log('='.repeat(50));
  console.log('FlashScore Volleyball Scraper');
  console.log('='.repeat(50));
  console.log(`Date: ${new Date().toLocaleString('fr-FR')}`);
  console.log(`Mode: ${scrapeOnly ? 'Scrape only' : sheetsOnly ? 'Sheets only' : 'Full (scrape + sheets)'}`);
  console.log('='.repeat(50));

  let matchData;

  // Step 1: Scrape data (unless sheets-only mode)
  if (!sheetsOnly) {
    console.log('\n[1/2] Scraping FlashScore volleyball matches...\n');

    matchData = await scrapeFlashScore(config.scraper.headless);

    console.log(`\nScraped ${matchData.length} matches`);

    // Save to JSON file (in output dir if exists, otherwise current dir)
    const fs = await import('fs');
    const path = await import('path');
    const outputDir = fs.existsSync('./output') ? './output' : '.';
    const outputFile = path.join(outputDir, `matches_${new Date().toISOString().split('T')[0]}.json`);
    fs.writeFileSync(outputFile, JSON.stringify(matchData, null, 2));
    console.log(`Data saved to ${outputFile}`);

    if (scrapeOnly) {
      console.log('\n--scrape-only flag set. Skipping Google Sheets injection.');
      printSummary(matchData);
      return;
    }
  }

  // Step 2: Inject to Google Sheets (unless scrape-only mode)
  if (!scrapeOnly) {
    console.log('\n[2/2] Injecting data into Google Sheets...\n');

    // Load from JSON if sheets-only mode
    if (sheetsOnly && jsonFile) {
      const fs = await import('fs');
      matchData = JSON.parse(fs.readFileSync(jsonFile, 'utf8'));
      console.log(`Loaded ${matchData.length} matches from ${jsonFile}`);
    }

    if (!matchData || matchData.length === 0) {
      console.log('No match data to inject. Run with scrape first or provide --json=file.json');
      return;
    }

    if (!config.google.spreadsheetId) {
      console.error('ERROR: SPREADSHEET_ID not configured!');
      console.error('Please set SPREADSHEET_ID in .env file or environment variable');
      console.error('\nYour scraped data has been saved to JSON file.');
      return;
    }

    await injectToGoogleSheets(matchData, config.sheets.startRow);
  }

  printSummary(matchData);
  console.log('\nDone!');
}

function printSummary(matchData) {
  console.log('\n' + '='.repeat(50));
  console.log('SUMMARY');
  console.log('='.repeat(50));
  console.log(`Total matches: ${matchData.length}`);

  // Group by country/league
  const byLeague = {};
  for (const m of matchData) {
    const key = `${m.country} - ${m.league}`;
    byLeague[key] = (byLeague[key] || 0) + 1;
  }

  console.log('\nMatches by league:');
  for (const [league, count] of Object.entries(byLeague)) {
    console.log(`  ${league}: ${count}`);
  }

  // Sample match
  if (matchData.length > 0) {
    const sample = matchData[0];
    console.log('\nSample match:');
    console.log(`  ${sample.teamA} vs ${sample.teamB}`);
    console.log(`  Date: ${sample.date} ${sample.time}`);
    console.log(`  Team A sets: 3=${sample.teamAStats?.count3}, 4=${sample.teamAStats?.count4}, 5=${sample.teamAStats?.count5}`);
    console.log(`  Team B sets: 3=${sample.teamBStats?.count3}, 4=${sample.teamBStats?.count4}, 5=${sample.teamBStats?.count5}`);
    console.log(`  H2H sets: 3=${sample.h2hStats?.count3}, 4=${sample.h2hStats?.count4}, 5=${sample.h2hStats?.count5}`);
  }
}

// Run
main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
