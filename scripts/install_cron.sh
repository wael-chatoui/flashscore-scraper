#!/bin/bash
#
# Install cron job or systemd timer for the FlashScore scrapers
#
# Usage:
#   ./install_cron.sh cron      # Install crontab entries (volleyball + hockey)
#   ./install_cron.sh systemd   # Install systemd timers (recommended)
#   ./install_cron.sh remove    # Remove all scheduled tasks
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
USER=$(whoami)

case "$1" in
    cron)
        echo "Installing cron jobs..."

        # Remove existing entries first
        if crontab -l 2>/dev/null | grep -q "run_scraper.sh\|run_hockey_scraper.sh"; then
            echo "Removing existing scraper cron jobs..."
            crontab -l | grep -v "run_scraper.sh\|run_hockey_scraper.sh" | crontab -
        fi

        # Volleyball: 1:00 AM daily
        VOLLEY_CMD="0 1 * * * $SCRIPT_DIR/run_scraper.sh >> $PROJECT_DIR/logs/cron.log 2>&1"
        # Hockey: 2:00 AM daily
        HOCKEY_CMD="0 2 * * * $SCRIPT_DIR/run_hockey_scraper.sh >> $PROJECT_DIR/logs/cron_hockey.log 2>&1"

        (crontab -l 2>/dev/null; echo "$VOLLEY_CMD"; echo "$HOCKEY_CMD") | crontab -

        echo "Cron jobs installed:"
        echo "  Volleyball: Daily at 1:00 AM — $SCRIPT_DIR/run_scraper.sh"
        echo "  Hockey:     Daily at 2:00 AM — $SCRIPT_DIR/run_hockey_scraper.sh"
        echo ""
        echo "View with: crontab -l"
        ;;

    systemd)
        echo "Installing systemd timers..."

        # Create user systemd directory
        mkdir -p ~/.config/systemd/user

        # --- Volleyball ---
        sed "s|%i|$USER|g; s|/home/%i/Work/test/scriping-sports|$PROJECT_DIR|g" \
            "$SCRIPT_DIR/flashscore-scraper.service" > ~/.config/systemd/user/flashscore-scraper.service
        cp "$SCRIPT_DIR/flashscore-scraper.timer" ~/.config/systemd/user/

        # --- Hockey ---
        sed "s|%i|$USER|g; s|/home/%i/Work/test/scriping-sports|$PROJECT_DIR|g" \
            "$SCRIPT_DIR/flashscore-hockey-scraper.service" > ~/.config/systemd/user/flashscore-hockey-scraper.service
        cp "$SCRIPT_DIR/flashscore-hockey-scraper.timer" ~/.config/systemd/user/

        # Reload and enable both
        systemctl --user daemon-reload
        systemctl --user enable flashscore-scraper.timer
        systemctl --user start flashscore-scraper.timer
        systemctl --user enable flashscore-hockey-scraper.timer
        systemctl --user start flashscore-hockey-scraper.timer

        echo "Systemd timers installed and started:"
        echo "  Volleyball: Daily at 1:00 AM"
        echo "  Hockey:     Daily at 2:00 AM"
        echo ""
        echo "Commands:"
        echo "  Status:  systemctl --user status flashscore-scraper.timer"
        echo "           systemctl --user status flashscore-hockey-scraper.timer"
        echo "  Logs:    journalctl --user -u flashscore-scraper.service"
        echo "           journalctl --user -u flashscore-hockey-scraper.service"
        echo "  Run now: systemctl --user start flashscore-scraper.service"
        echo "           systemctl --user start flashscore-hockey-scraper.service"
        echo "  Disable: systemctl --user disable flashscore-scraper.timer"
        echo "           systemctl --user disable flashscore-hockey-scraper.timer"
        ;;

    remove)
        echo "Removing scheduled tasks..."

        # Remove cron
        if crontab -l 2>/dev/null | grep -q "run_scraper.sh\|run_hockey_scraper.sh"; then
            crontab -l | grep -v "run_scraper.sh\|run_hockey_scraper.sh" | crontab -
            echo "Removed cron jobs"
        fi

        # Remove systemd — volleyball
        if [ -f ~/.config/systemd/user/flashscore-scraper.timer ]; then
            systemctl --user stop flashscore-scraper.timer 2>/dev/null || true
            systemctl --user disable flashscore-scraper.timer 2>/dev/null || true
            rm -f ~/.config/systemd/user/flashscore-scraper.timer
            rm -f ~/.config/systemd/user/flashscore-scraper.service
            echo "Removed volleyball systemd timer"
        fi

        # Remove systemd — hockey
        if [ -f ~/.config/systemd/user/flashscore-hockey-scraper.timer ]; then
            systemctl --user stop flashscore-hockey-scraper.timer 2>/dev/null || true
            systemctl --user disable flashscore-hockey-scraper.timer 2>/dev/null || true
            rm -f ~/.config/systemd/user/flashscore-hockey-scraper.timer
            rm -f ~/.config/systemd/user/flashscore-hockey-scraper.service
            echo "Removed hockey systemd timer"
        fi

        systemctl --user daemon-reload 2>/dev/null || true
        echo "All scheduled tasks removed"
        ;;

    *)
        echo "Usage: $0 {cron|systemd|remove}"
        echo ""
        echo "Options:"
        echo "  cron     - Install crontab entries (volleyball at 1 AM, hockey at 2 AM)"
        echo "  systemd  - Install systemd timers (recommended)"
        echo "  remove   - Remove all scheduled tasks"
        echo ""
        echo "Both scrapers run daily so the Google Sheet is ready when the client wakes up."
        exit 1
        ;;
esac
