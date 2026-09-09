"""Display-safe wiki projections for a family quest and trip feature.

Both providers read only an explicit ``## Kitchen Display`` section. The rest
of each wiki page can remain private working context and is never copied into
the scene model.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reterminal.payloads import JSONValue
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import (
    AGENDA_BODY,
    AGENDA_LABEL,
    AGENDA_LEADING,
    AGENDA_TITLE,
    BODY_BOLD,
    DISPLAY,
    HEADLINE,
    KICKER,
    MARGIN,
    META,
    WIDTH,
    draw_kicker,
    new_canvas,
    render_notice,
    to_1bit,
)
from reterminal.render.layout import clamp_lines, wrap_text
from reterminal.scenes import SceneSpec


_FIELD_RE = re.compile(r"^-\s+\*\*([^*]+):\*\*\s*(.*?)\s*$")


@dataclass(frozen=True, slots=True)
class QuestCard:
    title: str
    deck: str
    levels: tuple[tuple[str, str], ...]
    dinner: str
    valid_until: date


@dataclass(frozen=True, slots=True)
class TripCard:
    title: str
    dates: str
    starts: date
    route: tuple[str, ...]
    next_action: str
    rule: str
    ready: tuple[str, ...] = ()
    reviewed: date | None = None
    valid_until: date | None = None


def _display_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    in_display = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## "):
            if in_display:
                break
            in_display = line[3:].strip().lower() == "kitchen display"
            continue
        if not in_display or not line:
            continue
        match = _FIELD_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip().lower()
        if key in fields:
            raise ValueError(f"duplicate Kitchen Display field: {key}")
        fields[key] = match.group(2).strip()
    if not in_display:
        raise ValueError("missing `## Kitchen Display` section")
    return fields


def _required(fields: Mapping[str, str], names: tuple[str, ...]) -> None:
    missing = [name for name in names if not fields.get(name)]
    if missing:
        raise ValueError(f"missing Kitchen Display fields: {', '.join(missing)}")


def _iso_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field} date: {value!r}") from exc


def parse_quest(path: Path) -> QuestCard:
    fields = _display_fields(path)
    names = ("title", "deck", "spark", "build", "guide", "dinner", "valid until")
    _required(fields, names)
    return QuestCard(
        title=fields["title"],
        deck=fields["deck"],
        levels=tuple((name.upper(), fields[name]) for name in ("spark", "build", "guide")),
        dinner=fields["dinner"],
        valid_until=_iso_date(fields["valid until"], "valid until"),
    )


def parse_trip(path: Path) -> TripCard:
    fields = _display_fields(path)
    names = ("title", "dates", "starts", "route", "next", "rule")
    _required(fields, names)
    route = tuple(part.strip() for part in re.split(r"\s*(?:\||→)\s*", fields["route"]) if part.strip())
    if len(route) < 2:
        raise ValueError("Kitchen Display route needs at least two stops")
    reviewed = fields.get("reviewed")
    return TripCard(
        title=fields["title"],
        dates=fields["dates"],
        starts=_iso_date(fields["starts"], "starts"),
        route=route,
        next_action=fields["next"],
        rule=fields["rule"],
        ready=tuple(fields[key] for key in ("ready 1", "ready 2", "ready 3") if fields.get(key)),
        reviewed=_iso_date(reviewed, "reviewed") if reviewed else None,
        valid_until=_iso_date(fields.get("valid until") or fields["ends"], "valid until")
        if fields.get("valid until") or fields.get("ends") else None,
    )


def _text_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    f: ImageFont.ImageFont,
    width: int,
    max_lines: int,
) -> list[str]:
    return clamp_lines(draw, wrap_text(draw, text, f, width), f, width, max_lines)


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    *,
    x: int,
    y: int,
    f: ImageFont.ImageFont,
    fill: int = 0,
    line_height: int,
) -> int:
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill)
        y += line_height
    return y


def _draw_quest_mark(draw: ImageDraw.ImageDraw, title: str) -> None:
    x0, y0, x1, y1 = MARGIN, 64, 244, 446
    draw.rectangle([x0, y0, x1, y1], fill=0)

    digest = hashlib.sha256(title.encode()).digest()
    cell = 30
    grid_w = cell * 5
    gx = x0 + (x1 - x0 - grid_w) // 2
    gy = 112
    bit = 0
    for row in range(5):
        row_values: list[bool] = []
        for _ in range(3):
            byte = digest[bit // 8]
            row_values.append(bool(byte & (1 << (bit % 8))))
            bit += 1
        values = row_values + row_values[-2::-1]
        for col, enabled in enumerate(values):
            if enabled:
                inset = 2
                draw.rectangle(
                    [
                        gx + col * cell + inset,
                        gy + row * cell + inset,
                        gx + (col + 1) * cell - inset,
                        gy + (row + 1) * cell - inset,
                    ],
                    fill=255,
                )

    draw.text((x0 + 24, 304), "PICK YOUR", font=KICKER, fill=255)
    draw.text((x0 + 24, 334), "LEVEL", font=HEADLINE, fill=255)
    draw.line([(x0 + 24, 378), (x1 - 24, 378)], fill=255, width=2)
    draw.text((x0 + 24, 394), "MAKE · TEST · SHARE", font=KICKER, fill=255)


def render_quest(card: QuestCard) -> Image.Image:
    """One current household idea, large enough for a kitchen glance."""
    img, draw = new_canvas()
    draw_kicker(draw, "Family quest", right=f"THRU {card.valid_until:%b %-d}".upper(), label_font=AGENDA_LABEL)
    width = WIDTH - MARGIN * 2
    title = card.title
    if len(wrap_text(draw, title, AGENDA_TITLE, width)) > 2:
        title = "A current family quest"
    cursor = _draw_lines(draw, wrap_text(draw, title, AGENDA_TITLE, width), x=MARGIN, y=76,
                         f=AGENDA_TITLE, line_height=40)
    deck = wrap_text(draw, card.deck, AGENDA_BODY, width)
    if len(deck) <= 2:
        cursor = _draw_lines(draw, deck, x=MARGIN, y=cursor + 20, f=AGENDA_BODY, line_height=AGENDA_LEADING)
    label, action = card.levels[0]
    cursor = max(244, cursor + 28)
    draw.text((MARGIN, cursor), label, font=AGENDA_LABEL, fill=0)
    lines = wrap_text(draw, action, AGENDA_BODY, width)
    if cursor + 30 + len(lines) * AGENDA_LEADING > 408:
        lines = ["See the family quest for the full idea."]
    _draw_lines(draw, lines, x=MARGIN, y=cursor + 30, f=AGENDA_BODY, line_height=AGENDA_LEADING)
    draw.text((MARGIN, 442), "More ideas and a dinner question in the family quest", font=AGENDA_LABEL, fill=0)
    return to_1bit(img)


def _draw_mountain_panel(draw: ImageDraw.ImageDraw, title: str) -> None:
    x0, y0, x1, y1 = MARGIN, 64, 310, 310
    draw.rectangle([x0, y0, x1, y1], fill=0)
    digest = hashlib.sha256(title.encode()).digest()

    points: list[tuple[int, int]] = [(x0 + 18, y1 - 42)]
    x = x0 + 18
    for index in range(5):
        x += 45 + digest[index] % 10
        peak_y = y0 + 58 + digest[index + 5] % 76
        points.extend([(x - 24, y1 - 42), (x, peak_y), (x + 28, y1 - 42)])
    points.append((x1 - 18, y1 - 42))
    draw.line(points, fill=255, width=3, joint="curve")
    draw.line([(px, min(y1 - 28, py + 32)) for px, py in points], fill=255, width=1)
    draw.ellipse([x1 - 78, y0 + 26, x1 - 36, y0 + 68], outline=255, width=3)
    draw.text((x0 + 20, y1 - 27), "FAMILY EXPEDITION", font=KICKER, fill=255)


def _draw_route(draw: ImageDraw.ImageDraw, route: tuple[str, ...]) -> None:
    y = 350
    x0 = MARGIN + 6
    x1 = WIDTH - MARGIN - 6
    draw.text((MARGIN, 320), "ROUTE", font=KICKER, fill=0)
    draw.line([(x0, y), (x1, y)], fill=0, width=2)
    count = len(route)
    for index, stop in enumerate(route):
        x = x0 if count == 1 else x0 + index * (x1 - x0) // (count - 1)
        draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=0)
        label_w = draw.textlength(stop.upper(), font=META)
        label_x = max(MARGIN, min(WIDTH - MARGIN - label_w, x - label_w / 2))
        draw.text((label_x, y + 14), stop.upper(), font=META, fill=0)


def render_trip(card: TripCard, *, today: date | None = None) -> Image.Image:
    today = today or date.today()
    img, draw = new_canvas()
    draw_kicker(draw, "Focus", right=card.dates.upper())

    delta = (card.starts - today).days
    if delta > 0:
        number = str(delta)
        draw.text((MARGIN, 72), number, font=DISPLAY, fill=0)
        number_w = draw.textlength(number, font=DISPLAY)
        draw.text((MARGIN + number_w + 16, 106), "DAYS TO", font=BODY_BOLD, fill=0)
    elif delta == 0:
        draw.text((MARGIN, 80), "TODAY", font=DISPLAY, fill=0)
    else:
        draw.text((MARGIN, 84), "ON TRIP", font=HEADLINE, fill=0)

    draw.text((MARGIN, 162), card.title.upper(), font=HEADLINE, fill=0)
    draw.text((MARGIN, 220), "NEXT", font=KICKER, fill=0)
    action_text = (card.ready or (card.next_action,))[0]
    action_lines = _text_lines(draw, action_text, HEADLINE, WIDTH - MARGIN * 2, 2)
    _draw_lines(draw, action_lines, x=MARGIN, y=250, f=HEADLINE, line_height=36)

    footer_top = 378
    draw.rectangle([MARGIN, footer_top, WIDTH - MARGIN, 452], fill=0)
    rule = _text_lines(draw, card.rule, BODY_BOLD, WIDTH - MARGIN * 2 - 32, 2)
    _draw_lines(draw, rule, x=MARGIN + 16, y=footer_top + 15, f=BODY_BOLD, fill=255, line_height=27)

    return to_1bit(img)


class QuestProvider:
    name = "quest"

    def __init__(self, path: Path | str, *, omit_unavailable: bool = False):
        self.path = Path(path).expanduser()
        self.omit_unavailable = omit_unavailable

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            if self.omit_unavailable:
                return []
            image = render_notice("Family Quest", "quest source missing", str(self.path))
        else:
            try:
                card = parse_quest(self.path)
                if date.today() > card.valid_until:
                    if self.omit_unavailable:
                        return []
                    image = render_notice("Family Quest", "quest needs a refresh", "choose the next weekly card")
                else:
                    image = render_quest(card)
            except ValueError as exc:
                if self.omit_unavailable:
                    return []
                image = render_notice("Family Quest", "quest source invalid", str(exc))
        return [
            SceneSpec(
                id="family-quest",
                kind="prerendered",
                title="Family Quest",
                priority=90,
                prerendered=image,
            )
        ]


class TripProvider:
    name = "trip"

    def __init__(self, path: Path | str, *, omit_unavailable: bool = False):
        self.path = Path(path).expanduser()
        self.omit_unavailable = omit_unavailable

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            if self.omit_unavailable:
                return []
            image = render_notice("Trip", "trip source missing", str(self.path))
        else:
            try:
                card = parse_trip(self.path)
                if card.valid_until is None or date.today() > card.valid_until:
                    if self.omit_unavailable:
                        return []
                    image = render_notice("Trip", "trip needs a current date", "Add an explicit Valid until date to the display card.")
                elif card.valid_until < card.starts:
                    raise ValueError("trip Valid until precedes Starts")
                else:
                    image = render_trip(card)
            except ValueError as exc:
                if self.omit_unavailable:
                    return []
                image = render_notice("Trip", "trip source invalid", str(exc))
        return [
            SceneSpec(
                id="trip-feature",
                kind="prerendered",
                title="Trip",
                priority=80,
                prerendered=image,
            )
        ]


def _quest_factory(config: Mapping[str, JSONValue]) -> QuestProvider:
    path = config.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("quest provider requires a non-empty 'path'")
    return QuestProvider(path, omit_unavailable=config.get("omit_unavailable", False))


def _trip_factory(config: Mapping[str, JSONValue]) -> TripProvider:
    path = config.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("trip provider requires a non-empty 'path'")
    return TripProvider(path, omit_unavailable=config.get("omit_unavailable", False))


register_provider("quest", _quest_factory)
register_provider("trip", _trip_factory)
