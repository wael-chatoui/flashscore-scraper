"""
FlashScore Hockey Scraper

Scrapes hockey matches and per-team raw last-15 total goals from FlashScore.
Returns a list of up to 15 total-goal values per team (e.g. [5, 7, 3, 6, ...]).
Sport-specific logic only — shared infrastructure lives in base_scraper.
"""

import asyncio
import logging
from typing import TypedDict

from playwright.async_api import Page

from .base_scraper import (
    BASE_URL,
    Match,
    build_selectors,
    click_show_more_buttons,
    goto_with_retry,
    run_scraper,
)

logger = logging.getLogger(__name__)

HOCKEY_URL = f'{BASE_URL}/hockey/'

HOCKEY_SELECTORS = build_selectors(
    league_link='a.headerLeague__title, a[href*="/hockey/"]',
    navigation={
        'next_day': (
            'button[data-day-picker-arrow="next"],'
            ' button[aria-label="Jour suivant"],'
            ' button.calendar__navigation--tomorrow'
        ),
        'next_day_alt': ('[aria-label*="suivant"], [aria-label*="next"]'),
        'prev_day': (
            'button[data-day-picker-arrow="prev"],'
            ' button[aria-label="Jour précédent"],'
            ' button.calendar__navigation--yesterday'
        ),
        'prev_day_alt': ('[aria-label*="précédent"], [aria-label*="prev"]'),
    },
)


# ── TypedDicts ────────────────────────────────────────────────────────


class HockeyMatch(Match):
    pass


class HockeyMatchStats(TypedDict):
    teamAScores: list[int]  # Raw total goals per match (up to 15 values)
    teamBScores: list[int]


class HockeyMatchWithStats(HockeyMatch, HockeyMatchStats):
    pass


# ── Helpers ──────────────────────────────────────────────────────────


_FEMININE_KEYWORDS = (
    'femme', 'women', 'féminin', 'feminine', 'dames', 'ladies',
    '(f)', '(w)', 'women\'s',
)


def detect_sexe(league: str) -> str:
    """Return 'F' for feminine leagues, 'H' otherwise."""
    lower = league.lower()
    for kw in _FEMININE_KEYWORDS:
        if kw in lower:
            return 'F'
    return 'H'


# ── Hockey-specific parsing ──────────────────────────────────────────


def parse_hockey_score(text: str) -> tuple[int | None, int | None]:
    """Parse a hockey score string into (goals_a, goals_b).

    Handles formats: "4:2", "4-2", "4 - 2", "4 : 2", "42" (concatenated).
    Strips OT/SO/AP/TB suffixes (e.g. "4:2 AP", "3-2 SO").
    Returns (None, None) if parsing fails.
    """
    if not text:
        return None, None

    text = text.strip()

    for suffix in ('AP', 'TB', 'SO', 'OT', 'P', 'ap', 'tb', 'so', 'ot', 'p'):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()

    for sep in (':', '-'):
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts) == 2:
                try:
                    return int(parts[0].strip()), int(parts[1].strip())
                except ValueError:
                    continue

    if len(text) == 2 and text.isdigit():
        return int(text[0]), int(text[1])

    return None, None


async def collect_scores_in_section(section, max_matches: int = 15) -> list[int]:
    """Collect raw total-goal values from an H2H section.

    Returns a list of total goals per match (up to max_matches, default 15).
    Example: [5, 7, 3, 6, 4, ...].
    """
    rows = await section.query_selector_all(HOCKEY_SELECTORS['h2h']['row'])
    scores: list[int] = []

    for row in rows:
        if len(scores) >= max_matches:
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

            scores.append(goals_a + goals_b)
        except Exception:
            pass

    return scores


# ── Hockey-specific H2H logic ───────────────────────────────────────


