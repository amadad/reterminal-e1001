"""Render the live missions provider output for inspection.

Run:
    uv run python examples/preview_missions.py
Outputs:
    /tmp/reterminal-review/slot-1-missions.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from reterminal.providers.missions import MissionsProvider

OUT_DIR = Path("/tmp/reterminal-review")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scenes = MissionsProvider().fetch()
    if not scenes or scenes[0].prerendered is None:
        print("Missions provider produced no preview")
        return 1
    out = OUT_DIR / "slot-1-missions.png"
    scenes[0].prerendered.save(out)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
