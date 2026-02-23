"""
FlashScore Hockey Scraper

Scrapes hockey matches and per-team last-15 goal statistics from FlashScore.
Goal categorization: <=5 goals, =6 goals, >=7 goals.
"""

import asyncio
from datetime import datetime, timedelta
from typing import TypedDict

from playwright.async_api import ElementHandle, Page, async_playwright

from .config import config
from .scraper import (
    BASE_URL,
    click_show_more_buttons,
    find_team_rank,
    normalize_team_name,
    scrape_league_standings,
)

HOCKEY_URL = f'{BASE_URL}/hockey/'

# ── Centralized CSS selectors for hockey pages ───────────────────────
# Mirrors volleyball SELECTORS structure; key diff: league_link uses hockey href.
HOCKEY_SELECTORS: dict[str, dict[str, str]] = {
    'matches': {
        'container': '.leagues--live, .event, [class*="sportName"]',
        'all_items': '.event__match, [class*="headerLeague"], [class*="divider"]',
        'title_text': '.headerLeague__title-text, [class*="title-text"], [class*="titleText"]',
        'category_text': '.headerLeague__category-text, [class*="category-text"]',
        'league_link': 'a.headerLeague__title, a[href*="/hockey/"]',
        'home_team': '.event__participant--home',
        'away_team': '.event__participant--away',
        'match_time': '.event__stage, .event__time, [class*="stage"]',
        'match_link': 'a[href*="/match/"]',
        '_class_header': 'headerLeague',
        '_class_divider': 'divider',
        '_class_match': 'event__match',
    },
    'navigation': {
        'next_day': (
            'button.calendar__navigation--tomorrow,'
            ' button[data-testid="calendar-next"],'
            ' [class*="calendar__navigation--next"],'
            ' .calendar__nav--next'
        ),
        'next_day_alt': (
            '[aria-label*="suivant"], [aria-label*="next"],'
            ' button.arrow--next, .calendar__direction--next'
        ),
    },
    'standings': {
        'table_row': '.ui-table__row',
        'cell_rank': '.tableCellRank',
        'cell_team': '.tableCellParticipant__name',
    },
    'h2h': {
        'section': '.h2h__section',
        'section_title': '.h2h__title, .section__title',
        'row': '.h2h__row',
        'result': '.h2h__result',
        'show_more_btn': 'button.wclButtonLink--h2h',
    },
}


# ── TypedDicts ────────────────────────────────────────────────────────
# Reuse count3/count4/count5 key names for injection compatibility.
# count3 = <=5 goals, count4 = =6 goals, count5 = >=7 goals


class GoalStats(TypedDict):
    count3: int  # <=5 goals
    count4: int  # =6 goals
    count5: int  # >=7 goals


class HockeyMatch(TypedDict):
    date: str
    time: str
    country: str
    league: str
    teamA: str
    rankA: str
    teamB: str
    rankB: str
    matchUrl: str


class HockeyMatchStats(TypedDict):
    teamAStats: GoalStats
    teamBStats: GoalStats


class HockeyMatchWithStats(HockeyMatch, HockeyMatchStats):
    pass


# ── Parsing helpers ───────────────────────────────────────────────────


def parse_hockey_score(text: str) -> tuple[int | None, int | None]:
    """Parse a hockey score string into (goals_a, goals_b).

    Handles formats: "4:2", "4-2", "4 - 2", "4 : 2".
    Strips OT/SO/AP/TB suffixes (e.g. "4:2 AP", "3-2 SO").
    Returns (None, None) if parsing fails.
    """
    if not text:
        return None, None

    text = text.strip()

    # Strip common overtime/shootout suffixes
    for suffix in ('AP', 'TB', 'SO', 'OT', 'P', 'ap', 'tb', 'so', 'ot', 'p'):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()

    # Try colon separator first (most common for hockey)
    for sep in (':', '-'):
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts) == 2:
                try:
                    return int(parts[0].strip()), int(parts[1].strip())
                except ValueError:
                    continue

    return None, None


