# Changelog

## [2026-01-19] - Rankings Feature Enhancement

### Added
- **Team Rankings from League Standings**: The scraper now fetches league standings pages to populate team rankings (rankA, rankB columns)
- **Normalized Team Name Matching**: Added dual-key storage for standings - stores both original names (e.g., "san diego mojo f") and normalized names (e.g., "san diego mojo") for better matching
- **URL Alternatives for Multi-language Support**: Added automatic URL pattern alternatives to handle French/English variations:
  - `-femmes` ↔ `-women`
  - `-hommes` ↔ `-men`
  - `liga-femmes` ↔ `liga-women`

### Fixed
- **League URL Extraction**: Fixed the JavaScript extraction logic to properly track `currentLeagueUrl` across league headers. Previously, league URLs were not being captured from the main page
- **Country Name Extraction**: Now correctly extracts country from `.headerLeague__category-text` element instead of flag title
- **Standings Page Loading**: Changed from `networkidle` to `domcontentloaded` with 5-second wait for more reliable page loading

### Changed
- **Column Mapping** (from previous session): Corrected the Google Sheets column preset to match actual sheet structure:
  - Date: Column A
  - Match info (time, country, league, teams, ranks): Columns I-O
  - Team A stats: Columns T-V
  - Team B stats: Columns AE-AG
  - H2H stats: Columns AJ-AL

### Technical Details

#### Files Modified
- `src/scraper.py`:
  - Updated `extract_today_matches()` to track `currentLeagueUrl` variable
  - Updated `scrape_league_standings()` with better URL alternatives and team name normalization
  - Added debug logging for standings URL attempts and errors

#### Standings Scraping Flow
1. Scraper fetches main volleyball page
2. Extracts league URLs from `.headerLeague__title` links
3. For each unique league, fetches `/classement/` page
4. Extracts team rankings from `.ui-table__row` elements
5. Stores rankings with both original and normalized team names
6. Matches team names using partial matching as fallback

#### CSS Selectors Used
- League header: `.headerLeague__title-text`, `.headerLeague__category-text`
- League link: `a.headerLeague__title`, `a[href*="/volleyball/"]`
- Standings table: `.ui-table__row`
- Rank cell: `.tableCellRank`
- Team name cell: `.tableCellParticipant__name`
