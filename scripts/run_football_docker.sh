#!/bin/bash
#
# FlashScore Football Scraper - Docker Runner
#
# Designed for the ofelia scheduler container on the VPS.
# It runs the football service defined in docker-compose.yml.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/scheduler_football_$(date +%Y-%m-%d).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting football docker job"
cd "$PROJECT_DIR"
docker compose run --rm football-scraper 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

if [ "$EXIT_CODE" -eq 0 ]; then
    log "Football docker job completed successfully"
else
    log "ERROR: Football docker job failed with exit code $EXIT_CODE"
fi

exit "$EXIT_CODE"