async def count_goals_in_section(
    section: ElementHandle, max_matches: int = 15
) -> GoalStats:
    """Count goal distribution from an H2H section.

    Parses scores, sums total goals per match, categorizes:
    - count3: <=5 goals
    - count4: =6 goals
    - count5: >=7 goals

    Stops after max_matches (default 15).
    """
    rows = await section.query_selector_all(HOCKEY_SELECTORS['h2h']['row'])
    count3, count4, count5 = 0, 0, 0
    processed = 0

    for row in rows:
        if processed >= max_matches:
            break
        try:
            result_el = await row.query_selector(HOCKEY_SELECTORS['h2h']['result'])
            if not result_el:
                continue

            result_text = await result_el.text_content()
            if not result_text:
                continue

            goals_a, goals_b = parse_hockey_score(result_text)
            if goals_a is None or goals_b is None:
                continue

            total_goals = goals_a + goals_b
            processed += 1

            if total_goals <= 5:
                count3 += 1
            elif total_goals == 6:
                count4 += 1
            else:  # >= 7
                count5 += 1
        except Exception:
            pass

    return {'count3': count3, 'count4': count4, 'count5': count5}


# ── Match extraction ──────────────────────────────────────────────────


async def extract_hockey_matches_for_date(
    page: Page, days_offset: int = 1
) -> list[HockeyMatch]:
    """Extract hockey match info from the hockey page for a specific date.

    Args:
        page: Playwright page object
        days_offset: Number of days from today (0=today, 1=tomorrow, etc.)
    """
    await page.goto(HOCKEY_URL, wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(3000)

    # Navigate to the target date
    if days_offset > 0:
        print(f'Navigating to J+{days_offset}...')
        for _ in range(days_offset):
            next_button = await page.query_selector(
                HOCKEY_SELECTORS['navigation']['next_day']
            )
            if next_button:
                await next_button.click()
                await page.wait_for_timeout(2000)
            else:
                next_button = await page.query_selector(
                    HOCKEY_SELECTORS['navigation']['next_day_alt']
                )
                if next_button:
                    await next_button.click()
                    await page.wait_for_timeout(2000)
                else:
                    print('Warning: Could not find next day navigation button')

    matches: list[HockeyMatch] = []

    # Extract all data via JS evaluation
    extracted_data = await page.evaluate(
        """(sel) => {
        const results = [];
        let currentCountry = '';
        let currentLeague = '';
        let currentLeagueUrl = '';

        const container = document.querySelector(sel.container)?.parentElement || document.body;
        const allElements = container.querySelectorAll(sel.all_items);

        allElements.forEach(el => {
            const isHeader = el.className.includes(sel._class_header);
            const isDivider = el.className.includes(sel._class_divider);
            if (isHeader || isDivider) {
                const titleEl = el.querySelector(sel.title_text);
                if (titleEl) {
                    const fullTitle = titleEl.textContent?.trim() || '';
                    const categoryEl = el.querySelector(sel.category_text);
                    const categoryText = categoryEl?.textContent?.trim() || '';

                    if (categoryText) {
                        currentCountry = categoryText;
                        currentLeague = fullTitle;
                    } else {
                        const parts = fullTitle.split(':');
                        if (parts.length >= 2) {
                            currentCountry = parts[0].trim();
                            currentLeague = parts.slice(1).join(':').trim();
                        } else {
                            currentLeague = fullTitle;
                        }
                    }

                    const leagueLink = el.querySelector(sel.league_link);
                    if (leagueLink) {
                        const href = leagueLink.getAttribute('href') || '';
                        if (href && !href.includes('/match/')) {
                            currentLeagueUrl = href;
                        }
                    }
                }
                return;
            }

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
    }""",
        HOCKEY_SELECTORS['matches'],
    )

    target_date = datetime.now() + timedelta(days=days_offset)
    date_str = target_date.strftime('%d/%m/%Y')

    for data in extracted_data:
        match_url = ''
        if data.get('href'):
            base_href = data['href']
            if not base_href.startswith('http'):
                base_href = f'{BASE_URL}{base_href}'
            base_href = base_href.split('?')[0].rstrip('/')
            match_url = f'{base_href}/tete-a-tete/global/'

        matches.append(
            {
                'date': date_str,
                'time': data.get('time', ''),
                'country': data.get('country', ''),
                'league': data.get('league', ''),
                'leagueUrl': data.get('leagueUrl', ''),
                'teamA': data['teamA'],
                'rankA': '',
                'teamB': data['teamB'],
                'rankB': '',
                'matchUrl': match_url,
            }
        )

    print(f'Found {len(matches)} hockey matches for {date_str}')
    return matches


# ── Per-team stats (no H2H / confrontation directe) ──────────────────


async def scrape_hockey_h2h_stats(
    page: Page, h2h_url: str, team_a: str = '', team_b: str = ''
) -> HockeyMatchStats:
    """Scrape per-team last-15 goal stats for a hockey match.

    Skips the "confrontation directe" section — only processes
    per-team sections with a 15-match limit.
    """
    default_stats: GoalStats = {'count3': 0, 'count4': 0, 'count5': 0}

    try:
        await page.goto(h2h_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        # Click all "Montrer plus" buttons to reveal all matches
        await click_show_more_buttons(page)
        await page.wait_for_timeout(500)

        sections = await page.query_selector_all(HOCKEY_SELECTORS['h2h']['section'])

        team_a_stats = default_stats.copy()
        team_b_stats = default_stats.copy()

        team_a_lower = team_a.lower()
        team_b_lower = team_b.lower()

        matched_a = False
        matched_b = False

        for section in sections:
            title_el = await section.query_selector(
                HOCKEY_SELECTORS['h2h']['section_title']
            )
            title = ''
            if title_el:
                title_text = await title_el.text_content()
                title = (title_text or '').lower()

            # Skip confrontation directe section
            if 'confrontation' in title:
                continue

            stats = await count_goals_in_section(section, max_matches=15)

            if team_a_lower and team_a_lower in title:
                team_a_stats = stats
                matched_a = True
            elif team_b_lower and team_b_lower in title:
                team_b_stats = stats
                matched_b = True

        # Fallback: assign unmatched sections by index (skip confrontation)
        if not (matched_a and matched_b):
            unmatched_sections = []
            for section in sections:
                title_el = await section.query_selector(
                    HOCKEY_SELECTORS['h2h']['section_title']
                )
                title = ''
                if title_el:
                    title_text = await title_el.text_content()
                    title = (title_text or '').lower()

                if 'confrontation' in title:
                    continue
                if matched_a and team_a_lower and team_a_lower in title:
                    continue
                if matched_b and team_b_lower and team_b_lower in title:
                    continue

                unmatched_sections.append(section)

            for section in unmatched_sections:
                stats = await count_goals_in_section(section, max_matches=15)
                if not matched_a:
                    team_a_stats = stats
                    matched_a = True
                elif not matched_b:
                    team_b_stats = stats
                    matched_b = True

        return {'teamAStats': team_a_stats, 'teamBStats': team_b_stats}
    except Exception as e:
        print(f'Error scraping hockey stats for {h2h_url}: {e}')
        return {'teamAStats': default_stats, 'teamBStats': default_stats}


# ── Selector validation ──────────────────────────────────────────────


async def validate_hockey_selectors(page: Page) -> None:
    """Spot-check critical selectors on the hockey page at startup."""
    try:
        await page.goto(HOCKEY_URL, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        checks = {
            'match rows': HOCKEY_SELECTORS['matches']['all_items'],
            'next-day nav': HOCKEY_SELECTORS['navigation']['next_day'],
        }

        all_ok = True
        for label, selector in checks.items():
            count = await page.evaluate(
                '(sel) => document.querySelectorAll(sel).length', selector
            )
            if count == 0:
                print(
                    f'  [selector-check] WARNING: "{label}" matched 0 elements ({selector})'
                )
                all_ok = False

        if all_ok:
            print('  [selector-check] All critical hockey selectors OK')
    except Exception as e:
        print(f'  [selector-check] Could not validate hockey selectors: {e}')


# ── Main entry point ─────────────────────────────────────────────────


async def scrape_hockey(days_offset: int = 0) -> list[HockeyMatchWithStats]:
    """Main hockey scraping function.

    Args:
        days_offset: Number of days from today to scrape.
    """
    print('Starting FlashScore hockey scraper...')
    target_date = datetime.now() + timedelta(days=days_offset)
    print(f'Target date: {target_date.strftime("%d/%m/%Y")} (J+{days_offset})')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale='fr-FR',
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                ' (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
        )
        page = await context.new_page()

        try:
            # Step 0: Validate selectors
            await validate_hockey_selectors(page)

            # Step 1: Get matches for target date
            print(f'Fetching hockey matches for {target_date.strftime("%d/%m/%Y")}...')
            matches = await extract_hockey_matches_for_date(page, days_offset)
            print(f'Found {len(matches)} hockey matches')

            # Step 2: Fetch standings for each unique league
            print('Fetching league standings for rankings...')
            league_standings: dict[str, dict[str, int]] = {}
            seen_leagues: set[str] = set()

            for match in matches:
                league_url = match.get('leagueUrl', '')
                league_key = (
                    league_url
                    or f'{match.get("country", "")}_{match.get("league", "")}'
                )

                if league_key and league_key not in seen_leagues:
                    seen_leagues.add(league_key)

                    if league_url:
                        full_url = (
                            f'{BASE_URL}{league_url}'
                            if not league_url.startswith('http')
                            else league_url
                        )
                        print(
                            f'  Fetching standings for: {match.get("league", league_url)}'
                        )
                        standings = await scrape_league_standings(page, full_url)

                        if standings:
                            league_standings[league_key] = standings

                    await page.wait_for_timeout(500)

            # Step 3: Apply rankings to matches
            for match in matches:
                league_url = match.get('leagueUrl', '')
                league_key = (
                    league_url
                    or f'{match.get("country", "")}_{match.get("league", "")}'
                )
                standings = league_standings.get(league_key, {})
                match['rankA'] = find_team_rank(match['teamA'], standings)
                match['rankB'] = find_team_rank(match['teamB'], standings)

            # Step 4: For each match, get per-team stats (no H2H)
            results: list[HockeyMatchWithStats] = []
            max_matches = config.scraper.max_matches or len(matches)
            matches_to_process = (
                matches[:max_matches] if max_matches > 0 else matches
            )

            for i, match in enumerate(matches_to_process):
                n = f'{i + 1}/{len(matches_to_process)}'
                print(
                    f'Processing match {n}: {match["teamA"]} vs {match["teamB"]}'
                )

                match_data = {k: v for k, v in match.items() if k != 'leagueUrl'}

                if match['matchUrl']:
                    stats = await scrape_hockey_h2h_stats(
                        page, match['matchUrl'], match['teamA'], match['teamB']
                    )
                    results.append({**match_data, **stats})
                else:
                    results.append(
                        {
                            **match_data,
                            'teamAStats': {'count3': 0, 'count4': 0, 'count5': 0},
                            'teamBStats': {'count3': 0, 'count4': 0, 'count5': 0},
                        }
                    )

                await page.wait_for_timeout(1000)

            return results
        finally:
            await browser.close()


if __name__ == '__main__':
    results = asyncio.run(scrape_hockey())
    print(f'\nScraped {len(results)} hockey matches')
