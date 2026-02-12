"""
FlashScore Volleyball Scraper

Scrapes volleyball matches and H2H statistics from FlashScore
"""

import asyncio
from datetime import datetime, timedelta
from typing import TypedDict
from playwright.async_api import async_playwright, Page, ElementHandle

from config import config

BASE_URL = 'https://www.flashscore.fr'
VOLLEYBALL_URL = f'{BASE_URL}/volleyball/'

# ── Centralized CSS selectors ──────────────────────────────────────────
# When FlashScore changes their HTML, update selectors here only.
# Values that contain commas are native CSS fallback chains (first match wins).
# Keys prefixed with _class_ are used in JS className.includes() checks.
SELECTORS: dict[str, dict[str, str]] = {
    'matches': {
        'container':        '.leagues--live, .event, [class*="sportName"]',
        'all_items':        '.event__match, [class*="headerLeague"], [class*="divider"]',
        'title_text':       '.headerLeague__title-text, [class*="title-text"], [class*="titleText"]',
        'category_text':    '.headerLeague__category-text, [class*="category-text"]',
        'league_link':      'a.headerLeague__title, a[href*="/volleyball/"]',
        'home_team':        '.event__participant--home',
        'away_team':        '.event__participant--away',
        'match_time':       '.event__stage, .event__time, [class*="stage"]',
        'match_link':       'a[href*="/match/"]',
        # className.includes() patterns used inside JS
        '_class_header':    'headerLeague',
        '_class_divider':   'divider',
        '_class_match':     'event__match',
    },
    'navigation': {
        'next_day':         'button.calendar__navigation--tomorrow, button[data-testid="calendar-next"], [class*="calendar__navigation--next"], .calendar__nav--next',
        'next_day_alt':     '[aria-label*="suivant"], [aria-label*="next"], button.arrow--next, .calendar__direction--next',
    },
    'standings': {
        'table_row':        '.ui-table__row',
        'cell_rank':        '.tableCellRank',
        'cell_team':        '.tableCellParticipant__name',
    },
    'h2h': {
        'section':          '.h2h__section',
        'section_title':    '.h2h__title, .section__title',
        'row':              '.h2h__row',
        'result':           '.h2h__result',
        'show_more_btn':    'button.wclButtonLink--h2h',
    },
}


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
    rows = await section.query_selector_all(SELECTORS['h2h']['row'])
    count3, count4, count5 = 0, 0, 0

    for row in rows:
        try:
            result_el = await row.query_selector(SELECTORS['h2h']['result'])
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


