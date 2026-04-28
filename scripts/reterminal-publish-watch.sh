#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${RETERMINAL_REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON_DIR="$REPO_ROOT/python"
UV_BIN="${UV_BIN:-/Users/amadad/.local/bin/uv}"
FEED="${RETERMINAL_FEED:-$PYTHON_DIR/examples/kitchen-display.json}"
DISCOVERY_TIMEOUT="${RETERMINAL_DISCOVERY_TIMEOUT:-1.5}"
DISCOVERY_WORKERS="${RETERMINAL_DISCOVERY_WORKERS:-32}"

cd "$PYTHON_DIR"

if [[ -z "${RETERMINAL_HOST:-}" ]]; then
  discover_args=(reterminal discover --output json --timeout "$DISCOVERY_TIMEOUT" --workers "$DISCOVERY_WORKERS")
  if [[ -n "${RETERMINAL_DISCOVERY_SUBNET:-}" ]]; then
    discover_args+=(--subnet "$RETERMINAL_DISCOVERY_SUBNET")
  fi

  discovery_json="$($UV_BIN run "${discover_args[@]}")"
  resolved_host="$(DISCOVERY_JSON="$discovery_json" python3 - <<'PY'
import json
import os

results = json.loads(os.environ.get("DISCOVERY_JSON", "[]"))
if not results:
    raise SystemExit(1)
first = results[0]
print(first.get("target") or first.get("status", {}).get("ip") or "")
PY
)" || {
    echo "No reachable reTerminal host found. Set RETERMINAL_HOST or RETERMINAL_DISCOVERY_SUBNET." >&2
    exit 1
  }
  export RETERMINAL_HOST="$resolved_host"
fi

exec "$UV_BIN" run reterminal publish \
  --feed "$FEED" \
  --push \
  --watch \
  --live \
  "$@"
