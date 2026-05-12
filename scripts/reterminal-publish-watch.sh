#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${RETERMINAL_REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON_DIR="$REPO_ROOT/python"
if [[ -z "${UV_BIN:-}" ]]; then
  UV_BIN="$(command -v uv || true)"
  if [[ -z "$UV_BIN" ]]; then
    echo "uv not found. Set UV_BIN or install uv." >&2
    exit 127
  fi
fi
DEFAULT_FEED="$PYTHON_DIR/examples/kitchen-display.json"
if [[ -f "$PYTHON_DIR/examples/kitchen-display.local.json" ]]; then
  DEFAULT_FEED="$PYTHON_DIR/examples/kitchen-display.local.json"
fi
FEED="${RETERMINAL_FEED:-$DEFAULT_FEED}"
DISCOVERY_TIMEOUT="${RETERMINAL_DISCOVERY_TIMEOUT:-1.5}"
DISCOVERY_WORKERS="${RETERMINAL_DISCOVERY_WORKERS:-32}"
DISCOVERY_RETRY_SECONDS="${RETERMINAL_DISCOVERY_RETRY_SECONDS:-30}"

cd "$PYTHON_DIR"

exec "$UV_BIN" run reterminal publish \
  --feed "$FEED" \
  --watch \
  --live \
  "$@"
