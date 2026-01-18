import { chromium } from 'playwright';
import config from './config.js';

const BASE_URL = 'https://www.flashscore.fr';
const VOLLEYBALL_URL = `${BASE_URL}/volleyball/`;

/**
 * Count sets distribution from a H2H section
 * @param {import('playwright').Page} page
 * @param {import('playwright').ElementHandle} section
 * @returns {Promise<{count3: number, count4: number, count5: number}>}
 */
async function countSetsInSection(section) {
  const rows = await section.$$('.h2h__row');
  let count3 = 0, count4 = 0, count5 = 0;

  for (const row of rows) {
    try {
      const resultEl = await row.$('.h2h__result');
      if (!resultEl) continue;

      const resultText = (await resultEl.textContent())?.trim();
      if (!resultText) continue;

      // Format can be "3 - 1", "3-1", or "31" (concatenated digits)
      let setsA, setsB;

      if (resultText.includes('-')) {
        // Format: "3-1" or "3 - 1"
        const parts = resultText.split('-').map(s => parseInt(s.trim(), 10));
        if (parts.length !== 2 || isNaN(parts[0]) || isNaN(parts[1])) continue;
        setsA = parts[0];
        setsB = parts[1];
      } else if (resultText.length === 2) {
        // Format: "31" (concatenated digits)
        setsA = parseInt(resultText[0], 10);
        setsB = parseInt(resultText[1], 10);
        if (isNaN(setsA) || isNaN(setsB)) continue;
      } else {
        continue;
      }

      const totalSets = setsA + setsB; // 3-0→3, 3-1→4, 3-2→5

      if (totalSets === 3) count3++;
      else if (totalSets === 4) count4++;
      else if (totalSets === 5) count5++;
    } catch (e) {
      // Skip malformed rows
    }
  }

  return { count3, count4, count5 };
}

/**
 * Click all "Montrer plus" buttons to reveal hidden matches
 * @param {import('playwright').Page} page
 */
async function clickShowMoreButtons(page) {
  let clicked = true;
  while (clicked) {
    clicked = false;
    const buttons = await page.$$('button.wclButtonLink--h2h');
    for (const btn of buttons) {
      try {
        const isVisible = await btn.isVisible();
        if (isVisible) {
          await btn.click();
          clicked = true;
          await page.waitForTimeout(300);
        }
      } catch (e) {
        // Button may have been removed
      }
    }
  }
}

/**
 * Extract match info from the main volleyball page
 * @param {import('playwright').Page} page
 * @returns {Promise<Array<{date: string, time: string, country: string, league: string, teamA: string, rankA: string, teamB: string, rankB: string, matchUrl: string}>>}
 */
async function extractTodayMatches(page) {
  await page.goto(VOLLEYBALL_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);

  const matches = [];

  // Use page.evaluate to extract all data at once for better performance and accuracy
  const extractedData = await page.evaluate(() => {
    const results = [];
    let currentCountry = '';
    let currentLeague = '';

    // Get all elements in the event container
    const container = document.querySelector('.leagues--live, .event, [class*="sportName"]')?.parentElement || document.body;
    const allElements = container.querySelectorAll('.event__match, [class*="headerLeague"], [class*="divider"]');

    allElements.forEach(el => {
      // Check if it's a league header
      if (el.className.includes('headerLeague') || el.className.includes('divider')) {
        const titleEl = el.querySelector('.headerLeague__title-text, [class*="title-text"], [class*="titleText"]');
        if (titleEl) {
          const fullTitle = titleEl.textContent?.trim() || '';
          // Extract country from flag title or parse from text
          const flagEl = el.querySelector('[class*="flag"]');
          const flagTitle = flagEl?.getAttribute('title') || '';

          if (flagTitle) {
            // Flag title format: "Country" or contains country name
            currentCountry = flagTitle.split('(')[0]?.trim() || flagTitle;
            currentLeague = fullTitle;
          } else {
            // Try to split "Country: League" format
            const parts = fullTitle.split(':');
            if (parts.length >= 2) {
              currentCountry = parts[0].trim();
              currentLeague = parts.slice(1).join(':').trim();
            } else {
              currentLeague = fullTitle;
            }
          }
        }
        return;
      }

      // It's a match
      if (el.className.includes('event__match')) {
        const homeEl = el.querySelector('.event__participant--home');
        const awayEl = el.querySelector('.event__participant--away');
        const timeEl = el.querySelector('.event__stage, .event__time, [class*="stage"]');
        const linkEl = el.querySelector('a[href*="/match/"]');

        const teamA = homeEl?.textContent?.trim() || '';
        const teamB = awayEl?.textContent?.trim() || '';
        const time = timeEl?.textContent?.trim() || '';
        const href = linkEl?.getAttribute('href') || '';

        if (teamA && teamB) {
          results.push({
            country: currentCountry,
            league: currentLeague,
            teamA,
            teamB,
            time,
            href
          });
        }
      }
    });

    return results;
  });

  // Process extracted data
  for (const data of extractedData) {
    // Build H2H URL
    let matchUrl = '';
    if (data.href) {
      let baseHref = data.href.startsWith('http') ? data.href : `${BASE_URL}${data.href}`;
      baseHref = baseHref.split('?')[0].replace(/\/$/, '');
      matchUrl = `${baseHref}/tete-a-tete/global/`;
    }

    // Today's date
    const today = new Date();
    const dateStr = today.toLocaleDateString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    });

    matches.push({
      date: dateStr,
      time: data.time || '',
      country: data.country || '',
      league: data.league || '',
      teamA: data.teamA,
      rankA: '',
      teamB: data.teamB,
      rankB: '',
      matchUrl
    });
  }

  console.log(`Found ${matches.length} matches`);
  return matches;
}

