# Explore Skill

Perform a thorough exploration of the entire project — its idea, architecture, codebase, and current state.

## Steps

1. **Read project documentation** — Read `CLAUDE.md`, `README.md`, `pyproject.toml`, `.env.example`, `Dockerfile`, and `docker-compose.yml` to understand the project purpose, dependencies, and configuration.

2. **Map the project structure** — List the full directory tree and identify all packages, modules, scripts, config files, and output directories.

3. **Understand the core flow** — Read the main entry points (`__main__.py`, `main.py`, `batch_scrape.py`) to understand how the application is invoked and what it does end-to-end.

4. **Analyze the scraping layer** — Read all scraper modules (e.g. `scraper.py`, `base_scraper.py`, any sport-specific scrapers). Understand selectors, data models, navigation logic, and how match data is extracted.

5. **Analyze the data layer** — Read `sheets.py`, `sort_sheet.py`, `read_sheet.py`, and `config.py` to understand how data flows from scraping to Google Sheets.

6. **Review infrastructure** — Examine scripts (`scripts/`), CI/CD workflows (`.github/`), Docker setup, and scheduling configuration.

7. **Check current state** — Run `git log --oneline -15` and `git status` to understand recent activity and any uncommitted work.

8. **Produce a summary report** — Present a clear, structured summary to the user covering:
   - **Project idea**: What the tool does and why it exists.
   - **Architecture**: High-level data flow from scraping to output.
   - **Key modules**: Purpose of each file/module, one line each.
   - **Tech stack**: Languages, frameworks, and external services used.
   - **Configuration**: Environment variables, credentials, and presets.
   - **Deployment**: How the project is built, scheduled, and deployed.
   - **Current state**: Recent commits, open issues, or areas of active development.
   - **Observations**: Anything notable — potential improvements, inconsistencies, or strengths.
