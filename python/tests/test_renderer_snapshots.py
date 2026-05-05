"""Snapshot tests for the four kitchen-display renderers.

Each renderer is pure: markdown → PIL.Image (1-bit, 800x480). We freeze a
fixture file at a known mtime, render it, hash the raw bitmap, and compare
against a stored hash. This catches:

- Layout drift when one renderer is changed and silently affects how we
  expect the others to look.
- Accidental non-determinism (timestamp leakage, locale-dependent format).
- Regressions from refactors of the shared `render/kitchen.py` helpers.

To regenerate goldens after an intentional layout change:

    RETERMINAL_UPDATE_GOLDEN=1 uv run --extra dev pytest -q tests/test_renderer_snapshots.py

Then commit `tests/fixtures/kitchen_renderer_goldens.json` alongside the
renderer change so the snapshot pin moves in the same commit.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path

import pytest

from reterminal.encoding import pil_to_raw
from reterminal.providers.activities import parse_activities, render_activities
from reterminal.providers.calendar import parse_calendar, render_calendar
from reterminal.providers.events import render_events
from reterminal.providers.missions import parse_missions, render_missions
from reterminal.render.kitchen import HELVETICA, draw_source_stamp


# Snapshot bitmaps are pinned to Helvetica.ttc (macOS). On Linux CI the
# kitchen renderer falls back to PIL's default bitmap font, which produces
# completely different pixels — so the goldens (and any ink-counting
# assertions) are only meaningful on a host that actually has Helvetica.
pytestmark = pytest.mark.skipif(
    not HELVETICA.exists(),
    reason="Helvetica.ttc not available; renderer falls back to PIL default font",
)


GOLDENS_FILE = Path(__file__).parent / "fixtures" / "kitchen_renderer_goldens.json"
FROZEN_MTIME = datetime(2026, 5, 5, 9, 0, 0).timestamp()
FROZEN_TODAY = date(2026, 5, 5)


CALENDAR_FIXTURE = """\
# Today

## Today

- 9:30am Piano [@kid1]
- 12:00pm Family lunch
- 4:00pm Baseball practice (Ammar)

## Tomorrow

- 7:50am Play Group (Laila)
- 4:45pm Ballet (Laila)

## Notes

ignored.
"""

MISSIONS_FIXTURE = """\
# Missions

## Active

### Laila
kind: project
title: STEAM Fair
progress: 1 / 4 weeks
next: pick a problem

### Ammar
kind: habit
title: Reading
progress: 7 days
streak: 1 1 1 1 1 1 1
next: read a chapter

### Noora
kind: milestone
title: Standing up
progress: 0 / 3
next: pull up on couch

### Hasan
kind: goal
title: Soccer goals
progress: 3 / 10
next: practice shots
"""

EVENTS_FIXTURE = """\
# Events

## Upcoming

- 2026-05-16 Cradle Con [event]
- 2026-05-22 Maryland [trip]
- 2026-06-13 Recital [performance]
- 2026-06-19 Great Wolf Lodge [trip]
- 2026-06-26 Last day of school [school]
"""

ACTIVITIES_FIXTURE = """\
# Activities

## Recent

- 2026-04-24 The Princess Bride [movie]
- 2026-04-18 The Fifth Element [movie]
- 2026-04-17 Honey I Shrunk the Kids [movie]

## Queue

- Stranger Things: Tales from '85 [series]
- Back to the Future [movie]
"""


def _digest(image) -> str:
    return hashlib.sha256(pil_to_raw(image)).hexdigest()


def _check_or_update(name: str, image) -> None:
    digest = _digest(image)
    goldens: dict[str, str] = {}
    if GOLDENS_FILE.exists():
        goldens = json.loads(GOLDENS_FILE.read_text())
    if os.environ.get("RETERMINAL_UPDATE_GOLDEN"):
        goldens[name] = digest
        GOLDENS_FILE.parent.mkdir(parents=True, exist_ok=True)
        GOLDENS_FILE.write_text(json.dumps(goldens, indent=2, sort_keys=True) + "\n")
        return
    expected = goldens.get(name)
    assert expected is not None, (
        f"No golden for {name!r}. Regenerate with "
        f"RETERMINAL_UPDATE_GOLDEN=1 pytest tests/test_renderer_snapshots.py"
    )
    assert digest == expected, (
        f"Renderer {name!r} drifted: got {digest}, expected {expected}. "
        f"If intentional, regenerate with RETERMINAL_UPDATE_GOLDEN=1."
    )


def _write_frozen(path: Path, body: str) -> Path:
    path.write_text(body)
    os.utime(path, (FROZEN_MTIME, FROZEN_MTIME))
    return path


def test_calendar_render_snapshot(tmp_path: Path):
    md = _write_frozen(tmp_path / "calendar.md", CALENDAR_FIXTURE)
    today, tomorrow = parse_calendar(md)
    image = render_calendar(today, tomorrow, source_path=md)
    _check_or_update("calendar", image)


def test_missions_render_snapshot(tmp_path: Path):
    md = _write_frozen(tmp_path / "missions.md", MISSIONS_FIXTURE)
    missions = parse_missions(md)
    image = render_missions(missions, source_path=md)
    _check_or_update("missions", image)


def test_events_render_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Events renders `days_until` from `date.today()`; freeze it."""
    md = _write_frozen(tmp_path / "events.md", EVENTS_FIXTURE)

    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return FROZEN_TODAY

    monkeypatch.setattr("reterminal.providers.events.date", _FrozenDate)
    # Re-parse under the frozen date so days_until / past-event filtering match.
    from reterminal.providers.events import parse_events
    events = parse_events(md)
    image = render_events(events, source_path=md)
    _check_or_update("events", image)


