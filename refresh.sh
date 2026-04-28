#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
The legacy fixed-page refresh command has been removed from the active CLI.

Use the provider-driven pipeline instead:

  cd python
  uv run reterminal publish --feed examples/kitchen-display.json --preview ./previews
  uv run reterminal publish --feed examples/kitchen-display.json --push --watch --live

For launchd production use, see scripts/reterminal-publish-watch.sh.
EOF

exit 1
