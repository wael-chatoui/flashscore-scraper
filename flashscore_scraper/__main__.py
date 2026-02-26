"""Allow running as: python -m flashscore_scraper"""

import asyncio

from .config import setup_logging
from .main import main

if __name__ == '__main__':
    setup_logging()
    asyncio.run(main())
