"""Render the live events and activities provider outputs for inspection.

Run:
    uv run python examples/preview_family.py
Outputs:
    /tmp/reterminal-review/slot-2-events.png
    /tmp/reterminal-review/slot-3-activities.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from reterminal.providers.activities import ActivitiesProvider
from reterminal.providers.events import EventsProvider

OUT_DIR = Path("/tmp/reterminal-review")


def _save_provider_preview(provider, path: Path) -> bool:
    scenes = provider.fetch()
    if not scenes or scenes[0].prerendered is None:
        print(f"{provider.name} provider produced no preview")
        return False
    scenes[0].prerendered.save(path)
    print(f"Wrote {path}")
    return True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    ok &= _save_provider_preview(EventsProvider(), OUT_DIR / "slot-2-events.png")
    ok &= _save_provider_preview(ActivitiesProvider(), OUT_DIR / "slot-3-activities.png")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
