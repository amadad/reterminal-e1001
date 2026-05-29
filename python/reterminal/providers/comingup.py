"""Renderer + SceneProvider for the consolidated "Coming Up" page.

Merges two sources into one forward-looking board:

- `events.md` `## Upcoming` — dated items, proximity-sorted, days-to-go
- `activities.md` `## Queue` — undated "what's next" items

The backward-looking `## Recent` activity log is intentionally not shown here;
this slot is for what's ahead, not a watch history. Dated events render as big
day-count rows up top; the queue follows as a compact footer list.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from PIL import Image

from reterminal.family.activities import Activity, parse_activities
from reterminal.family.events import Event, parse_events
from reterminal.payloads import JSONValue
from reterminal.providers.events import DEFAULT_SHAPE, SHAPES
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import HEIGHT, WIDTH, draw_source_stamp, font, new_canvas, render_notice, to_1bit, truncate_text
from reterminal.render.viz import shape as _draw_viz_shape
from reterminal.scenes import SceneSpec


def _shape_for(tag: str | None) -> str:
    return SHAPES.get(tag or "", DEFAULT_SHAPE)


def render_comingup(
    events: list[Event],
    queue: list[Activity],
    *,
    source_path: Path | None = None,
) -> Image.Image:
    img, draw = new_canvas()
    margin = 24

    draw.text((margin, margin), "COMING UP", font=font(14, "bold"), fill=0)

    queue_shown = queue[:3]
    queue_band = 24 + len(queue_shown) * 28 if queue_shown else 0

    body_top = margin + 44
    body_bottom = HEIGHT - margin - queue_band

    shown = events[: 5 if not queue_shown else 4]
    if not shown and not queue_shown:
        draw.text((margin, HEIGHT // 2), "(nothing coming up)", font=font(24), fill=0)
        draw_source_stamp(draw, source_path, stale_after=timedelta(days=14))
        return to_1bit(img)

    big = font(54, "bold")
    sm = font(16)
    title = font(28)

    days_col_x = margin
    days_col_w = 196
    date_col_x = days_col_x + days_col_w
    date_col_w = 104
    glyph_col_x = date_col_x + date_col_w
    glyph_col_w = 38
    label_col_x = glyph_col_x + glyph_col_w

    if shown:
        row_height = (body_bottom - body_top) // len(shown)
        for i, ev in enumerate(shown):
            y = body_top + i * row_height
            baseline = y + row_height // 2

            n_str = str(ev.days_until)
            n_w = draw.textlength(n_str, font=big)
            n_bbox = big.getbbox(n_str)
            n_top = baseline - (n_bbox[3] - n_bbox[1]) // 2 - n_bbox[1]
            draw.text((days_col_x, n_top), n_str, font=big, fill=0)
            draw.text((days_col_x + n_w + 8, baseline - 8), "days", font=sm, fill=0)

            date_str = ev.on.strftime("%b %d")
            draw.text((date_col_x, baseline - 8), date_str, font=sm, fill=0)

            _draw_viz_shape(draw, glyph_col_x + glyph_col_w // 2 - 6, baseline, _shape_for(ev.tag), size=18)

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

    if queue_shown:
        qy = HEIGHT - margin - queue_band + 2
        draw.line([(margin, qy), (WIDTH - margin, qy)], fill=0, width=1)
        qy += 8
        draw.text((margin, qy), "UP NEXT", font=font(13, "bold"), fill=0)
        qy += 22
        item_f = font(22)
        for a in queue_shown:
            label = truncate_text(draw, a.label, item_f, WIDTH - margin * 2 - 20)
            draw.text((margin, qy), "•", font=item_f, fill=0)
            draw.text((margin + 20, qy), label, font=item_f, fill=0)
            qy += 28

    draw_source_stamp(draw, source_path, stale_after=timedelta(days=14))
    return to_1bit(img)


class ComingUpProvider:
    name = "comingup"

    def __init__(self, events: Path | str, queue: Path | str):
        self.events_path = Path(events).expanduser()
        self.queue_path = Path(queue).expanduser()

    def fetch(self) -> list[SceneSpec]:
        if not self.events_path.exists() and not self.queue_path.exists():
            image = render_notice("Coming Up", "coming-up source missing", str(self.events_path))
        else:
            events = parse_events(self.events_path) if self.events_path.exists() else []
            queue = parse_activities(self.queue_path)[1] if self.queue_path.exists() else []
            # Stamp staleness off whichever source was touched most recently.
            stamp_src = max(
                (p for p in (self.events_path, self.queue_path) if p.exists()),
                key=lambda p: p.stat().st_mtime,
                default=None,
            )
            image = render_comingup(events, queue, source_path=stamp_src)
        return [
            SceneSpec(
                id="comingup",
                kind="prerendered",
                title="Coming Up",
                priority=80,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, JSONValue]) -> ComingUpProvider:
    events = config.get("events", config.get("path", ""))
    queue = config.get("queue", "")
    return ComingUpProvider(events=str(events), queue=str(queue))


register_provider("comingup", _factory)
