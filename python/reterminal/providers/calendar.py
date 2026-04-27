"""SceneProvider for the calendar slot (slot 0).

Reads ~/madad/family/calendar.md (## Today + ## Tomorrow), renders a
two-column today-board. The file is machine-written by OpenClaw heartbeat
from gws — this provider has no Google dependency and never makes a network
call. If the file is missing or empty, the provider returns no scenes and
the slot keeps showing whatever was last pushed.

Line format inside ## Today and ## Tomorrow (per CONVENTIONS.md):

    HH:MM[am|pm] Label [@who]

Examples:
    - 9:30am Hasan piano [@hasan]
    - 12:00pm Family lunch
    - 4:00pm Ammar baseball practice [@ammar]
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from reterminal.providers.manifest import register_provider
from reterminal.scenes import SceneSpec


WIDTH, HEIGHT = 800, 480
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")
DEFAULT_PATH = Path.home() / "madad" / "family" / "calendar.md"

TIME_RE = re.compile(r"^(\d{1,2}(?::\d{2})?(?:am|pm)?)\s+(.*)$", re.IGNORECASE)
WHO_RE = re.compile(r"\[@([^\]]+)\]\s*$")


@dataclass(frozen=True)
class CalendarItem:
    time: str
    label: str
    who: str | None


def _parse_line(raw: str) -> CalendarItem | None:
    line = raw.strip()
    if not line.startswith("- "):
        return None
    body = line[2:].strip()
    if not body:
        return None
    who = None
    m_who = WHO_RE.search(body)
    if m_who:
        who = m_who.group(1).strip().lower()
        body = body[: m_who.start()].strip()
    m_time = TIME_RE.match(body)
    if m_time:
        time = m_time.group(1)
        label = m_time.group(2).strip()
    else:
        time = ""
        label = body
    return CalendarItem(time=time, label=label, who=who)


def parse_calendar(path: Path) -> tuple[list[CalendarItem], list[CalendarItem]]:
    today: list[CalendarItem] = []
    tomorrow: list[CalendarItem] = []
    section: str | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## "):
            name = line[3:].strip().lower()
            section = name if name in {"today", "tomorrow"} else None
            continue
        if section is None:
            continue
        item = _parse_line(line)
        if item is None:
            continue
        (today if section == "today" else tomorrow).append(item)
    return today, tomorrow


def _font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    face_index = {"regular": 0, "bold": 1}.get(weight, 0)
    return ImageFont.truetype(str(HELVETICA), size, index=face_index)


def _truncate(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> str:
    label = text
    while draw.textlength(label, font=font) > max_w and len(label) > 4:
        label = label[:-2] + "…"
    return label


def _render_column(
    draw: ImageDraw.ImageDraw,
    items: list[CalendarItem],
    *,
    x: int,
    y: int,
    width: int,
    bottom: int,
    title: str,
) -> None:
    title_f = _font(18, "bold")
    time_f = _font(20, "bold")
    label_f = _font(24)
    who_f = _font(14)

    draw.text((x, y), title, font=title_f, fill=0)
    draw.line([(x, y + 28), (x + width, y + 28)], fill=0, width=1)

    cursor = y + 44
    if not items:
        draw.text((x, cursor), "(nothing scheduled)", font=label_f, fill=0)
        return

    for item in items:
        if cursor > bottom - 30:
            break
        time_str = item.time or "—"
        time_w = draw.textlength(time_str, font=time_f)
        draw.text((x, cursor), time_str, font=time_f, fill=0)
        label_x = x + max(int(time_w), 80) + 12
        label = _truncate(draw, item.label, label_f, x + width - label_x)
        draw.text((label_x, cursor + 2), label, font=label_f, fill=0)
        if item.who:
            who_str = f"@{item.who}"
            who_w = draw.textlength(who_str, font=who_f)
            draw.text((x + width - who_w, cursor + 32), who_str, font=who_f, fill=0)
        cursor += 48


def render_calendar(today: list[CalendarItem], tomorrow: list[CalendarItem]) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    margin = 24
    gutter = 28

    draw.text((margin, margin), "AGENDA", font=_font(13, "bold"), fill=0)

    body_top = margin + 30
    body_bottom = HEIGHT - margin
    col_w = (WIDTH - margin * 2 - gutter) // 2

    _render_column(
        draw, today,
        x=margin, y=body_top, width=col_w, bottom=body_bottom,
        title="TODAY",
    )
    _render_column(
        draw, tomorrow,
        x=margin + col_w + gutter, y=body_top, width=col_w, bottom=body_bottom,
        title="TOMORROW",
    )

    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")


class CalendarProvider:
    name = "calendar"

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path).expanduser()

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            return []
        today, tomorrow = parse_calendar(self.path)
        if not today and not tomorrow:
            return []
        image = render_calendar(today, tomorrow)
        return [
            SceneSpec(
                id="calendar",
                kind="prerendered",
                title="Agenda",
                priority=100,
                preferred_slot=0,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, Any]) -> CalendarProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return CalendarProvider(path=path)


register_provider("calendar", _factory)
