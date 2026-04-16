#!/usr/bin/env bash
set -euo pipefail

# Legacy page refresh wrapper.
# Prefer `uv run reterminal publish --feed ...` for the new scene pipeline.
# Usage: ./refresh.sh [page_name]
#   ./refresh.sh           # Refresh market page (default)
#   ./refresh.sh market    # Refresh just market page
#   ./refresh.sh all       # Refresh all legacy pages

cd "$(dirname "$0")/python"

: "${RETERMINAL_HOST:?Set RETERMINAL_HOST to the device IP before running refresh.sh}"
HOST="$RETERMINAL_HOST"
PAGE="${1:-market}"

if command -v uv >/dev/null 2>&1; then
    uv run reterminal refresh --host "$HOST" "$PAGE" --live
else
    python3 -m reterminal refresh --host "$HOST" "$PAGE" --live
fi
