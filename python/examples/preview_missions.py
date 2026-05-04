"""Render the live missions provider output for inspection.

Run:
    uv run python examples/preview_missions.py
Outputs:
    /tmp/reterminal-review/slot-1-missions.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import OUT_DIR, load_kitchen_scenes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, help="Provider manifest to preview")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scenes = [scene for scene in load_kitchen_scenes(args.feed) if scene.id == "missions"]
    if not scenes or scenes[0].prerendered is None:
        print("Missions provider produced no preview")
        return 1
    slot = scenes[0].preferred_slot if scenes[0].preferred_slot is not None else 1
    out = OUT_DIR / f"slot-{slot}-missions.png"
    scenes[0].prerendered.save(out)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
