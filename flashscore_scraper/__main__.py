"""Allow running as: python -m flashscore_scraper"""
from .main import main

import asyncio

if __name__ == "__main__":
    asyncio.run(main())
