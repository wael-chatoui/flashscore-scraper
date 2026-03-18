import asyncio
from playwright.async_api import async_playwright


async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(locale="fr-FR")

        # Test URLs that gave all-zero stats
        urls = [
            ("JT Thunders vs Nagoya", "https://www.flashscore.fr/match/volleyball/jt-thunders-ny1bf4Dj/nagoya-jTKINSpR/tete-a-tete/global/"),
            ("Odolena Voda vs Liberec", "https://www.flashscore.fr/match/volleyball/liberec-AamoCaeE/odolena-voda-8WrL1m7J/tete-a-tete/global/"),
            ("Dinamo Bucuresti vs Craiova", "https://www.flashscore.fr/match/volleyball/craiova-OfkhJ7gb/dinamo-bucuresti-O6ac1n9H/tete-a-tete/global/"),
        ]

        for name, url in urls:
            print(f"\n{'='*50}")
            print(f"Testing: {name}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)

            # Click show more buttons
            buttons = await page.query_selector_all("button.wclButtonLink--h2h")
            for btn in buttons:
                try:
                    if await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(300)
                except Exception:
                    pass

            sections = await page.query_selector_all(".h2h__section")
            print(f"Sections: {len(sections)}")

            for i, section in enumerate(sections):
                # Get title using the new selector
                title_el = await section.query_selector("[data-testid='wcl-scores-overline-02']")
                if not title_el:
                    title_el = await section.query_selector(".h2h__title, .section__title")
                title = ""
                if title_el:
                    title = (await title_el.text_content()).strip()

                rows = await section.query_selector_all(".h2h__row")
                results = []
                for row in rows:
                    rel = await row.query_selector(".h2h__result")
                    if rel:
                        t = await rel.text_content()
                        results.append(t.strip())
                print(f"  Section {i} ({title}): {len(rows)} rows, results={results}")

            # Check page for error/block indicators
            body = await page.evaluate("document.body.innerText.substring(0, 200)")
            if "Erreur" in body or "error" in body.lower() or "blocked" in body.lower():
                print(f"  PAGE ERROR: {body[:200]}")

        await browser.close()


asyncio.run(test())
