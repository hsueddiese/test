#!/usr/bin/env bash
# Adds a cron job that runs the daily email summary at 16:30 every day.
# Usage: bash schedule_setup.sh [path-to-venv-python]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${1:-python3}"
CRON_JOB="30 16 * * * cd \"$SCRIPT_DIR\" && $PYTHON daily_email_summary.py >> \"$SCRIPT_DIR/summary.log\" 2>&1"

# Avoid duplicate entries
( crontab -l 2>/dev/null | grep -v "daily_email_summary.py" ; echo "$CRON_JOB" ) | crontab -
echo "Cron job installed:"
echo "  $CRON_JOB"
