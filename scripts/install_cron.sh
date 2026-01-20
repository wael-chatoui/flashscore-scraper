#!/bin/bash
#
# Install cron job or systemd timer for the FlashScore scraper
#
# Usage:
#   ./install_cron.sh cron      # Install crontab entry
#   ./install_cron.sh systemd   # Install systemd timer (recommended)
#   ./install_cron.sh remove    # Remove all scheduled tasks
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
USER=$(whoami)

case "$1" in
    cron)
        echo "Installing cron job..."

        # Create cron entry (runs at 1:00 AM daily to scrape tomorrow's matches)
        CRON_CMD="0 1 * * * $SCRIPT_DIR/run_scraper.sh >> $PROJECT_DIR/logs/cron.log 2>&1"

        # Check if already installed
        if crontab -l 2>/dev/null | grep -q "run_scraper.sh"; then
            echo "Cron job already exists. Updating..."
            crontab -l | grep -v "run_scraper.sh" | crontab -
        fi

        # Add new cron entry
        (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

        echo "Cron job installed:"
        echo "  Schedule: Daily at 1:00 AM (scrapes tomorrow's matches)"
        echo "  Command: $SCRIPT_DIR/run_scraper.sh"
        echo ""
        echo "View with: crontab -l"
        ;;

    systemd)
        echo "Installing systemd timer..."

        # Create user systemd directory
        mkdir -p ~/.config/systemd/user

        # Copy and customize service file
        sed "s|%i|$USER|g; s|/home/%i/Work/test/scriping-sports|$PROJECT_DIR|g" \
            "$SCRIPT_DIR/flashscore-scraper.service" > ~/.config/systemd/user/flashscore-scraper.service

        # Copy timer file
        cp "$SCRIPT_DIR/flashscore-scraper.timer" ~/.config/systemd/user/

        # Reload systemd and enable timer
        systemctl --user daemon-reload
        systemctl --user enable flashscore-scraper.timer
        systemctl --user start flashscore-scraper.timer

        echo "Systemd timer installed and started:"
        echo "  Schedule: Daily at 1:00 AM (scrapes tomorrow's matches)"
        echo ""
        echo "Commands:"
        echo "  Status:  systemctl --user status flashscore-scraper.timer"
        echo "  Logs:    journalctl --user -u flashscore-scraper.service"
        echo "  Run now: systemctl --user start flashscore-scraper.service"
        echo "  Disable: systemctl --user disable flashscore-scraper.timer"
        ;;

    remove)
        echo "Removing scheduled tasks..."

        # Remove cron
        if crontab -l 2>/dev/null | grep -q "run_scraper.sh"; then
            crontab -l | grep -v "run_scraper.sh" | crontab -
            echo "Removed cron job"
        fi

        # Remove systemd
        if [ -f ~/.config/systemd/user/flashscore-scraper.timer ]; then
            systemctl --user stop flashscore-scraper.timer 2>/dev/null || true
            systemctl --user disable flashscore-scraper.timer 2>/dev/null || true
            rm -f ~/.config/systemd/user/flashscore-scraper.timer
            rm -f ~/.config/systemd/user/flashscore-scraper.service
            systemctl --user daemon-reload
            echo "Removed systemd timer"
        fi

        echo "All scheduled tasks removed"
        ;;

    *)
        echo "Usage: $0 {cron|systemd|remove}"
        echo ""
        echo "Options:"
        echo "  cron     - Install crontab entry (runs at 1:00 AM daily)"
        echo "  systemd  - Install systemd timer (recommended, runs at 1:00 AM daily)"
        echo "  remove   - Remove all scheduled tasks"
        echo ""
        echo "The scraper runs at 1:00 AM and fetches tomorrow's matches (J+1)."
        echo "This way, the Google Sheet is ready with match data when the client wakes up."
        exit 1
        ;;
esac