async def scrape_hockey_h2h_stats(
    page: Page, h2h_url: str, team_a: str = '', team_b: str = ''
) -> HockeyMatchStats:
    """Scrape per-team last-15 raw total goals for a hockey match.

    Skips the "confrontation directe" section — only processes per-team sections.
    Returns lists of up to 15 total-goal values per team.
    """
    default_scores: list[int] = []

    try:
        await goto_with_retry(page, h2h_url)
        await page.wait_for_timeout(3000)

        await click_show_more_buttons(page)
        await page.wait_for_timeout(500)

        sections = await page.query_selector_all(HOCKEY_SELECTORS['h2h']['section'])

        # Rate-limit mitigation: if no sections found, wait and retry once
        if not sections:
            logger.warning(
                'H2H page has 0 sections for %s vs %s — retrying in 15s (%s)',
                team_a, team_b, h2h_url,
            )
            await page.wait_for_timeout(15000)
            await page.reload(wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)
            await click_show_more_buttons(page)
            await page.wait_for_timeout(500)
            sections = await page.query_selector_all(HOCKEY_SELECTORS['h2h']['section'])
            if not sections:
                logger.warning(
                    'H2H page still has 0 sections after retry for %s vs %s',
                    team_a, team_b,
                )
                return {'teamAScores': default_scores, 'teamBScores': default_scores}

        team_a_scores: list[int] = []
        team_b_scores: list[int] = []

        team_a_lower = team_a.lower()
        team_b_lower = team_b.lower()

        matched_a = False
        matched_b = False
        matched_h2h = False

        # Collect section titles
        section_titles: list[str] = []
        for section in sections:
            title_el = await section.query_selector(HOCKEY_SELECTORS['h2h']['section_title'])
            title = ''
            if title_el:
                title_text = await title_el.text_content()
                title = (title_text or '').lower()
            section_titles.append(title)

        # First pass: match by title content
        for section, title in zip(sections, section_titles, strict=False):
            if 'confrontation' in title:
                matched_h2h = True
                continue  # Skip H2H section for hockey

            scores = await collect_scores_in_section(section, max_matches=15)

            if team_a_lower and team_a_lower in title:
                team_a_scores = scores
                matched_a = True
            elif team_b_lower and team_b_lower in title:
                team_b_scores = scores
                matched_b = True

        # Fallback: assign by standard order
        if not (matched_a and matched_b):
            unmatched_sections = []
            for i, (section, title) in enumerate(zip(sections, section_titles, strict=False)):
                if matched_h2h and 'confrontation' in title:
                    continue
                if matched_a and team_a_lower and team_a_lower in title:
                    continue
                if matched_b and team_b_lower and team_b_lower in title:
                    continue
                unmatched_sections.append((i, section))

            # When all titles are empty and we have 3 sections,
            # skip the first (confrontation directe), use 2nd and 3rd
            if len(sections) == 3 and not matched_h2h and all(t == '' for t in section_titles):
                unmatched_sections = unmatched_sections[1:]

            for _idx, section in unmatched_sections:
                scores = await collect_scores_in_section(section, max_matches=15)
                if not matched_a:
                    team_a_scores = scores
                    matched_a = True
                elif not matched_b:
                    team_b_scores = scores
                    matched_b = True

        if not matched_a or not matched_b:
            logger.warning(
                'Incomplete H2H matching for %s vs %s: matched_a=%s, matched_b=%s '
                '(sections=%d, titles=%s)',
                team_a, team_b, matched_a, matched_b,
                len(sections), section_titles,
            )

        return {'teamAScores': team_a_scores, 'teamBScores': team_b_scores}
    except Exception as e:
        logger.error('Error scraping hockey stats for %s: %s', h2h_url, e)
        return {'teamAScores': default_scores, 'teamBScores': default_scores}


# ── Entry point ──────────────────────────────────────────────────────


async def scrape_hockey(days_offset: int = 0) -> list[HockeyMatchWithStats]:
    """Main hockey scraping function.

    Args:
        days_offset: Number of days from today to scrape.
    """
    default_stats = {
        'teamAScores': [],
        'teamBScores': [],
    }
    validation_checks = {
        'match rows': HOCKEY_SELECTORS['matches']['all_items'],
        'prev-day nav': HOCKEY_SELECTORS['navigation']['prev_day'],
    }

    return await run_scraper(
        sport_name='hockey',
        sport_url=HOCKEY_URL,
        selectors=HOCKEY_SELECTORS,
        days_offset=days_offset,
        scrape_match_stats=scrape_hockey_h2h_stats,
        default_stats=default_stats,
        validation_checks=validation_checks,
    )


if __name__ == '__main__':
    from .config import setup_logging

    setup_logging()
    results = asyncio.run(scrape_hockey())
    logger.info('Scraped %d hockey matches', len(results))