def test_activities_render_snapshot(tmp_path: Path):
    md = _write_frozen(tmp_path / "activities.md", ACTIVITIES_FIXTURE)
    recent, queue = parse_activities(md)
    image = render_activities(recent, queue, poster_path=None, source_path=md)
    _check_or_update("activities", image)


def test_renderers_are_deterministic(tmp_path: Path):
    """Same input → same bytes. Fast guard against latent non-determinism."""
    md = _write_frozen(tmp_path / "missions.md", MISSIONS_FIXTURE)
    missions = parse_missions(md)
    img1 = render_missions(missions, source_path=md)
    img2 = render_missions(missions, source_path=md)
    assert pil_to_raw(img1) == pil_to_raw(img2)


# -- stale-glyph behavior tests (covers task #2 wiring) ----------------------


def _stamp_ink_count(image, x0: int, y0: int, x1: int, y1: int) -> int:
    """Count black pixels in a rectangle. Fresh stamp = thin glyphs; stale
    pill = solid filled rect, so the counts differ by an order of magnitude."""
    return sum(
        1
        for y in range(y0, y1)
        for x in range(x0, x1)
        if image.getpixel((x, y)) == 0
    )


def test_stale_glyph_when_threshold_exceeded_vs_fresh(tmp_path: Path):
    """Stale draws a solid black pill; fresh draws thin glyph ink. The
    inked-pixel count in the stamp region is the cleanest discriminator."""
    from datetime import timedelta

    from PIL import Image, ImageDraw

    from reterminal.render.kitchen import HEIGHT, WIDTH

    md = tmp_path / "calendar.md"
    md.write_text("## Today\n- 9:30am Piano\n")

    # Fresh
    fresh_t = datetime(2026, 5, 5, 8, 30, 0).timestamp()
    os.utime(md, (fresh_t, fresh_t))
    fresh_img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw_source_stamp(
        ImageDraw.Draw(fresh_img),
        md,
        stale_after=timedelta(hours=2),
        now=datetime(2026, 5, 5, 9, 0, 0),
    )

    # Stale (mtime 6h before now)
    stale_t = datetime(2026, 5, 5, 0, 0, 0).timestamp()
    os.utime(md, (stale_t, stale_t))
    stale_img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw_source_stamp(
        ImageDraw.Draw(stale_img),
        md,
        stale_after=timedelta(hours=2),
        now=datetime(2026, 5, 5, 6, 0, 0),
    )

    # Stamp region: bottom-right corner.
    region = (WIDTH - 220, HEIGHT - 26, WIDTH - 20, HEIGHT - 6)
    fresh_ink = _stamp_ink_count(fresh_img, *region)
    stale_ink = _stamp_ink_count(stale_img, *region)
    # Stale pill is filled background; fresh stamp is glyph strokes only.
    assert stale_ink > fresh_ink * 3, (
        f"expected stale region to be much darker than fresh; "
        f"got stale={stale_ink} fresh={fresh_ink}"
    )


def test_stamp_omitted_when_no_threshold_set(tmp_path: Path):
    """Without `stale_after`, the stamp never escalates — backwards-compatible."""
    from PIL import Image, ImageDraw

    from reterminal.render.kitchen import HEIGHT, WIDTH

    md = tmp_path / "calendar.md"
    md.write_text("## Today\n- 9:30am Piano\n")
    very_old = datetime(2020, 1, 1).timestamp()
    os.utime(md, (very_old, very_old))

    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw_source_stamp(ImageDraw.Draw(img), md)  # no stale_after
    region = (WIDTH - 220, HEIGHT - 26, WIDTH - 20, HEIGHT - 6)
    ink = _stamp_ink_count(img, *region)
    # Just glyphs, never a filled pill — ink is bounded.
    assert 0 < ink < 250
