#!/bin/bash
# Refresh reTerminal pages
# Usage: ./refresh.sh [page_name]
#   ./refresh.sh           # Refresh market page (default for cron)
#   ./refresh.sh market    # Refresh just market page
#   ./refresh.sh all       # Refresh all pages

cd "$(dirname "$0")/python"
source .venv/bin/activate 2>/dev/null || source ../.venv/bin/activate 2>/dev/null

# Load environment if .env exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -n "$1" ]; then
    python -m reterminal refresh "$1"
else
    python -m reterminal refresh market  # Default to market only for cron
fi
