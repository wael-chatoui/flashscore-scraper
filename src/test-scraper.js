/**
 * Test script to verify scraper works without Google Sheets
 */
import { scrapeFlashScore } from './scraper.js';

async function test() {
  console.log('Testing FlashScore scraper (headless=false for debugging)...\n');

  try {
    // Run with visible browser for testing
    const matches = await scrapeFlashScore(false);

    console.log('\n' + '='.repeat(60));
    console.log(`Found ${matches.length} matches`);
    console.log('='.repeat(60));

    // Print first 5 matches
    for (let i = 0; i < Math.min(5, matches.length); i++) {
      const m = matches[i];
      console.log(`\nMatch ${i + 1}:`);
      console.log(`  ${m.teamA} vs ${m.teamB}`);
      console.log(`  ${m.country} - ${m.league}`);
      console.log(`  ${m.date} ${m.time}`);
      console.log(`  Team A stats: 3sets=${m.teamAStats.count3}, 4sets=${m.teamAStats.count4}, 5sets=${m.teamAStats.count5}`);
      console.log(`  Team B stats: 3sets=${m.teamBStats.count3}, 4sets=${m.teamBStats.count4}, 5sets=${m.teamBStats.count5}`);
      console.log(`  H2H stats: 3sets=${m.h2hStats.count3}, 4sets=${m.h2hStats.count4}, 5sets=${m.h2hStats.count5}`);
    }

    // Save full results
    const fs = await import('fs');
    fs.writeFileSync('test-results.json', JSON.stringify(matches, null, 2));
    console.log('\nFull results saved to test-results.json');

  } catch (err) {
    console.error('Test failed:', err);
    process.exit(1);
  }
}

test();
