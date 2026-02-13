#!/usr/bin/env python3
"""Debug script to verify H2H stats counting matches the scraped JSON"""

import asyncio
import json
from playwright.async_api import async_playwright

URLS = [
    ("Tourcoing", "Nice", "https://www.flashscore.fr/match/volleyball/nice-O4MYx0BC/tourcoing-lhL6wFCl/tete-a-tete/global/"),
    ("Jastrzebski", "Belchatow", "https://www.flashscore.fr/match/volleyball/belchatow-SMCDQxuK/jastrzebski-lWD9RIPD/tete-a-tete/global/"),
]

def count_sets(results):
    """Count 3/4/5 set matches from result strings"""
    c3, c4, c5 = 0, 0, 0
    for r in results:
        r = r.strip()
        if '-' in r:
            parts = r.split('-')
            a, b = int(parts[0].strip()), int(parts[1].strip())
        elif len(r) == 2:
            a, b = int(r[0]), int(r[1])
        else:
            continue
        total = a + b
        if total == 3: c3 += 1
        elif total == 4: c4 += 1
        elif total == 5: c5 += 1
    return {'count3': c3, 'count4': c4, 'count5': c5}


async def main():
    # Load the scraped JSON for comparison
    try:
        with open('./output/matches_2026-02-13.json') as f:
            scraped = json.load(f)
        scraped_map = {}
        for m in scraped:
            key = f"{m['teamA']} vs {m['teamB']}"
            scraped_map[key] = m
    except Exception:
        scraped_map = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale='fr-FR')
        page = await context.new_page()

        for team_a, team_b, url in URLS:
            label = f"{team_a} vs {team_b}"
            print(f"\n{'='*60}")
            print(f"Match: {label}")
            print(f"{'='*60}")

            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(5000)

            # Click show more buttons
            while True:
                buttons = await page.query_selector_all('button.wclButtonLink--h2h')
                clicked = False
                for btn in buttons:
                    if await btn.is_visible():
                        await btn.click()
                        clicked = True
                        await page.wait_for_timeout(300)
                if not clicked:
                    break

            sections = await page.query_selector_all('.h2h__section')

            for i, section in enumerate(sections):
                # Get the header text from the wcl-headerSection div
                header_el = await section.query_selector('div[class*="headerSection"]')
                header = ''
                if header_el:
                    header = (await header_el.text_content() or '').strip()

                # Get all results
                rows = await section.query_selector_all('.h2h__row')
                results = []
                for row in rows:
                    result_el = await row.query_selector('.h2h__result')
                    if result_el:
                        txt = await result_el.text_content()
                        if txt:
                            results.append(txt.strip())

                stats = count_sets(results)
                print(f"\n  Section {i}: '{header}'")
                print(f"    Rows: {len(rows)}, Results parsed: {len(results)}")
                print(f"    Stats: {stats}")

            # Compare with scraped JSON
            if label in scraped_map:
                m = scraped_map[label]
                print(f"\n  Scraped JSON values:")
                print(f"    teamAStats ({team_a}): {m['teamAStats']}")
                print(f"    teamBStats ({team_b}): {m['teamBStats']}")
                print(f"    h2hStats: {m['h2hStats']}")

        await browser.close()

asyncio.run(main())
