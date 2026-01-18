"""
FlashScore Volleyball Scraper

Scrapes volleyball matches and H2H statistics from FlashScore
"""

import asyncio
from datetime import datetime
from typing import TypedDict
from playwright.async_api import async_playwright, Page, ElementHandle

from config import config

BASE_URL = 'https://www.flashscore.fr'
VOLLEYBALL_URL = f'{BASE_URL}/volleyball/'


class SetStats(TypedDict):
    count3: int
    count4: int
    count5: int


class MatchStats(TypedDict):
    teamAStats: SetStats
    teamBStats: SetStats
    h2hStats: SetStats


class Match(TypedDict):
    date: str
    time: str
    country: str
    league: str
    teamA: str
    rankA: str
    teamB: str
    rankB: str
    matchUrl: str


class MatchWithStats(Match, MatchStats):
    pass


async def count_sets_in_section(section: ElementHandle) -> SetStats:
    """
    Count sets distribution from a H2H section
    """
    rows = await section.query_selector_all('.h2h__row')
    count3, count4, count5 = 0, 0, 0

    for row in rows:
        try:
            result_el = await row.query_selector('.h2h__result')
            if not result_el:
                continue

            result_text = await result_el.text_content()
            if not result_text:
                continue

            result_text = result_text.strip()

            # Format can be "3 - 1", "3-1", or "31" (concatenated digits)
            sets_a, sets_b = None, None

            if '-' in result_text:
                # Format: "3-1" or "3 - 1"
                parts = result_text.split('-')
                if len(parts) != 2:
                    continue
                try:
                    sets_a = int(parts[0].strip())
                    sets_b = int(parts[1].strip())
                except ValueError:
                    continue
            elif len(result_text) == 2:
                # Format: "31" (concatenated digits)
                try:
                    sets_a = int(result_text[0])
                    sets_b = int(result_text[1])
                except ValueError:
                    continue
            else:
                continue

            total_sets = sets_a + sets_b  # 3-0→3, 3-1→4, 3-2→5

            if total_sets == 3:
                count3 += 1
            elif total_sets == 4:
                count4 += 1
            elif total_sets == 5:
                count5 += 1
        except Exception:
            # Skip malformed rows
            pass

    return {'count3': count3, 'count4': count4, 'count5': count5}


async def click_show_more_buttons(page: Page) -> None:
    """
    Click all "Montrer plus" buttons to reveal hidden matches
    """
    clicked = True
    while clicked:
        clicked = False
        buttons = await page.query_selector_all('button.wclButtonLink--h2h')
        for btn in buttons:
            try:
                is_visible = await btn.is_visible()
                if is_visible:
                    await btn.click()
                    clicked = True
                    await page.wait_for_timeout(300)
            except Exception:
                # Button may have been removed
                pass


async def extract_today_matches(page: Page) -> list[Match]:
    """
    Extract match info from the main volleyball page
    """
    await page.goto(VOLLEYBALL_URL, wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(3000)

    matches: list[Match] = []

    # Use page.evaluate to extract all data at once for better performance and accuracy
    extracted_data = await page.evaluate('''() => {
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
    }''')

    # Process extracted data
    for data in extracted_data:
        # Build H2H URL
        match_url = ''
        if data.get('href'):
            base_href = data['href']
            if not base_href.startswith('http'):
                base_href = f'{BASE_URL}{base_href}'
            base_href = base_href.split('?')[0].rstrip('/')
            match_url = f'{base_href}/tete-a-tete/global/'

        # Today's date (French format)
        today = datetime.now()
        date_str = today.strftime('%d/%m/%Y')

        matches.append({
            'date': date_str,
            'time': data.get('time', ''),
            'country': data.get('country', ''),
            'league': data.get('league', ''),
            'teamA': data['teamA'],
            'rankA': '',
            'teamB': data['teamB'],
            'rankB': '',
            'matchUrl': match_url
        })

    print(f'Found {len(matches)} matches')
    return matches


async def scrape_h2h_stats(page: Page, h2h_url: str) -> MatchStats:
    """
    Scrape H2H stats for a specific match
    """
    default_stats: SetStats = {'count3': 0, 'count4': 0, 'count5': 0}

    try:
        await page.goto(h2h_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        # Click all "Montrer plus" buttons to reveal all matches
        await click_show_more_buttons(page)
        await page.wait_for_timeout(500)

        # Get all H2H sections
        sections = await page.query_selector_all('.h2h__section')

        team_a_stats = default_stats.copy()
        team_b_stats = default_stats.copy()
        h2h_stats = default_stats.copy()

        for i, section in enumerate(sections):
            # Get section title to identify which section it is
            title_el = await section.query_selector('.h2h__title, .section__title')
            title = ''
            if title_el:
                title_text = await title_el.text_content()
                title = (title_text or '').lower()

            stats = await count_sets_in_section(section)

            # Identify section by index (typically: 0=Team A, 1=Team B, 2=H2H)
            # Or by title containing team names or "confrontations"
            if i == 0 or 'derniers matchs' in title:
                if i == 0:
                    team_a_stats = stats
                elif i == 1:
                    team_b_stats = stats
            elif 'confrontation' in title or i == 2:
                h2h_stats = stats

            # Fallback: assign by index
            if i == 0:
                team_a_stats = stats
            elif i == 1:
                team_b_stats = stats
            elif i == 2:
                h2h_stats = stats

        return {
            'teamAStats': team_a_stats,
            'teamBStats': team_b_stats,
            'h2hStats': h2h_stats
        }
    except Exception as e:
        print(f'Error scraping H2H for {h2h_url}: {e}')
        return {
            'teamAStats': default_stats,
            'teamBStats': default_stats,
            'h2hStats': default_stats
        }


async def scrape_flashscore(headless: bool = True) -> list[MatchWithStats]:
    """
    Main scraping function
    """
    print('Starting FlashScore volleyball scraper...')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            locale='fr-FR',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            # Step 1: Get today's matches
            print("Fetching today's matches...")
            matches = await extract_today_matches(page)
            print(f'Found {len(matches)} matches')

            # Step 2: For each match, get H2H stats
            results: list[MatchWithStats] = []
            max_matches = config.scraper.max_matches or len(matches)
            matches_to_process = matches[:max_matches] if max_matches > 0 else matches

            for i, match in enumerate(matches_to_process):
                print(f"Processing match {i + 1}/{len(matches_to_process)}: {match['teamA']} vs {match['teamB']}")

                if match['matchUrl']:
                    stats = await scrape_h2h_stats(page, match['matchUrl'])
                    results.append({
                        **match,
                        **stats
                    })
                else:
                    results.append({
                        **match,
                        'teamAStats': {'count3': 0, 'count4': 0, 'count5': 0},
                        'teamBStats': {'count3': 0, 'count4': 0, 'count5': 0},
                        'h2hStats': {'count3': 0, 'count4': 0, 'count5': 0}
                    })

                # Small delay between requests
                await page.wait_for_timeout(1000)

            return results
        finally:
            await browser.close()


if __name__ == '__main__':
    # Allow running scraper directly for testing
    results = asyncio.run(scrape_flashscore(headless=False))
    print(f'\nScraped {len(results)} matches')
