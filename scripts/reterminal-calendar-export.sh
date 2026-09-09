#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${RETERMINAL_REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
UV_BIN="${UV_BIN:-$(command -v uv)}"

exec env -u VIRTUAL_ENV "$UV_BIN" --directory "$REPO_ROOT/python" run reterminal calendar-export \
  --destination "${RETERMINAL_CALENDAR_OUTPUT:-$REPO_ROOT/artifacts/local/family-calendar.json}" \
  --config-dir "${RETERMINAL_CALENDAR_CONFIG_DIR:-$HOME/.config/gws-amadad}" \
  --calendar "${RETERMINAL_CALENDAR_NAME:-Family}" \
  --timezone "${RETERMINAL_TIMEZONE:-America/New_York}" \
  --gws "${GWS_BIN:-gws}" "$@"
