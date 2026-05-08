"""Renderer + SceneProvider for the events kitchen page.

Parses `events.md` via `reterminal.family.events.parse_events`; the parser
already filters past items and sorts by proximity. Tag→shape mapping is a
render concern and lives here so `Event` itself stays pure data.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from PIL import Image

from reterminal.family.events import DEFAULT_PATH, Event, parse_events
from reterminal.payloads import JSONValue
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import HEIGHT, WIDTH, draw_source_stamp, font, new_canvas, render_notice, to_1bit, truncate_text
from reterminal.render.viz import shape as _draw_viz_shape
from reterminal.scenes import SceneSpec


SHAPES = {
    "trip": "triangle",
    "school": "square",
    "event": "circle",
    "performance": "diamond",
    "camp": "triangle_outline",
    "celebration": "star",
}
DEFAULT_SHAPE = "dot"


def _shape_for(event: Event) -> str:
    return SHAPES.get(event.tag or "", DEFAULT_SHAPE)


def render_events(events: list[Event], *, source_path: Path | None = None) -> Image.Image:
    img, draw = new_canvas()
    margin = 24

    draw.text((margin, margin), "UPCOMING", font=font(14, "bold"), fill=0)

    shown = events[:5]
    if not shown:
        draw.text((margin, HEIGHT // 2), "(no upcoming events)", font=font(24), fill=0)
        draw_source_stamp(draw, source_path, stale_after=timedelta(days=14))
        return to_1bit(img)

    row_top = margin + 42
    row_height = (HEIGHT - row_top - margin) // len(shown)

    days_col_x = margin
    days_col_w = 200
    date_col_x = days_col_x + days_col_w
    date_col_w = 110
    glyph_col_x = date_col_x + date_col_w
    glyph_col_w = 40
    label_col_x = glyph_col_x + glyph_col_w

    big = font(56, "bold")
    sm = font(16)
    title = font(28)

    for i, ev in enumerate(shown):
        y = row_top + i * row_height
        baseline = y + row_height // 2

        n_str = str(ev.days_until)
        n_w = draw.textlength(n_str, font=big)
        n_bbox = big.getbbox(n_str)
        n_top = baseline - (n_bbox[3] - n_bbox[1]) // 2 - n_bbox[1]
        draw.text((days_col_x, n_top), n_str, font=big, fill=0)
        draw.text((days_col_x + n_w + 8, baseline - 8), "days", font=sm, fill=0)

        date_str = ev.on.strftime("%b %d")
        draw.text((date_col_x, baseline - title.getbbox(date_str)[3] // 2 - 2), date_str, font=sm, fill=0)

        _draw_viz_shape(draw, glyph_col_x + glyph_col_w // 2 - 6, baseline, _shape_for(ev), size=18)

        max_w = WIDTH - label_col_x - margin
        label = truncate_text(draw, ev.label, title, max_w)
        label_bbox = title.getbbox(label)
        draw.text(
            (label_col_x, baseline - (label_bbox[3] - label_bbox[1]) // 2 - label_bbox[1]),
            label,
            font=title,
            fill=0,
        )

        if i < len(shown) - 1:
            rule_y = y + row_height - 2
            draw.line([(margin, rule_y), (WIDTH - margin, rule_y)], fill=0, width=1)

    draw_source_stamp(draw, source_path, stale_after=timedelta(days=14))
    return to_1bit(img)


class EventsProvider:
    name = "events"

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path).expanduser()

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            image = render_notice("Upcoming", "events source missing", str(self.path))
        else:
            events = parse_events(self.path)
            image = render_events(events, source_path=self.path)
        return [
            SceneSpec(
                id="events",
                kind="prerendered",
                title="Upcoming",
                priority=80,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, JSONValue]) -> EventsProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return EventsProvider(path=path)


register_provider("events", _factory)
