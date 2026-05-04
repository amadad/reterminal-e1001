"""Render the live events and activities provider outputs for inspection.

Run:
    uv run python examples/preview_family.py
Outputs:
    /tmp/reterminal-review/slot-2-events.png
    /tmp/reterminal-review/slot-3-activities.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import OUT_DIR, load_kitchen_scenes

FALLBACK_SLOTS = {"events": 2, "activities": 3}


def _save_scene_preview(scene, path: Path) -> bool:
    if scene.prerendered is None:
        print(f"{scene.id} provider produced no preview")
        return False
    scene.prerendered.save(path)
    print(f"Wrote {path}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, help="Provider manifest to preview")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_id = {scene.id: scene for scene in load_kitchen_scenes(args.feed)}
    ok = True
    for scene_id in ("events", "activities"):
        scene = by_id.get(scene_id)
        if scene is None:
            print(f"{scene_id} provider produced no preview")
            ok = False
            continue
        slot = scene.preferred_slot if scene.preferred_slot is not None else FALLBACK_SLOTS[scene_id]
        ok &= _save_scene_preview(scene, OUT_DIR / f"slot-{slot}-{scene_id}.png")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
