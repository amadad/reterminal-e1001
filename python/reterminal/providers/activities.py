"""SceneProvider for the activities slot (slot 3).

Reads ~/madad/family/activities.md (## Recent + ## Queue), renders a 1-bit
800x480 layout: recent activities on the left, next-up hero on the lower
left, optional poster on the right.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from reterminal.providers.manifest import register_provider
from reterminal.scenes import SceneSpec


WIDTH, HEIGHT = 800, 480
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")
DEFAULT_PATH = Path.home() / "madad" / "family" / "activities.md"
POSTERS_DIR = Path("/tmp/reterminal-review/posters")

ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(.*)$")
TAG_RE = re.compile(r"\[([^\]]+)\]\s*$")


@dataclass(frozen=True)
class Activity:
    on: date | None
    label: str
    tag: str | None


def parse_activity_line(line: str) -> Activity | None:
    body = line[2:].strip() if line.startswith("- ") else line.strip()
    if not body:
        return None
    tag = None
    m = TAG_RE.search(body)
    if m:
        tag = m.group(1)
        body = body[: m.start()].strip()
    m = ISO_DATE.match(body)
    if m:
        y, mo, d, label = m.groups()
        return Activity(date(int(y), int(mo), int(d)), label.strip(), tag)
    return Activity(None, body, tag)


def parse_activities(path: Path) -> tuple[list[Activity], list[Activity]]:
    recent: list[Activity] = []
    queue: list[Activity] = []
    section: str | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## "):
            name = line[3:].strip().lower()
            section = name if name in {"recent", "queue"} else None
            continue
        if section is None or not line.startswith("- "):
            continue
        item = parse_activity_line(line)
        if item is None:
            continue
        (recent if section == "recent" else queue).append(item)
    recent.sort(key=lambda a: a.on or date.min, reverse=True)
    return recent, queue


def _font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    face_index = {"regular": 0, "bold": 1}.get(weight, 0)
    return ImageFont.truetype(str(HELVETICA), size, index=face_index)


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
) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    margin = 24
    gutter = 24

    kicker = _font(14, "bold")
    section_h = _font(18, "bold")
    item_f = _font(28)
    meta_f = _font(16)
    hero_title = _font(36, "bold")

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

    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")


class ActivitiesProvider:
    name = "activities"

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path).expanduser()

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            return []
        recent, queue = parse_activities(self.path)
        poster = _resolve_poster(queue)
        image = render_activities(recent, queue, poster_path=poster)
        return [
            SceneSpec(
                id="activities",
                kind="prerendered",
                title="Activities",
                priority=70,
                preferred_slot=3,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, Any]) -> ActivitiesProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return ActivitiesProvider(path=path)


register_provider("activities", _factory)
