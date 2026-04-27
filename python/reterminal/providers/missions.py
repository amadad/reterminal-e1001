"""SceneProvider for the missions slot (slot 1).

Reads ~/madad/family/missions.md and returns a SceneSpec carrying a
prerendered 800x480 1-bit bitmap. The provider owns parsing and layout
end-to-end; MonoRenderer just blits the bitmap.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from reterminal.providers.manifest import register_provider
from reterminal.render.viz import dots, heatmap, progress_bar
from reterminal.scenes import SceneSpec


WIDTH, HEIGHT = 800, 480
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")
DEFAULT_PATH = Path.home() / "madad" / "family" / "missions.md"
KID_ORDER = ("Laila", "Hasan", "Ammar", "Noora")


@dataclass(slots=True)
class Mission:
    who: str
    kind: str = ""
    title: str = ""
    progress: str = ""
    streak: list[int] = field(default_factory=list)
    next_action: str = ""


_KEYVAL = re.compile(r"^([a-z_]+):\s*(.*)$")
_NUM_OF_NUM = re.compile(r"(\d+)\s*/\s*(\d+)")


def parse_missions(path: Path) -> list[Mission]:
    missions: list[Mission] = []
    current: Mission | None = None
    in_active = False
    for raw in path.read_text().splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            in_active = line[3:].strip().lower() == "active"
            continue
        if not in_active:
            continue
        if line.startswith("### "):
            if current:
                missions.append(current)
            current = Mission(who=line[4:].strip())
            continue
        if current is None:
            continue
        m = _KEYVAL.match(line.strip())
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "kind":
            current.kind = val
        elif key == "title":
            current.title = val
        elif key == "progress":
            current.progress = val
        elif key == "streak":
            current.streak = [int(x) for x in val.split() if x in {"0", "1"}]
        elif key == "next":
            current.next_action = val
    if current:
        missions.append(current)
    return missions


def _parse_fraction(s: str) -> tuple[int, int] | None:
    m = _NUM_OF_NUM.search(s)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _parse_days(s: str) -> int | None:
    m = re.search(r"(\d+)\s*days?", s)
    return int(m.group(1)) if m else None


def _font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(HELVETICA), size, index={"regular": 0, "bold": 1}[weight])


def _wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.ImageFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if draw.textlength(candidate, font=f) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _render_quadrant(draw: ImageDraw.ImageDraw, m: Mission, x: int, y: int, w: int, h: int) -> None:
    pad = 20
    cx = x + pad
    top = y + pad
    inner_w = w - pad * 2
    bottom = y + h - pad

    name_f = _font(20, "bold")
    kind_f = _font(13, "bold")
    title_f = _font(30, "bold")
    next_label_f = _font(12, "bold")
    next_f = _font(16)
    meta_f = _font(14)

    draw.text((cx, top), m.who.upper(), font=name_f, fill=0)
    kind_label = m.kind.upper()
    kw = draw.textlength(kind_label, font=kind_f)
    draw.text((cx + inner_w - kw, top + 4), kind_label, font=kind_f, fill=0)

    title_y = top + 32
    title_lines = _wrap(draw, m.title, title_f, inner_w)[:1]
    for line in title_lines:
        draw.text((cx, title_y), line, font=title_f, fill=0)
        title_y += 38

    next_lines = _wrap(draw, m.next_action, next_f, inner_w)[:2]
    next_block_h = 18 + 19 * len(next_lines)
    next_top = bottom - next_block_h
    draw.text((cx, next_top), "NEXT", font=next_label_f, fill=0)
    line_y = next_top + 18
    for line in next_lines:
        draw.text((cx, line_y), line, font=next_f, fill=0)
        line_y += 19

    viz_top = title_y + 4
    viz_bottom = next_top - 10

    if m.kind == "project":
        frac = _parse_fraction(m.progress)
        if frac:
            value, total = frac
            bar_y = viz_top + 6
            progress_bar(draw, cx, bar_y, inner_w, 18, value=value, total=total, segments=total, gap=4)
            draw.text((cx, bar_y + 26), f"{value} of {total} weeks", font=meta_f, fill=0)
    elif m.kind == "habit":
        days = _parse_days(m.progress) or 0
        if m.streak:
            series = m.streak
        elif days > 0:
            series = [1] * days
        else:
            series = [0] * 30
        cols = 10
        rows = (len(series) + cols - 1) // cols
        avail_h = viz_bottom - viz_top
        cell = 14
        gap = 3
        grid_h = rows * cell + (rows - 1) * gap
        if grid_h + 20 > avail_h:
            cell = max(8, (avail_h - 20 - (rows - 1) * gap) // rows)
        max_cell_w = (inner_w - (cols - 1) * gap) // cols
        cell = min(cell, max_cell_w)
        heatmap(draw, cx, viz_top, series, cols=cols, cell=cell, gap=gap)
        grid_right = cx + cols * cell + (cols - 1) * gap
        streak_big = _font(28, "bold")
        draw.text((grid_right + 14, viz_top - 2), str(days), font=streak_big, fill=0)
        draw.text((grid_right + 14, viz_top + 28), "day streak", font=meta_f, fill=0)
    elif m.kind == "milestone":
        frac = _parse_fraction(m.progress)
        if frac:
            value, total = frac
            dots(draw, cx, viz_top + 4, filled=value, total=total, size=18, gap=10)
            draw.text((cx, viz_top + 32), f"{value} of {total}", font=meta_f, fill=0)
    elif m.kind == "goal":
        frac = _parse_fraction(m.progress)
        if frac:
            value, total = frac
            progress_bar(draw, cx, viz_top + 6, inner_w, 14, value=value, total=total)
            draw.text((cx, viz_top + 28), f"{value} / {total}", font=meta_f, fill=0)


def render_missions(missions: list[Mission]) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    draw.text((24, 14), "MISSIONS", font=_font(13, "bold"), fill=0)

    grid_top = 38
    grid_h = HEIGHT - grid_top
    grid_w = WIDTH
    cell_w = grid_w // 2
    cell_h = grid_h // 2

    mid_x = grid_w // 2
    mid_y = grid_top + grid_h // 2
    draw.line([(mid_x, grid_top + 10), (mid_x, HEIGHT - 10)], fill=0, width=1)
    draw.line([(20, mid_y), (WIDTH - 20, mid_y)], fill=0, width=1)

    by_name = {m.who: m for m in missions}
    for i, name in enumerate(KID_ORDER):
        m = by_name.get(name)
        if m is None:
            continue
        row, col = divmod(i, 2)
        qx = col * cell_w
        qy = grid_top + row * cell_h
        _render_quadrant(draw, m, qx, qy, cell_w, cell_h)

    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")


class MissionsProvider:
    name = "missions"

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path).expanduser()

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            return []
        missions = parse_missions(self.path)
        image = render_missions(missions)
        return [
            SceneSpec(
                id="missions",
                kind="prerendered",
                title="Missions",
                priority=90,
                preferred_slot=1,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, Any]) -> MissionsProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return MissionsProvider(path=path)


register_provider("missions", _factory)
