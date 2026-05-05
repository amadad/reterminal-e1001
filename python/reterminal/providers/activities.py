"""Renderer + SceneProvider for the activities kitchen page.

Parses `activities.md` via `reterminal.family.activities.parse_activities`
and renders a 1-bit 800x480 layout: recent activities on the left, next-up
hero on the lower left, optional dithered poster on the right when a
matching image exists in the posters dir.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from reterminal.family.activities import DEFAULT_PATH, Activity, parse_activities
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import (
    HEIGHT,
    WIDTH,
    draw_source_stamp,
    font,
    render_notice,
    to_1bit,
)
from reterminal.scenes import SceneSpec


POSTERS_DIR = Path("/tmp/reterminal-review/posters")


def _dither_poster(path: Path, target_h: int) -> Image.Image:
    src = Image.open(path).convert("L")
    ratio = target_h / src.height
    new_w = int(src.width * ratio)
    src = src.resize((new_w, target_h), Image.LANCZOS)
    src = ImageOps.autocontrast(src, cutoff=2)
    src = ImageEnhance.Brightness(src).enhance(1.15)
    src = ImageEnhance.Contrast(src).enhance(1.6)
    return src.convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def _resolve_poster(queue: list[Activity]) -> Path | None:
    if not queue:
        return None
    slug = queue[0].label.lower().replace(" ", "-").replace("'", "")
    for ext in ("jpg", "png"):
        candidate = POSTERS_DIR / f"{slug}.{ext}"
        if candidate.exists():
            return candidate
    return None


def render_activities(
    recent: list[Activity],
    queue: list[Activity],
    poster_path: Path | None = None,
    *,
    source_path: Path | None = None,
) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    margin = 24
    gutter = 24

    kicker = font(14, "bold")
    section_h = font(18, "bold")
    item_f = font(28)
    meta_f = font(16)
    hero_title = font(36, "bold")

    poster_h = HEIGHT - margin * 2
    poster = _dither_poster(poster_path, poster_h) if poster_path and poster_path.exists() else None

    if poster:
        poster_x = WIDTH - margin - poster.width
        img.paste(poster, (poster_x, margin))
        left_right_edge = poster_x - gutter
    else:
        left_right_edge = WIDTH - margin

    text_max_w = left_right_edge - margin

    draw.text((margin, margin), "ACTIVITIES", font=kicker, fill=0)

    y = margin + 40
    draw.text((margin, y), "RECENT", font=section_h, fill=0)
    y += 32
    for a in recent[:3]:
        date_s = a.on.strftime("%b %d") if a.on else ""
        dw = draw.textlength(date_s, font=meta_f) if date_s else 0
        label = a.label
        label_budget = text_max_w - dw - 12
        while draw.textlength(label, font=item_f) > label_budget and len(label) > 4:
            label = label[:-2] + "…"
        draw.text((margin, y), label, font=item_f, fill=0)
        if date_s:
            draw.text((left_right_edge - dw, y + 4), date_s, font=meta_f, fill=0)
        y += 46

    rule_y = y + 6
    draw.line([(margin, rule_y), (left_right_edge, rule_y)], fill=0, width=1)

    y = rule_y + 20
    draw.text((margin, y), "NEXT UP", font=section_h, fill=0)
    y += 36
    if queue:
        hero = queue[0]
        label = hero.label
        words = label.split()
        line1, line2 = "", ""
        for w in words:
            candidate = f"{line1} {w}".strip()
            if draw.textlength(candidate, font=hero_title) <= text_max_w:
                line1 = candidate
            else:
                line2 = f"{line2} {w}".strip()
        draw.text((margin, y), line1, font=hero_title, fill=0)
        y += 44
        if line2:
            draw.text((margin, y), line2, font=hero_title, fill=0)
            y += 44
        y += 8
        for a in queue[1:3]:
            rest_label = a.label
            while draw.textlength(rest_label, font=item_f) > text_max_w and len(rest_label) > 4:
                rest_label = rest_label[:-2] + "…"
            draw.text((margin, y), rest_label, font=item_f, fill=0)
            y += 38

    draw_source_stamp(draw, source_path, stale_after=timedelta(days=14))
    return to_1bit(img)


class ActivitiesProvider:
    name = "activities"

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path).expanduser()

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            image = render_notice("Activities", "activities source missing", str(self.path))
        else:
            recent, queue = parse_activities(self.path)
            poster = _resolve_poster(queue)
            image = render_activities(recent, queue, poster_path=poster, source_path=self.path)
        return [
            SceneSpec(
                id="activities",
                kind="prerendered",
                title="Activities",
                priority=70,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, Any]) -> ActivitiesProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return ActivitiesProvider(path=path)


register_provider("activities", _factory)
