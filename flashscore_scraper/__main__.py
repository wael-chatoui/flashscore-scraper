"""Allow running as: python -m flashscore_scraper"""

import asyncio

from .main import main

if __name__ == '__main__':
    asyncio.run(main())
