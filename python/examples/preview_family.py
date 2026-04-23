"""Preview the events.md (slot 2) and activities.md (slot 3) layouts.

Standalone script — reads the two markdowns, renders 800x480 1-bit PNGs for
inspection. Not yet plumbed into the main scene pipeline; this is for fast
layout iteration before promoting either to a real scene kind.

Run:
    uv run python examples/preview_family.py
Outputs:
    /tmp/reterminal-review/slot-2-events.png
    /tmp/reterminal-review/slot-3-activities.png
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

WIDTH, HEIGHT = 800, 480
OUT_DIR = Path("/tmp/reterminal-review")
FAMILY = Path.home() / "madad" / "family"
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    face_index = {"regular": 0, "bold": 1}.get(weight, 0)
    return ImageFont.truetype(str(HELVETICA), size, index=face_index)


# ---- parsing ----

ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(.*)$")

# Category shapes — drawn directly with PIL so we do not depend on font glyph
# coverage. Each key maps to a shape kind the renderer draws in-place.
SHAPES = {
    "trip": "triangle",
    "school": "square",
    "event": "circle",
    "performance": "diamond",
    "camp": "triangle_outline",
    "celebration": "star",
}
DEFAULT_SHAPE = "dot"


def draw_shape(draw: ImageDraw.ImageDraw, kind: str, cx: int, cy: int, size: int = 16) -> None:
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
    else:  # dot
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=0)


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


@dataclass(frozen=True)
class Activity:
    on: date | None
    label: str
    tag: str | None


TAG_RE = re.compile(r"\[([^\]]+)\]\s*$")


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


# ---- rendering ----

def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    return img, ImageDraw.Draw(img)


def to_1bit(img: Image.Image) -> Image.Image:
    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")


def render_events(events: list[Event]) -> Image.Image:
    img, draw = new_canvas()
    margin = 24

    # Tiny kicker
    draw.text((margin, margin), "UPCOMING", font=font(14, "bold"), fill=0)

    # Rows
    shown = events[:5]
    if not shown:
        draw.text((margin, HEIGHT // 2), "(no upcoming events)", font=font(24), fill=0)
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

        # "NN" big + "days" small
        n_str = str(ev.days_until)
        n_w = draw.textlength(n_str, font=big)
        n_bbox = big.getbbox(n_str)
        n_top = baseline - (n_bbox[3] - n_bbox[1]) // 2 - n_bbox[1]
        draw.text((days_col_x, n_top), n_str, font=big, fill=0)

        draw.text(
            (days_col_x + n_w + 8, baseline - 8),
            "days",
            font=sm,
            fill=0,
        )

        # Date (e.g. "May 16")
        date_str = ev.on.strftime("%b %d")
        draw.text(
            (date_col_x, baseline - title.getbbox(date_str)[3] // 2 - 2),
            date_str,
            font=sm,
            fill=0,
        )

        # Category shape (drawn directly, font-independent)
        draw_shape(draw, ev.shape, glyph_col_x + glyph_col_w // 2 - 6, baseline, size=18)

        # Label
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

        # Thin rule between rows
        if i < len(shown) - 1:
            rule_y = y + row_height - 2
            draw.line([(margin, rule_y), (WIDTH - margin, rule_y)], fill=0, width=1)

    return to_1bit(img)


def dither_poster(path: Path, target_h: int) -> Image.Image:
    """Load a color poster, scale preserving aspect, Floyd-Steinberg to 1-bit.

    Movie posters often have dark/low-contrast sources that dither into noise.
    Stretch the histogram with autocontrast, then push contrast and brightness,
    then dither. Produces more legible results on the e-paper panel.
    """
    src = Image.open(path).convert("L")
    ratio = target_h / src.height
    new_w = int(src.width * ratio)
    src = src.resize((new_w, target_h), Image.LANCZOS)
    src = ImageOps.autocontrast(src, cutoff=2)
    src = ImageEnhance.Brightness(src).enhance(1.15)
    src = ImageEnhance.Contrast(src).enhance(1.6)
    return src.convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def render_activities(
    recent: list[Activity],
    queue: list[Activity],
    poster_path: Path | None = None,
) -> Image.Image:
    img, draw = new_canvas()
    margin = 24
    gutter = 24

    kicker = font(14, "bold")
    section_h = font(18, "bold")
    item_f = font(28)
    meta_f = font(16)
    hero_title = font(36, "bold")

    # ---- Right column: full-height poster ----
    poster_h = HEIGHT - margin * 2
    poster = dither_poster(poster_path, poster_h) if poster_path and poster_path.exists() else None

    if poster:
        poster_x = WIDTH - margin - poster.width
        img.paste(poster, (poster_x, margin))
        left_right_edge = poster_x - gutter
    else:
        left_right_edge = WIDTH - margin

    text_max_w = left_right_edge - margin

    # ---- Left column: kicker, recent, next up ----
    draw.text((margin, margin), "ACTIVITIES", font=kicker, fill=0)

    # Recent
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

    # Rule
    rule_y = y + 6
    draw.line([(margin, rule_y), (left_right_edge, rule_y)], fill=0, width=1)

    # Next up
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

    return to_1bit(img)


# ---- main ----

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events_path = FAMILY / "events.md"
    activities_path = FAMILY / "activities.md"
    if not events_path.exists() or not activities_path.exists():
        print(f"Missing inputs: {events_path} and/or {activities_path}")
        return 1

    events = parse_events(events_path)
    recent, queue = parse_activities(activities_path)

    # Poster lookup: if a queued item matches a local poster file by slugified
    # title, use it as the hero image. Keeps posters out of the markdown.
    poster_path: Path | None = None
    posters_dir = OUT_DIR / "posters"
    if queue:
        slug = queue[0].label.lower().replace(" ", "-").replace("'", "")
        for candidate in (posters_dir / f"{slug}.jpg", posters_dir / f"{slug}.png"):
            if candidate.exists():
                poster_path = candidate
                break

    events_img = render_events(events)
    activities_img = render_activities(recent, queue, poster_path=poster_path)

    events_out = OUT_DIR / "slot-2-events.png"
    activities_out = OUT_DIR / "slot-3-activities.png"
    events_img.save(events_out)
    activities_img.save(activities_out)
    print(f"Wrote {events_out}")
    print(f"Wrote {activities_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