/**
 * Scrape H2H stats for a specific match
 * @param {import('playwright').Page} page
 * @param {string} h2hUrl
 * @returns {Promise<{teamAStats: {count3: number, count4: number, count5: number}, teamBStats: {count3: number, count4: number, count5: number}, h2hStats: {count3: number, count4: number, count5: number}}>}
 */
async function scrapeH2HStats(page, h2hUrl) {
  const defaultStats = { count3: 0, count4: 0, count5: 0 };

  try {
    await page.goto(h2hUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);

    // Click all "Montrer plus" buttons to reveal all matches
    await clickShowMoreButtons(page);
    await page.waitForTimeout(500);

    // Get all H2H sections
    const sections = await page.$$('.h2h__section');

    let teamAStats = { ...defaultStats };
    let teamBStats = { ...defaultStats };
    let h2hStats = { ...defaultStats };

    for (let i = 0; i < sections.length; i++) {
      const section = sections[i];

      // Get section title to identify which section it is
      const titleEl = await section.$('.h2h__title, .section__title');
      const title = titleEl ? (await titleEl.textContent())?.toLowerCase() || '' : '';

      const stats = await countSetsInSection(section);

      // Identify section by index (typically: 0=Team A, 1=Team B, 2=H2H)
      // Or by title containing team names or "confrontations"
      if (i === 0 || title.includes('derniers matchs')) {
        if (i === 0) teamAStats = stats;
        else if (i === 1) teamBStats = stats;
      } else if (title.includes('confrontation') || i === 2) {
        h2hStats = stats;
      }

      // Fallback: assign by index
      if (i === 0) teamAStats = stats;
      else if (i === 1) teamBStats = stats;
      else if (i === 2) h2hStats = stats;
    }

    return { teamAStats, teamBStats, h2hStats };
  } catch (e) {
    console.error(`Error scraping H2H for ${h2hUrl}:`, e.message);
    return { teamAStats: defaultStats, teamBStats: defaultStats, h2hStats: defaultStats };
  }
}

/**
 * Main scraping function
 * @param {boolean} headless - Run browser in headless mode
 * @returns {Promise<Array>}
 */
export async function scrapeFlashScore(headless = true) {
  console.log('Starting FlashScore volleyball scraper...');

  const browser = await chromium.launch({ headless });
  const context = await browser.newContext({
    locale: 'fr-FR',
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();

  try {
    // Step 1: Get today's matches
    console.log('Fetching today\'s matches...');
    const matches = await extractTodayMatches(page);
    console.log(`Found ${matches.length} matches`);

    // Step 2: For each match, get H2H stats
    const results = [];
    const maxMatches = config.scraper.maxMatches || matches.length;
    const matchesToProcess = maxMatches > 0 ? matches.slice(0, maxMatches) : matches;

    for (let i = 0; i < matchesToProcess.length; i++) {
      const match = matchesToProcess[i];
      console.log(`Processing match ${i + 1}/${matchesToProcess.length}: ${match.teamA} vs ${match.teamB}`);

      if (match.matchUrl) {
        const stats = await scrapeH2HStats(page, match.matchUrl);
        results.push({
          ...match,
          ...stats
        });
      } else {
        results.push({
          ...match,
          teamAStats: { count3: 0, count4: 0, count5: 0 },
          teamBStats: { count3: 0, count4: 0, count5: 0 },
          h2hStats: { count3: 0, count4: 0, count5: 0 }
        });
      }

      // Small delay between requests
      await page.waitForTimeout(1000);
    }

    return results;
  } finally {
    await browser.close();
  }
}

export default { scrapeFlashScore };
