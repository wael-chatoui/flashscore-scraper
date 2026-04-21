"""
FlashScore Base Scraper

Shared infrastructure for all sport scrapers: browser setup, match extraction,
standings, rankings, date navigation, and the main scraper pipeline.
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, TypedDict

from playwright.async_api import Page, async_playwright

from .config import config

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_S = 2
PER_MATCH_TIMEOUT_S = 90  # seconds per match H2H scraping
GLOBAL_TIMEOUT_S = 2 * 3600  # 2 hours total for match processing loop
PARTIAL_SAVE_INTERVAL = 25  # save partial results every N matches
MAX_SHOW_MORE_CLICKS = 30  # cap show-more button clicks to prevent infinite loops
BATCH_SIZE = 30  # pause after every N matches
BATCH_COOLDOWN_S = 90  # seconds to pause between batches
CONSECUTIVE_EMPTY_LIMIT = 3  # trigger cooldown after N consecutive empty results
RATE_LIMIT_COOLDOWN_S = 180  # seconds to wait when rate-limited

BASE_URL = 'https://www.flashscore.fr'


# ── Shared TypedDict ─────────────────────────────────────────────────


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


# ── Shared CSS selectors ─────────────────────────────────────────────

# Selectors identical across all sports (matches, standings, h2h).
_SHARED_SELECTORS: dict[str, dict[str, str]] = {
    'matches': {
        'container': '.leagues--live, .event, [class*="sportName"]',
        'all_items': '.event__match, [class*="headerLeague"], [class*="divider"]',
        'title_text': '.headerLeague__title-text, [class*="title-text"], [class*="titleText"]',
        'category_text': '.headerLeague__category-text, [class*="category-text"]',
        'home_team': '.event__participant--home, .event__homeParticipant',
        'away_team': '.event__participant--away, .event__awayParticipant',
        'match_time': '.event__stage, .event__time, [class*="stage"]',
        'match_link': 'a[href*="/match/"]',
        '_class_header': 'headerLeague',
        '_class_divider': 'divider',
        '_class_match': 'event__match',
    },
    'standings': {
        'table_row': '.ui-table__row',
        'cell_rank': '.tableCellRank',
        'cell_team': '.tableCellParticipant__name',
    },
    'h2h': {
        'section': '.h2h__section',
        'section_title': ('.h2h__title, .section__title, [data-testid="wcl-scores-overline-02"]'),
        'row': '.h2h__row',
        'result': '.h2h__result',
        'show_more_btn': 'button.wclButtonLink--h2h',
    },
}


def build_selectors(
    league_link: str,
    navigation: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Build a full SELECTORS dict from sport-specific league_link and navigation.

    Args:
        league_link: CSS selector for league header links (e.g. 'a[href*="/volleyball/"]')
        navigation: Dict with 'next_day', 'next_day_alt', and optionally 'prev_day', 'prev_day_alt'
    """
    selectors: dict[str, dict[str, str]] = {
        'matches': {**_SHARED_SELECTORS['matches'], 'league_link': league_link},
        'navigation': navigation,
        'standings': {**_SHARED_SELECTORS['standings']},
        'h2h': {**_SHARED_SELECTORS['h2h']},
    }
    return selectors


# ── Retry helper ────────────────────────────────────────────────────


async def goto_with_retry(
    page: Page, url: str, *, timeout: int = 30000, retries: int = MAX_RETRIES
) -> None:
    """Navigate to a URL with retry on failure."""
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            return
        except Exception as e:
            if attempt == retries:
                raise
            logger.debug('Retry %d/%d for %s: %s', attempt, retries, url, e)
            await asyncio.sleep(RETRY_DELAY_S * attempt)


# ── Utilities ────────────────────────────────────────────────────────


async def accept_cookies(page: Page) -> None:
    """Dismiss cookie consent banner if present."""
    try:
        btn = await page.query_selector('#onetrust-accept-btn-handler')
        if btn:
            await btn.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass


