#!/usr/bin/env bash
set -euo pipefail

# Legacy page refresh wrapper.
# Prefer `uv run reterminal publish --feed ...` for the new scene pipeline.
# Usage: ./refresh.sh [page_name]
#   ./refresh.sh           # Refresh market page (default)
#   ./refresh.sh market    # Refresh just market page
#   ./refresh.sh all       # Refresh all legacy pages

cd "$(dirname "$0")/python"

HOST="${RETERMINAL_HOST:-192.168.7.77}"
PAGE="${1:-market}"

if command -v uv >/dev/null 2>&1; then
    uv run reterminal refresh --host "$HOST" "$PAGE"
else
    python3 -m reterminal refresh --host "$HOST" "$PAGE"
fi
