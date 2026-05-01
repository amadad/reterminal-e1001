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

if [[ -z "${RETERMINAL_HOST:-}" ]]; then
  while [[ -z "${RETERMINAL_HOST:-}" ]]; do
    discover_args=(reterminal discover --output json --timeout "$DISCOVERY_TIMEOUT" --workers "$DISCOVERY_WORKERS")
    if [[ -n "${RETERMINAL_DISCOVERY_SUBNET:-}" ]]; then
      discover_args+=(--subnet "$RETERMINAL_DISCOVERY_SUBNET")
    fi

    discovery_json="$($UV_BIN run "${discover_args[@]}" 2>/dev/null || printf '[]')"
    resolved_host="$(DISCOVERY_JSON="$discovery_json" python3 - <<'PY'
import json
import os

try:
    results = json.loads(os.environ.get("DISCOVERY_JSON", "[]"))
except json.JSONDecodeError:
    results = []
if results:
    first = results[0]
    print(first.get("target") or first.get("status", {}).get("ip") or "")
PY
)"
    if [[ -n "$resolved_host" ]]; then
      export RETERMINAL_HOST="$resolved_host"
      break
    fi
    echo "No reachable reTerminal host found; retrying in ${DISCOVERY_RETRY_SECONDS}s." >&2
    sleep "$DISCOVERY_RETRY_SECONDS"
  done
fi

exec "$UV_BIN" run reterminal publish \
  --feed "$FEED" \
  --push \
  --watch \
  --live \
  "$@"
