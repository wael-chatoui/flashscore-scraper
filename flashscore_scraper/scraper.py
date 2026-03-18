"""
FlashScore Volleyball Scraper

Scrapes volleyball matches and H2H statistics from FlashScore.
Sport-specific logic only — shared infrastructure lives in base_scraper.
"""

import asyncio
import logging
from typing import TypedDict

from playwright.async_api import ElementHandle, Page

from .base_scraper import (
    BASE_URL,
    Match,
    build_selectors,
    click_show_more_buttons,
    goto_with_retry,
    run_scraper,
)

logger = logging.getLogger(__name__)

VOLLEYBALL_URL = f'{BASE_URL}/volleyball/'

SELECTORS = build_selectors(
    league_link='a.headerLeague__title, a[href*="/volleyball/"]',
    navigation={
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
        'prev_day': (
            'button.calendar__navigation--yesterday,'
            ' button[data-testid="calendar-prev"],'
            ' [class*="calendar__navigation--prev"],'
            ' .calendar__nav--prev'
        ),
        'prev_day_alt': (
            '[aria-label*="précédent"], [aria-label*="prev"],'
            ' button.arrow--prev, .calendar__direction--prev'
        ),
    },
)


# ── TypedDicts ────────────────────────────────────────────────────────


class SetStats(TypedDict):
    count3: int
    count4: int
    count5: int


class MatchStats(TypedDict):
    teamAStats: SetStats
    teamBStats: SetStats
    h2hStats: SetStats


class MatchWithStats(Match, MatchStats):
    pass


# ── Volleyball-specific H2H logic ───────────────────────────────────


async def count_sets_in_section(section: ElementHandle) -> SetStats:
    """Count sets distribution from a H2H section.

    3-0→3 sets, 3-1→4 sets, 3-2→5 sets.
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

            sets_a, sets_b = None, None

            if '-' in result_text:
                parts = result_text.split('-')
                if len(parts) != 2:
                    continue
                try:
                    sets_a = int(parts[0].strip())
                    sets_b = int(parts[1].strip())
                except ValueError:
                    continue
            elif len(result_text) == 2:
                try:
                    sets_a = int(result_text[0])
                    sets_b = int(result_text[1])
                except ValueError:
                    continue
            else:
                continue

            total_sets = sets_a + sets_b

            if total_sets == 3:
                count3 += 1
            elif total_sets == 4:
                count4 += 1
            elif total_sets == 5:
                count5 += 1
        except Exception:
            pass

    return {'count3': count3, 'count4': count4, 'count5': count5}


async def scrape_h2h_stats(
    page: Page, h2h_url: str, team_a: str = '', team_b: str = ''
) -> MatchStats:
    """Scrape H2H stats for a volleyball match.

    Processes 3 sections: team A, team B, and confrontation directe.
    """
    default_stats: SetStats = {'count3': 0, 'count4': 0, 'count5': 0}

    try:
        await goto_with_retry(page, h2h_url)
        await page.wait_for_timeout(3000)

        await click_show_more_buttons(page)
        await page.wait_for_timeout(500)

        sections = await page.query_selector_all(SELECTORS['h2h']['section'])

        if not sections:
            logger.warning(
                'H2H page has 0 sections for %s vs %s (%s)',
                team_a,
                team_b,
                h2h_url,
            )
            return {
                'teamAStats': default_stats,
                'teamBStats': default_stats,
                'h2hStats': default_stats,
            }

        team_a_stats = default_stats.copy()
        team_b_stats = default_stats.copy()
        h2h_stats = default_stats.copy()

        team_a_lower = team_a.lower()
        team_b_lower = team_b.lower()

        matched_a = False
        matched_b = False
        matched_h2h = False

        for section in sections:
            title_el = await section.query_selector(SELECTORS['h2h']['section_title'])
            title = ''
            if title_el:
                title_text = await title_el.text_content()
                title = (title_text or '').lower()

            stats = await count_sets_in_section(section)

            if 'confrontation' in title:
                h2h_stats = stats
                matched_h2h = True
            elif team_a_lower and team_a_lower in title:
                team_a_stats = stats
                matched_a = True
            elif team_b_lower and team_b_lower in title:
                team_b_stats = stats
                matched_b = True

        # Fallback: assign unmatched sections by index
        if not (matched_a and matched_b and matched_h2h):
            unmatched_sections = []
            for section in sections:
                title_el = await section.query_selector(SELECTORS['h2h']['section_title'])
                title = ''
                if title_el:
                    title_text = await title_el.text_content()
                    title = (title_text or '').lower()

                if matched_h2h and 'confrontation' in title:
                    continue
                if matched_a and team_a_lower and team_a_lower in title:
                    continue
                if matched_b and team_b_lower and team_b_lower in title:
                    continue

                unmatched_sections.append(section)

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

        if not matched_a or not matched_b:
            logger.warning(
                'Incomplete H2H matching for %s vs %s: matched_a=%s, matched_b=%s, '
                'matched_h2h=%s (sections=%d)',
                team_a,
                team_b,
                matched_a,
                matched_b,
                matched_h2h,
                len(sections),
            )

        return {'teamAStats': team_a_stats, 'teamBStats': team_b_stats, 'h2hStats': h2h_stats}
    except Exception as e:
        logger.error('Error scraping H2H for %s: %s', h2h_url, e)
        return {'teamAStats': default_stats, 'teamBStats': default_stats, 'h2hStats': default_stats}


# ── Entry point ──────────────────────────────────────────────────────


async def scrape_flashscore(days_offset: int = 0) -> list[MatchWithStats]:
    """Main volleyball scraping function.

    Args:
        days_offset: Number of days from today to scrape.
    """
    default_stats = {
        'teamAStats': {'count3': 0, 'count4': 0, 'count5': 0},
        'teamBStats': {'count3': 0, 'count4': 0, 'count5': 0},
        'h2hStats': {'count3': 0, 'count4': 0, 'count5': 0},
    }
    validation_checks = {
        'match rows': SELECTORS['matches']['all_items'],
        'next-day nav': SELECTORS['navigation']['next_day'],
    }

    return await run_scraper(
        sport_name='volleyball',
        sport_url=VOLLEYBALL_URL,
        selectors=SELECTORS,
        days_offset=days_offset,
        scrape_match_stats=scrape_h2h_stats,
        default_stats=default_stats,
        validation_checks=validation_checks,
    )


if __name__ == '__main__':
    from .config import setup_logging

    setup_logging()
    results = asyncio.run(scrape_flashscore())
    logger.info('Scraped %d matches', len(results))