async def scrape_league_standings(page: Page, league_url: str) -> dict[str, int]:
    """
    Scrape team standings/rankings for a league.
    Returns a dict mapping team name (lowercase) to rank.
    Tries alternative URL patterns if primary fails.
    """
    # URL translations for common French/English variations
    url_alternatives = [
        league_url,
        league_url.replace('-femmes', '-women').replace('-hommes', '-men'),
        league_url.replace('-women', '-femmes').replace('-men', '-hommes'),
        league_url.replace('feminine', 'women').replace('masculin', 'men'),
        league_url.replace('liga-femmes', 'liga-women'),
        league_url.replace('liga-women', 'liga-femmes'),
    ]
    # Remove duplicates while preserving order
    url_alternatives = list(dict.fromkeys(url_alternatives))

    rankings: dict[str, int] = {}

    for url in url_alternatives:
        standings_url = f'{url.rstrip("/")}/classement/'

        try:

            # Use domcontentloaded with longer wait - more reliable than networkidle
            await page.goto(standings_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(5000)  # Extra wait for table to render

            # Extract standings using the table structure
            data = await page.evaluate('''(sel) => {
                const rows = document.querySelectorAll(sel.table_row);
                const standings = [];

                rows.forEach(row => {
                    const rankEl = row.querySelector(sel.cell_rank);
                    const teamEl = row.querySelector(sel.cell_team);

                    if (rankEl && teamEl) {
                        const rankText = rankEl.textContent?.trim().replace('.', '');
                        const rank = parseInt(rankText) || 0;
                        const team = teamEl.textContent?.trim() || '';
                        if (rank > 0 && team) {
                            standings.push({rank, team});
                        }
                    }
                });

                return standings;
            }''', SELECTORS['standings'])

            for item in data:
                # Store with both original lowercase and normalized keys for better matching
                team_lower = item['team'].lower()
                rankings[team_lower] = item['rank']
                # Also store normalized version (without suffixes like " f", " w")
                normalized = team_lower
                for suffix in [' f', ' w', ' (f)', ' (w)', ' femmes', ' women']:
                    if normalized.endswith(suffix):
                        normalized = normalized[:-len(suffix)]
                        break
                if normalized != team_lower:
                    rankings[normalized] = item['rank']

            if rankings:
                print(f'  Found {len(rankings)} teams in standings')
                break  # Success, no need to try other URLs

        except Exception:
            continue  # Try next URL alternative

    return rankings


def normalize_team_name(name: str) -> str:
    """Normalize team name for matching (lowercase, remove common suffixes)."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [' f', ' w', ' (f)', ' (w)', ' femmes', ' women']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name


def find_team_rank(team_name: str, standings: dict[str, int]) -> str:
    """Find team rank from standings, trying various name matches."""
    if not standings:
        return ''

    normalized = normalize_team_name(team_name)

    # Try exact match first
    if normalized in standings:
        return str(standings[normalized])

    # Try partial matching (team name contains or is contained in standings name)
    for standing_team, rank in standings.items():
        if normalized in standing_team or standing_team in normalized:
            return str(rank)

    return ''


async def click_show_more_buttons(page: Page) -> None:
    """
    Click all "Montrer plus" buttons to reveal hidden matches
    """
    clicked = True
    while clicked:
        clicked = False
        buttons = await page.query_selector_all(SELECTORS['h2h']['show_more_btn'])
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


async def extract_matches_for_date(page: Page, days_offset: int = 1) -> list[Match]:
    """
    Extract match info from the volleyball page for a specific date.

    Args:
        page: Playwright page object
        days_offset: Number of days from today (0=today, 1=tomorrow, etc.)
                     Default is 1 (tomorrow / J+1)
    """
    await page.goto(VOLLEYBALL_URL, wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(3000)

    # Navigate to the target date by clicking the date navigation arrows
    if days_offset > 0:
        print(f'Navigating to J+{days_offset} (tomorrow)...')
        for _ in range(days_offset):
            # Click the "next day" arrow button
            next_button = await page.query_selector(SELECTORS['navigation']['next_day'])
            if next_button:
                await next_button.click()
                await page.wait_for_timeout(2000)
            else:
                # Try clicking by aria-label or other selectors
                next_button = await page.query_selector(SELECTORS['navigation']['next_day_alt'])
                if next_button:
                    await next_button.click()
                    await page.wait_for_timeout(2000)
                else:
                    print('Warning: Could not find next day navigation button')

    matches: list[Match] = []

    # Use page.evaluate to extract all data at once for better performance and accuracy
    extracted_data = await page.evaluate('''(sel) => {
        const results = [];
        let currentCountry = '';
        let currentLeague = '';
        let currentLeagueUrl = '';

        // Get all elements in the event container
        const container = document.querySelector(sel.container)?.parentElement || document.body;
        const allElements = container.querySelectorAll(sel.all_items);

        allElements.forEach(el => {
            // Check if it's a league header
            if (el.className.includes(sel._class_header) || el.className.includes(sel._class_divider)) {
                const titleEl = el.querySelector(sel.title_text);
                if (titleEl) {
                    const fullTitle = titleEl.textContent?.trim() || '';
                    // Extract country from category text
                    const categoryEl = el.querySelector(sel.category_text);
                    const categoryText = categoryEl?.textContent?.trim() || '';

                    if (categoryText) {
                        currentCountry = categoryText;
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

                    // Extract league URL from the header link
                    const leagueLink = el.querySelector(sel.league_link);
                    if (leagueLink) {
                        const href = leagueLink.getAttribute('href') || '';
                        // Only use league URLs (not match URLs)
                        if (href && !href.includes('/match/')) {
                            currentLeagueUrl = href;
                        }
                    }
                }
                return;
            }

            // It's a match
            if (el.className.includes(sel._class_match)) {
                const homeEl = el.querySelector(sel.home_team);
                const awayEl = el.querySelector(sel.away_team);
                const timeEl = el.querySelector(sel.match_time);
                const linkEl = el.querySelector(sel.match_link);

                const teamA = homeEl?.textContent?.trim() || '';
                const teamB = awayEl?.textContent?.trim() || '';
                const time = timeEl?.textContent?.trim() || '';
                const href = linkEl?.getAttribute('href') || '';

                if (teamA && teamB) {
                    results.push({
                        country: currentCountry,
                        league: currentLeague,
                        leagueUrl: currentLeagueUrl,
                        teamA,
                        teamB,
                        time,
                        href
                    });
                }
            }
        });

        return results;
    }''', SELECTORS['matches'])

    # Calculate target date (French format)
    target_date = datetime.now() + timedelta(days=days_offset)
    date_str = target_date.strftime('%d/%m/%Y')

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

        matches.append({
            'date': date_str,
            'time': data.get('time', ''),
            'country': data.get('country', ''),
            'league': data.get('league', ''),
            'leagueUrl': data.get('leagueUrl', ''),  # Used internally to fetch standings
            'teamA': data['teamA'],
            'rankA': '',
            'teamB': data['teamB'],
            'rankB': '',
            'matchUrl': match_url
        })

    print(f'Found {len(matches)} matches for {date_str}')
    return matches


# Keep old function name as alias for backward compatibility
async def extract_today_matches(page: Page) -> list[Match]:
    """Extract today's matches (legacy function, use extract_matches_for_date instead)"""
    return await extract_matches_for_date(page, days_offset=0)


async def scrape_h2h_stats(page: Page, h2h_url: str, team_a: str = '', team_b: str = '') -> MatchStats:
    """
    Scrape H2H stats for a specific match.

    Args:
        page: Playwright page object
        h2h_url: URL of the H2H page
        team_a: Home team name (used to match section titles)
        team_b: Away team name (used to match section titles)
    """
    default_stats: SetStats = {'count3': 0, 'count4': 0, 'count5': 0}

    try:
        await page.goto(h2h_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        # Click all "Montrer plus" buttons to reveal all matches
        await click_show_more_buttons(page)
        await page.wait_for_timeout(500)

        # Get all H2H sections
        sections = await page.query_selector_all(SELECTORS['h2h']['section'])

        team_a_stats = default_stats.copy()
        team_b_stats = default_stats.copy()
        h2h_stats = default_stats.copy()

        team_a_lower = team_a.lower()
        team_b_lower = team_b.lower()

        # Track which teams we've matched by title
        matched_a = False
        matched_b = False
        matched_h2h = False

        for section in sections:
            # Get section title to identify which section it is
            title_el = await section.query_selector(SELECTORS['h2h']['section_title'])
            title = ''
            if title_el:
                title_text = await title_el.text_content()
                title = (title_text or '').lower()

            stats = await count_sets_in_section(section)

            # Match by title content: "Derniers matchs de [Team]" or "Confrontations directes"
            if 'confrontation' in title:
                h2h_stats = stats
                matched_h2h = True
            elif team_a_lower and team_a_lower in title:
                team_a_stats = stats
                matched_a = True
            elif team_b_lower and team_b_lower in title:
                team_b_stats = stats
                matched_b = True

        # Fallback: if title matching failed, assign unmatched sections by index
        if not (matched_a and matched_b and matched_h2h):
            unmatched_sections = []
            for i, section in enumerate(sections):
                title_el = await section.query_selector(SELECTORS['h2h']['section_title'])
                title = ''
                if title_el:
                    title_text = await title_el.text_content()
                    title = (title_text or '').lower()

                # Skip sections already matched
                if matched_h2h and 'confrontation' in title:
                    continue
                if matched_a and team_a_lower and team_a_lower in title:
                    continue
                if matched_b and team_b_lower and team_b_lower in title:
                    continue

                unmatched_sections.append(section)

            # Assign unmatched sections by order to unfilled slots
            for section in unmatched_sections:
                stats = await count_sets_in_section(section)
                if not matched_a:
                    team_a_stats = stats
                    matched_a = True
                elif not matched_b:
                    team_b_stats = stats
                    matched_b = True
                elif not matched_h2h:
                    h2h_stats = stats
                    matched_h2h = True

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


async def validate_selectors(page: Page) -> None:
    """
    Spot-check critical selectors on the volleyball page at startup.
    Prints warnings for any selector matching 0 elements.
    Non-blocking: scraping continues regardless of results.
    """
    try:
        await page.goto(VOLLEYBALL_URL, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        checks = {
            'match rows':   SELECTORS['matches']['all_items'],
            'next-day nav': SELECTORS['navigation']['next_day'],
        }

        all_ok = True
        for label, selector in checks.items():
            # Use first selector in a comma-separated fallback chain
            count = await page.evaluate(
                '(sel) => document.querySelectorAll(sel).length', selector
            )
            if count == 0:
                print(f'  [selector-check] WARNING: "{label}" matched 0 elements ({selector})')
                all_ok = False

        if all_ok:
            print('  [selector-check] All critical selectors OK')
    except Exception as e:
        print(f'  [selector-check] Could not validate selectors: {e}')


async def scrape_flashscore(days_offset: int = 0) -> list[MatchWithStats]:
    """
    Main scraping function.

    Args:
        days_offset: Number of days from today to scrape.
                     Default is 1 (tomorrow / J+1) for the scheduled cron job.
                     Use 0 for today's matches.
    """
    print('Starting FlashScore volleyball scraper...')
    target_date = datetime.now() + timedelta(days=days_offset)
    print(f'Target date: {target_date.strftime("%d/%m/%Y")} (J+{days_offset})')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale='fr-FR',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            # Step 0: Validate selectors (non-blocking)
            await validate_selectors(page)

            # Step 1: Get matches for target date (default: tomorrow)
            print(f"Fetching matches for {target_date.strftime('%d/%m/%Y')}...")
            matches = await extract_matches_for_date(page, days_offset)
            print(f'Found {len(matches)} matches')

            # Step 2: Fetch standings for each unique league to get rankings
            print("Fetching league standings for rankings...")
            league_standings: dict[str, dict[str, int]] = {}
            seen_leagues: set[str] = set()

            for match in matches:
                league_url = match.get('leagueUrl', '')
                league_key = league_url or f"{match.get('country', '')}_{match.get('league', '')}"

                if league_key and league_key not in seen_leagues:
                    seen_leagues.add(league_key)

                    if league_url:
                        full_url = f'{BASE_URL}{league_url}' if not league_url.startswith('http') else league_url
                        print(f'  Fetching standings for: {match.get("league", league_url)}')
                        standings = await scrape_league_standings(page, full_url)

                        if standings:
                            league_standings[league_key] = standings

                    await page.wait_for_timeout(500)

            # Step 3: Apply rankings to matches
            for match in matches:
                league_url = match.get('leagueUrl', '')
                league_key = league_url or f"{match.get('country', '')}_{match.get('league', '')}"
                standings = league_standings.get(league_key, {})
                match['rankA'] = find_team_rank(match['teamA'], standings)
                match['rankB'] = find_team_rank(match['teamB'], standings)

            # Step 4: For each match, get H2H stats
            results: list[MatchWithStats] = []
            max_matches = config.scraper.max_matches or len(matches)
            matches_to_process = matches[:max_matches] if max_matches > 0 else matches

            for i, match in enumerate(matches_to_process):
                print(f"Processing match {i + 1}/{len(matches_to_process)}: {match['teamA']} vs {match['teamB']}")

                # Remove internal leagueUrl field from output
                match_data = {k: v for k, v in match.items() if k != 'leagueUrl'}

                if match['matchUrl']:
                    stats = await scrape_h2h_stats(page, match['matchUrl'], match['teamA'], match['teamB'])
                    results.append({
                        **match_data,
                        **stats
                    })
                else:
                    results.append({
                        **match_data,
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
    results = asyncio.run(scrape_flashscore())
    print(f'\nScraped {len(results)} matches')
