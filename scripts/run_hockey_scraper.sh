#!/bin/bash
#
# FlashScore Hockey Scraper - Daily Runner Script
#
# Usage: ./run_hockey_scraper.sh
#
# This script is designed to be run by cron or systemd timer.
# It activates the virtual environment and runs the hockey scraper.
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Log file
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/hockey_scraper_$(date +%Y-%m-%d).log"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting FlashScore Hockey Scraper"
log "=========================================="

# Change to project directory
cd "$PROJECT_DIR"

# Check if .env exists, source it
if [ -f "$PROJECT_DIR/.env" ]; then
    log "Loading environment from .env"
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Check required environment variables
if [ -z "$SPREADSHEET_ID" ]; then
    log "ERROR: SPREADSHEET_ID not set!"
    exit 1
fi

# Activate virtual environment
if [ -d "$PROJECT_DIR/.venv" ]; then
    log "Activating virtual environment"
    source "$PROJECT_DIR/.venv/bin/activate"
else
    log "ERROR: Virtual environment not found at $PROJECT_DIR/.venv"
    log "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
    exit 1
fi

# Set credentials path if not set
export GOOGLE_CREDENTIALS_PATH="${GOOGLE_CREDENTIALS_PATH:-$PROJECT_DIR/credentials.json}"

# Run the hockey scraper
log "Running hockey scraper for today (safety net)..."
cd "$PROJECT_DIR"
python -m flashscore_scraper --sport=hockey --days=0 2>&1 | tee -a "$LOG_FILE"
EXIT_TODAY=${PIPESTATUS[0]}

log "Running hockey scraper for tomorrow..."
python -m flashscore_scraper --sport=hockey --days=1 2>&1 | tee -a "$LOG_FILE"
EXIT_TOMORROW=${PIPESTATUS[0]}

if [ $EXIT_TODAY -eq 0 ] && [ $EXIT_TOMORROW -eq 0 ]; then
    log "Hockey scraper completed successfully (today + tomorrow)"
    EXIT_CODE=0
else
    log "ERROR: Hockey scraper failed (today=$EXIT_TODAY, tomorrow=$EXIT_TOMORROW)"
    EXIT_CODE=1
fi

log "=========================================="
log "Finished"
log "=========================================="

exit $EXIT_CODE
