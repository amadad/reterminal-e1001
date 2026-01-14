#!/bin/bash
# Refresh reTerminal pages
# Usage: ./refresh.sh [page_name]
#   ./refresh.sh           # Refresh all pages
#   ./refresh.sh market    # Refresh just market page

cd "$(dirname "$0")"
source .venv/bin/activate

if [ -n "$1" ]; then
    python python/refresh.py --page "$1"
else
    python python/refresh.py --page market  # Default to market only for cron
fi
