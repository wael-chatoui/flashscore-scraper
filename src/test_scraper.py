#!/usr/bin/env python3
"""
Test script to verify scraper works without Google Sheets
"""

import asyncio
import json
import sys

from scraper import scrape_flashscore


async def test() -> None:
    """Run scraper test"""
    print('Testing FlashScore scraper...\n')

    try:
        matches = await scrape_flashscore()

        print('\n' + '=' * 60)
        print(f'Found {len(matches)} matches')
        print('=' * 60)

        # Print first 5 matches
        for i, m in enumerate(matches[:5]):
            print(f'\nMatch {i + 1}:')
            print(f"  {m['teamA']} (Rank: {m['rankA'] or 'N/A'}) vs {m['teamB']} (Rank: {m['rankB'] or 'N/A'})")
            print(f"  {m['country']} - {m['league']}")
            print(f"  {m['date']} {m['time']}")
            print(f"  Team A stats: 3sets={m['teamAStats']['count3']}, 4sets={m['teamAStats']['count4']}, 5sets={m['teamAStats']['count5']}")
            print(f"  Team B stats: 3sets={m['teamBStats']['count3']}, 4sets={m['teamBStats']['count4']}, 5sets={m['teamBStats']['count5']}")
            print(f"  H2H stats: 3sets={m['h2hStats']['count3']}, 4sets={m['h2hStats']['count4']}, 5sets={m['h2hStats']['count5']}")

        # Save full results
        with open('test-results.json', 'w', encoding='utf-8') as f:
            json.dump(matches, f, indent=2, ensure_ascii=False)
        print('\nFull results saved to test-results.json')

    except Exception as err:
        print(f'Test failed: {err}')
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(test())
