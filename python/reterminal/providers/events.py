"""SceneProvider for the events slot (slot 2).

Reads ~/madad/family/events.md (## Upcoming section), sorts by proximity,
drops past items, returns a SceneSpec carrying a prerendered 800x480 1-bit
bitmap. The provider owns parsing and layout end-to-end.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from reterminal.providers.manifest import register_provider
from reterminal.scenes import SceneSpec


WIDTH, HEIGHT = 800, 480
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")
DEFAULT_PATH = Path.home() / "madad" / "family" / "events.md"

ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(.*)$")
TAG_RE = re.compile(r"\[([^\]]+)\]\s*$")

SHAPES = {
    "trip": "triangle",
    "school": "square",
    "event": "circle",
    "performance": "diamond",
    "camp": "triangle_outline",
    "celebration": "star",
}
DEFAULT_SHAPE = "dot"


@dataclass(frozen=True)
class Event:
    on: date
    label: str
    tag: str | None

    @property
    def days_until(self) -> int:
        return (self.on - date.today()).days

    @property
    def shape(self) -> str:
        return SHAPES.get(self.tag or "", DEFAULT_SHAPE)


def parse_events(path: Path) -> list[Event]:
    events: list[Event] = []
    in_section = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_section = line[3:].strip().lower() == "upcoming"
            continue
        if not in_section or not line.startswith("- "):
            continue
        body = line[2:].strip()
        tag = None
        m_tag = TAG_RE.search(body)
        if m_tag:
            tag = m_tag.group(1).strip().lower()
            body = body[: m_tag.start()].strip()
        m = ISO_DATE.match(body)
        if not m:
            continue
        y, mo, d, label = m.groups()
        events.append(Event(date(int(y), int(mo), int(d)), label.strip(), tag))
    events.sort(key=lambda e: e.on)
    return [e for e in events if e.days_until >= 0]


def _font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    face_index = {"regular": 0, "bold": 1}.get(weight, 0)
    return ImageFont.truetype(str(HELVETICA), size, index=face_index)


def _draw_shape(draw: ImageDraw.ImageDraw, kind: str, cx: int, cy: int, size: int = 16) -> None:
    r = size // 2
    if kind == "circle":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    elif kind == "square":
        draw.rectangle([cx - r, cy - r, cx + r, cy + r], fill=0)
    elif kind == "triangle":
        draw.polygon([(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)], fill=0)
    elif kind == "triangle_outline":
        draw.polygon([(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)], outline=0, width=2)
    elif kind == "diamond":
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=0)
    elif kind == "star":
        import math
        pts = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r // 2
            pts.append((cx + rr * math.cos(angle), cy + rr * math.sin(angle)))
        draw.polygon(pts, fill=0)
    else:
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=0)


def render_events(events: list[Event]) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    margin = 24

    draw.text((margin, margin), "UPCOMING", font=_font(14, "bold"), fill=0)

    shown = events[:5]
    if not shown:
        draw.text((margin, HEIGHT // 2), "(no upcoming events)", font=_font(24), fill=0)
        return img.point(lambda x: 255 if x >= 192 else 0, mode="1")

    row_top = margin + 42
    row_height = (HEIGHT - row_top - margin) // len(shown)

    days_col_x = margin
    days_col_w = 200
    date_col_x = days_col_x + days_col_w
    date_col_w = 110
    glyph_col_x = date_col_x + date_col_w
    glyph_col_w = 40
    label_col_x = glyph_col_x + glyph_col_w

    big = _font(56, "bold")
    sm = _font(16)
    title = _font(28)

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

        _draw_shape(draw, ev.shape, glyph_col_x + glyph_col_w // 2 - 6, baseline, size=18)

        label = ev.label
        max_w = WIDTH - label_col_x - margin
        while draw.textlength(label, font=title) > max_w and len(label) > 4:
            label = label[:-2] + "…"
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

    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")


class EventsProvider:
    name = "events"

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path).expanduser()

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            return []
        events = parse_events(self.path)
        image = render_events(events)
        return [
            SceneSpec(
                id="events",
                kind="prerendered",
                title="Upcoming",
                priority=80,
                preferred_slot=2,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, Any]) -> EventsProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return EventsProvider(path=path)


register_provider("events", _factory)