def normalize_team_name(name: str) -> str:
    """Normalize team name for matching (lowercase, remove common suffixes)."""
    name = name.lower().strip()
    for suffix in [' f', ' w', ' (f)', ' (w)', ' femmes', ' women']:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
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


async def click_show_more_buttons(page: Page, max_clicks: int = MAX_SHOW_MORE_CLICKS) -> None:
    """Click all "Montrer plus" buttons to reveal hidden matches."""
    selector = _SHARED_SELECTORS['h2h']['show_more_btn']
    clicked = True
    total_clicks = 0
    while clicked:
        if total_clicks >= max_clicks:
            logger.warning(
                'Reached max show-more clicks (%d) — stopping to prevent infinite loop',
                max_clicks,
            )
            break
        clicked = False
        buttons = await page.query_selector_all(selector)
        for btn in buttons:
            if total_clicks >= max_clicks:
                break
            try:
                is_visible = await btn.is_visible()
                if is_visible:
                    await btn.click()
                    clicked = True
                    total_clicks += 1
                    await page.wait_for_timeout(300)
            except Exception:
                pass


# ── Shared scrapers ──────────────────────────────────────────────────


async def scrape_league_standings(page: Page, league_url: str) -> dict[str, int]:
    """Scrape team standings/rankings for a league.

    Returns a dict mapping team name (lowercase) to rank.
    Tries alternative URL patterns if primary fails.
    """
    url_alternatives = [
        league_url,
        league_url.replace('-femmes', '-women').replace('-hommes', '-men'),
        league_url.replace('-women', '-femmes').replace('-men', '-hommes'),
        league_url.replace('feminine', 'women').replace('masculin', 'men'),
        league_url.replace('liga-femmes', 'liga-women'),
        league_url.replace('liga-women', 'liga-femmes'),
    ]
    url_alternatives = list(dict.fromkeys(url_alternatives))

    standings_sel = _SHARED_SELECTORS['standings']
    rankings: dict[str, int] = {}

    for url in url_alternatives:
        standings_url = f'{url.rstrip("/")}/classement/'

        try:
            await goto_with_retry(page, standings_url)
            await page.wait_for_timeout(5000)

            data = await page.evaluate(
                """(sel) => {
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
            }""",
                standings_sel,
            )

            for item in data:
                team_lower = item['team'].lower()
                rankings[team_lower] = item['rank']
                normalized = team_lower
                for suffix in [' f', ' w', ' (f)', ' (w)', ' femmes', ' women']:
                    if normalized.endswith(suffix):
                        normalized = normalized[: -len(suffix)]
                        break
                if normalized != team_lower:
                    rankings[normalized] = item['rank']

            if rankings:
                logger.debug('Found %d teams in standings', len(rankings))
                break

        except Exception:
            continue

    return rankings


async def navigate_to_date(
    page: Page, selectors: dict[str, dict[str, str]], days_offset: int
) -> None:
    """Navigate to a target date by clicking navigation arrows.

    Supports both forward and backward navigation.
    """
    if days_offset == 0:
        return

    nav = selectors['navigation']
    steps = abs(days_offset)

    if days_offset > 0:
        logger.info('Navigating forward %d day(s)...', steps)
        primary_sel = nav['next_day']
        fallback_sel = nav.get('next_day_alt', '')
    else:
        logger.info('Navigating backward %d day(s)...', steps)
        primary_sel = nav.get('prev_day', nav['next_day'])
        fallback_sel = nav.get('prev_day_alt', nav.get('next_day_alt', ''))

    for _ in range(steps):
        btn = await page.query_selector(primary_sel)
        if not btn and fallback_sel:
            btn = await page.query_selector(fallback_sel)
        if btn:
            await btn.click(force=True)
            await page.wait_for_timeout(2000)
        else:
            logger.warning('Could not find date navigation button')


