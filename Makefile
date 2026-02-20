.PHONY: install lint format test run pre-commit ci

install:
	pip install -e ".[dev]"
	playwright install chromium

lint:
	ruff check flashscore_scraper/

format:
	ruff format flashscore_scraper/
	ruff check --fix flashscore_scraper/

test:
	pytest tests/ -v

run:
	flashscore-scraper

pre-commit:
	pre-commit install

ci: lint test
