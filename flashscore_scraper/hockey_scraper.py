"""
FlashScore Hockey Scraper

Scrapes hockey matches and per-team last-15 goal statistics from FlashScore.
Goal categorization: <=5 goals, =6 goals, >=7 goals.
Sport-specific logic only — shared infrastructure lives in base_scraper.
"""

import asyncio
from typing import TypedDict

from playwright.async_api import ElementHandle, Page

from .base_scraper import (
    BASE_URL,
    Match,
    build_selectors,
    click_show_more_buttons,
    run_scraper,
)

HOCKEY_URL = f'{BASE_URL}/hockey/'

HOCKEY_SELECTORS = build_selectors(
    league_link='a.headerLeague__title, a[href*="/hockey/"]',
    navigation={
        'next_day': (
            'button[data-day-picker-arrow="next"],'
            ' button[aria-label="Jour suivant"],'
            ' button.calendar__navigation--tomorrow'
        ),
        'next_day_alt': (
            '[aria-label*="suivant"], [aria-label*="next"]'
        ),
        'prev_day': (
            'button[data-day-picker-arrow="prev"],'
            ' button[aria-label="Jour précédent"],'
            ' button.calendar__navigation--yesterday'
        ),
        'prev_day_alt': (
            '[aria-label*="précédent"], [aria-label*="prev"]'
        ),
    },
)


# ── TypedDicts ────────────────────────────────────────────────────────
# count3 = <=5 goals, count4 = =6 goals, count5 = >=7 goals


class GoalStats(TypedDict):
    count3: int  # <=5 goals
    count4: int  # =6 goals
    count5: int  # >=7 goals


class HockeyMatch(Match):
    pass


class HockeyMatchStats(TypedDict):
    teamAStats: GoalStats
    teamBStats: GoalStats


class HockeyMatchWithStats(HockeyMatch, HockeyMatchStats):
    pass


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


async def count_goals_in_section(
    section: ElementHandle, max_matches: int = 15
) -> GoalStats:
    """Count goal distribution from an H2H section.

    Categorizes: <=5 goals (count3), =6 goals (count4), >=7 goals (count5).
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


# ── Hockey-specific H2H logic ───────────────────────────────────────


async def scrape_hockey_h2h_stats(
    page: Page, h2h_url: str, team_a: str = '', team_b: str = ''
) -> HockeyMatchStats:
    """Scrape per-team last-15 goal stats for a hockey match.

    Skips the "confrontation directe" section — only processes per-team sections.
    """
    default_stats: GoalStats = {'count3': 0, 'count4': 0, 'count5': 0}

    try:
        await page.goto(h2h_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        await click_show_more_buttons(page)
        await page.wait_for_timeout(500)

        sections = await page.query_selector_all(HOCKEY_SELECTORS['h2h']['section'])

        team_a_stats = default_stats.copy()
        team_b_stats = default_stats.copy()

        team_a_lower = team_a.lower()
        team_b_lower = team_b.lower()

        matched_a = False
        matched_b = False
        matched_h2h = False

        # Collect section titles
        section_titles: list[str] = []
        for section in sections:
            title_el = await section.query_selector(
                HOCKEY_SELECTORS['h2h']['section_title']
            )
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

            stats = await count_goals_in_section(section, max_matches=15)

            if team_a_lower and team_a_lower in title:
                team_a_stats = stats
                matched_a = True
            elif team_b_lower and team_b_lower in title:
                team_b_stats = stats
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
            if (
                len(sections) == 3
                and not matched_h2h
                and all(t == '' for t in section_titles)
            ):
                unmatched_sections = unmatched_sections[1:]

            for _idx, section in unmatched_sections:
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


# ── Entry point ──────────────────────────────────────────────────────


async def scrape_hockey(days_offset: int = 0) -> list[HockeyMatchWithStats]:
    """Main hockey scraping function.

    Args:
        days_offset: Number of days from today to scrape.
    """
    default_stats = {
        'teamAStats': {'count3': 0, 'count4': 0, 'count5': 0},
        'teamBStats': {'count3': 0, 'count4': 0, 'count5': 0},
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
    results = asyncio.run(scrape_hockey())
    print(f'\nScraped {len(results)} hockey matches')