async def extract_matches_for_date(
    page: Page,
    sport_url: str,
    selectors: dict[str, dict[str, str]],
    days_offset: int = 1,
) -> list[dict[str, Any]]:
    """Extract match info from a sport page for a specific date.

    Returns a list of match dicts including an internal 'leagueUrl' key.
    """
    await goto_with_retry(page, sport_url)
    await page.wait_for_timeout(3000)

    await navigate_to_date(page, selectors, days_offset)

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

                // Extract current score if available (finished or live matches)
                const scoreHomeEl = el.querySelector('.event__score--home');
                const scoreAwayEl = el.querySelector('.event__score--away');
                const scoreHome = scoreHomeEl?.textContent?.trim() || '';
                const scoreAway = scoreAwayEl?.textContent?.trim() || '';

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
                        scoreHome,
                        scoreAway,
                        time,
                        href
                    });
                }
            }
        });

        return results;
    }""",
        selectors['matches'],
    )

    target_date = datetime.now() + timedelta(days=days_offset)
    date_str = target_date.strftime('%d/%m/%Y')

    matches: list[dict[str, Any]] = []
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
                'scoreHome': data.get('scoreHome', ''),
                'scoreAway': data.get('scoreAway', ''),
                'matchUrl': match_url,
            }
        )

    logger.info('Found %d matches for %s', len(matches), date_str)
    return matches


async def validate_page_selectors(page: Page, sport_url: str, checks: dict[str, str]) -> None:
    """Spot-check critical selectors on a sport page at startup.

    Non-blocking: scraping continues regardless of results.
    """
    try:
        await goto_with_retry(page, sport_url)
        await page.wait_for_timeout(3000)
        await accept_cookies(page)

        all_ok = True
        for label, selector in checks.items():
            count = await page.evaluate('(sel) => document.querySelectorAll(sel).length', selector)
            if count == 0:
                logger.warning('[selector-check] "%s" matched 0 elements (%s)', label, selector)
                all_ok = False

        if all_ok:
            logger.info('[selector-check] All critical selectors OK')
    except Exception as e:
        logger.warning('[selector-check] Could not validate selectors: %s', e)


# ── Rate-limit detection ─────────────────────────────────────────────


def _stats_are_empty(stats: dict[str, Any]) -> bool:
    """Check if scraped stats are empty (likely rate-limited).

    Handles both dict-based stats (volleyball: all-zero count dicts)
    and list-based stats (hockey: empty teamAScores/teamBScores).
    """
    for v in stats.values():
        if isinstance(v, list) and len(v) == 0:
            return True  # hockey: empty score lists
        if isinstance(v, dict) and all(val == 0 for val in v.values()):
            return True  # volleyball: all-zero count dicts
    return False


# ── Orchestration ────────────────────────────────────────────────────


async def fetch_all_standings(
    page: Page, matches: list[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    """Fetch standings for each unique league found in matches."""
    logger.info('Fetching league standings for rankings...')
    league_standings: dict[str, dict[str, int]] = {}
    seen_leagues: set[str] = set()

    for match in matches:
        league_url = match.get('leagueUrl', '')
        league_key = league_url or f'{match.get("country", "")}_{match.get("league", "")}'

        if league_key and league_key not in seen_leagues:
            seen_leagues.add(league_key)

            if league_url:
                full_url = (
                    f'{BASE_URL}{league_url}' if not league_url.startswith('http') else league_url
                )
                logger.debug('Fetching standings for: %s', match.get('league', league_url))
                standings = await scrape_league_standings(page, full_url)

                if standings:
                    league_standings[league_key] = standings

            await page.wait_for_timeout(500)

    return league_standings


def apply_rankings(
    matches: list[dict[str, Any]], league_standings: dict[str, dict[str, int]]
) -> None:
    """Assign ranks to matches from league standings (mutates in place)."""
    for match in matches:
        league_url = match.get('leagueUrl', '')
        league_key = league_url or f'{match.get("country", "")}_{match.get("league", "")}'
        standings = league_standings.get(league_key, {})
        match['rankA'] = find_team_rank(match['teamA'], standings)
        match['rankB'] = find_team_rank(match['teamB'], standings)


async def run_scraper(
    sport_name: str,
    sport_url: str,
    selectors: dict[str, dict[str, str]],
    days_offset: int,
    scrape_match_stats: Callable,
    default_stats: dict[str, Any],
    validation_checks: dict[str, str],
    output_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Full scraper pipeline: browser → validate → extract → standings → rankings → stats.

    Args:
        sport_name: Display name (e.g. "volleyball", "hockey")
        sport_url: Full URL to the sport page
        selectors: From build_selectors()
        days_offset: Days from today to scrape
        scrape_match_stats: async (page, url, team_a, team_b) → stats dict
        default_stats: Fallback stats for matches without URLs
        validation_checks: {label: selector} for startup checks
    """
    logger.info('Starting FlashScore %s scraper...', sport_name)
    target_date = datetime.now() + timedelta(days=days_offset)
    logger.info('Target date: %s (J%+d)', target_date.strftime('%d/%m/%Y'), days_offset)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=config.scraper.headless)
        context = await browser.new_context(
            locale='fr-FR',
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                ' (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
        )
        page = await context.new_page()

        try:
            # Step 0: Validate selectors (non-blocking)
            await validate_page_selectors(page, sport_url, validation_checks)

            # Step 1: Get matches for target date
            logger.info(
                'Fetching %s matches for %s...',
                sport_name,
                target_date.strftime('%d/%m/%Y'),
            )
            matches = await extract_matches_for_date(page, sport_url, selectors, days_offset)
            logger.info('Found %d %s matches', len(matches), sport_name)

            # Step 2: Fetch standings for each unique league
            league_standings = await fetch_all_standings(page, matches)

            # Step 3: Apply rankings to matches
            apply_rankings(matches, league_standings)

            # Step 4: For each match, get sport-specific stats
            results: list[dict[str, Any]] = []
            max_matches = config.scraper.max_matches or len(matches)
            matches_to_process = matches[:max_matches] if max_matches > 0 else matches

            # Setup for partial saves
            if output_dir is None:
                _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                output_dir = os.path.join(_project_root, 'output')

            def save_partial(data: list[dict[str, Any]]) -> None:
                """Save intermediate results to a partial JSON file."""
                os.makedirs(output_dir, exist_ok=True)
                partial_file = os.path.join(
                    output_dir,
                    f'{sport_name}_partial_{target_date.strftime("%Y-%m-%d")}.json',
                )
                with open(partial_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info('Saved %d partial results to %s', len(data), partial_file)

            start_time = time.monotonic()
            consecutive_empty = 0
            failed_indices: list[int] = []  # indices of matches that got empty stats

            for i, match in enumerate(matches_to_process):
                # Global timeout: stop after GLOBAL_TIMEOUT_S to prevent 12h+ runs
                elapsed = time.monotonic() - start_time
                if elapsed >= GLOBAL_TIMEOUT_S:
                    logger.warning(
                        'Global timeout reached (%.0fs / %ds) after %d/%d matches '
                        '— returning partial results',
                        elapsed,
                        GLOBAL_TIMEOUT_S,
                        i,
                        len(matches_to_process),
                    )
                    break

                n = f'{i + 1}/{len(matches_to_process)}'
                logger.info('Processing match %s: %s vs %s', n, match['teamA'], match['teamB'])

                match_data = {k: v for k, v in match.items() if k != 'leagueUrl'}

                if match['matchUrl']:
                    try:
                        stats = await asyncio.wait_for(
                            scrape_match_stats(
                                page, match['matchUrl'], match['teamA'], match['teamB']
                            ),
                            timeout=PER_MATCH_TIMEOUT_S,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            'Timeout (%ds) scraping match %s: %s vs %s (%s) — using default stats',
                            PER_MATCH_TIMEOUT_S,
                            n,
                            match['teamA'],
                            match['teamB'],
                            match['matchUrl'],
                        )
                        stats = default_stats
                    # Check for empty/zero stats (possible rate-limit)
                    if _stats_are_empty(stats):
                        logger.warning(
                            'Empty stats for match %s: %s vs %s (%s)',
                            n,
                            match['teamA'],
                            match['teamB'],
                            match['matchUrl'],
                        )
                        consecutive_empty += 1
                        failed_indices.append(len(results))
                        if consecutive_empty >= CONSECUTIVE_EMPTY_LIMIT:
                            logger.warning(
                                'Rate-limit detected: %d consecutive empty results '
                                '— cooling down %ds',
                                consecutive_empty,
                                RATE_LIMIT_COOLDOWN_S,
                            )
                            await page.wait_for_timeout(RATE_LIMIT_COOLDOWN_S * 1000)
                            consecutive_empty = 0
                    else:
                        consecutive_empty = 0
                    results.append({**match_data, **stats})
                else:
                    logger.warning(
                        'No matchUrl for match %s: %s vs %s — using default stats',
                        n,
                        match['teamA'],
                        match['teamB'],
                    )
                    results.append({**match_data, **default_stats})

                # Save partial results periodically
                if len(results) % PARTIAL_SAVE_INTERVAL == 0:
                    save_partial(results)

                await page.wait_for_timeout(config.scraper.request_delay)

                # Batch cooldown: pause after every BATCH_SIZE matches
                if (i + 1) % BATCH_SIZE == 0 and i + 1 < len(matches_to_process):
                    logger.info(
                        'Batch cooldown: pausing %ds after %d matches...',
                        BATCH_COOLDOWN_S,
                        i + 1,
                    )
                    await page.wait_for_timeout(BATCH_COOLDOWN_S * 1000)

            # Retry pass: re-scrape matches that got empty stats (likely rate-limited)
            if failed_indices:
                elapsed = time.monotonic() - start_time
                remaining_s = GLOBAL_TIMEOUT_S - elapsed
                if remaining_s > 300:  # only retry if >5 min left
                    logger.info(
                        'Retry pass: %d matches with empty stats, cooling down %ds first...',
                        len(failed_indices),
                        RATE_LIMIT_COOLDOWN_S,
                    )
                    await page.wait_for_timeout(RATE_LIMIT_COOLDOWN_S * 1000)

                    retried = 0
                    fixed = 0
                    for idx in failed_indices:
                        elapsed = time.monotonic() - start_time
                        if elapsed >= GLOBAL_TIMEOUT_S:
                            logger.warning('Global timeout during retry pass')
                            break

                        r = results[idx]
                        url = r.get('matchUrl', '')
                        if not url:
                            continue

                        retried += 1
                        n = f'{retried}/{len(failed_indices)}'
                        logger.info(
                            'Retrying match %s: %s vs %s',
                            n,
                            r.get('teamA', ''),
                            r.get('teamB', ''),
                        )

                        try:
                            stats = await asyncio.wait_for(
                                scrape_match_stats(
                                    page,
                                    url,
                                    r.get('teamA', ''),
                                    r.get('teamB', ''),
                                ),
                                timeout=PER_MATCH_TIMEOUT_S,
                            )
                        except asyncio.TimeoutError:
                            stats = default_stats

                        if not _stats_are_empty(stats):
                            results[idx] = {**r, **stats}
                            fixed += 1

                        await page.wait_for_timeout(config.scraper.request_delay)

                        if retried % BATCH_SIZE == 0:
                            logger.info(
                                'Retry batch cooldown: pausing %ds...',
                                BATCH_COOLDOWN_S,
                            )
                            await page.wait_for_timeout(BATCH_COOLDOWN_S * 1000)

                    logger.info(
                        'Retry pass complete: fixed %d/%d matches',
                        fixed,
                        retried,
                    )
                else:
                    logger.warning(
                        'Skipping retry pass: only %.0fs remaining (need >300s)',
                        remaining_s,
                    )

            # Save final results
            if results:
                save_partial(results)

            return results
        finally:
            await browser.close()
