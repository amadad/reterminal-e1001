"""Renderer + SceneProvider for the missions kitchen page.

Parses `missions.md` via `reterminal.family.missions.parse_missions` and
returns a SceneSpec carrying a prerendered 800x480 1-bit bitmap. Slot
pinning is owned by the provider manifest; MonoRenderer just blits the
bitmap.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from reterminal.family.missions import (
    DEFAULT_PATH,
    Mission,
    parse_days,
    parse_fraction,
    parse_missions,
)
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import (
    HEIGHT,
    WIDTH,
    draw_source_stamp,
    font,
    render_notice,
    to_1bit,
)
from reterminal.render.viz import dots, heatmap, progress_bar
from reterminal.scenes import SceneSpec


DEFAULT_MISSION_ORDER: tuple[str, ...] = ()


def _wrap(draw: ImageDraw.ImageDraw, text: str, f, max_w: int) -> list[str]:
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

    name_f = font(20, "bold")
    kind_f = font(13, "bold")
    title_f = font(30, "bold")
    next_label_f = font(12, "bold")
    next_f = font(16)
    meta_f = font(14)

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
        frac = parse_fraction(m.progress)
        if frac:
            value, total = frac
            bar_y = viz_top + 6
            progress_bar(draw, cx, bar_y, inner_w, 18, value=value, total=total, segments=total, gap=4)
            draw.text((cx, bar_y + 26), f"{value} of {total} weeks", font=meta_f, fill=0)
    elif m.kind == "habit":
        days = parse_days(m.progress) or 0
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
        streak_big = font(28, "bold")
        draw.text((grid_right + 14, viz_top - 2), str(days), font=streak_big, fill=0)
        draw.text((grid_right + 14, viz_top + 28), "day streak", font=meta_f, fill=0)
    elif m.kind == "milestone":
        frac = parse_fraction(m.progress)
        if frac:
            value, total = frac
            dots(draw, cx, viz_top + 4, filled=value, total=total, size=18, gap=10)
            draw.text((cx, viz_top + 32), f"{value} of {total}", font=meta_f, fill=0)
    elif m.kind == "goal":
        frac = parse_fraction(m.progress)
        if frac:
            value, total = frac
            progress_bar(draw, cx, viz_top + 6, inner_w, 14, value=value, total=total)
            draw.text((cx, viz_top + 28), f"{value} / {total}", font=meta_f, fill=0)


def _ordered_missions(missions: list[Mission], order: tuple[str, ...] | None = None) -> list[Mission]:
    if not order:
        return missions[:4]
    by_name = {m.who: m for m in missions}
    ordered = [by_name[name] for name in order if name in by_name]
    seen = {m.who for m in ordered}
    ordered.extend(m for m in missions if m.who not in seen)
    return ordered[:4]


def render_missions(
    missions: list[Mission],
    *,
    source_path: Path | None = None,
    order: tuple[str, ...] | None = None,
) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"
    draw.text((24, 14), "MISSIONS", font=font(13, "bold"), fill=0)

    grid_top = 38
    grid_h = HEIGHT - grid_top
    grid_w = WIDTH
    cell_w = grid_w // 2
    cell_h = grid_h // 2

    mid_x = grid_w // 2
    mid_y = grid_top + grid_h // 2
    draw.line([(mid_x, grid_top + 10), (mid_x, HEIGHT - 10)], fill=0, width=1)
    draw.line([(20, mid_y), (WIDTH - 20, mid_y)], fill=0, width=1)

    for i, m in enumerate(_ordered_missions(missions, order)):
        row, col = divmod(i, 2)
        qx = col * cell_w
        qy = grid_top + row * cell_h
        _render_quadrant(draw, m, qx, qy, cell_w, cell_h)

    draw_source_stamp(draw, source_path, stale_after=timedelta(days=3))
    return to_1bit(img)


class MissionsProvider:
    name = "missions"

    def __init__(self, path: Path | str = DEFAULT_PATH, order: tuple[str, ...] | list[str] | None = None):
        self.path = Path(path).expanduser()
        self.order = tuple(order or DEFAULT_MISSION_ORDER)

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            image = render_notice("Missions", "missions source missing", str(self.path))
        else:
            missions = parse_missions(self.path)
            image = render_missions(missions, source_path=self.path, order=self.order)
        return [
            SceneSpec(
                id="missions",
                kind="prerendered",
                title="Missions",
                priority=90,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, Any]) -> MissionsProvider:
    path = config.get("path", str(DEFAULT_PATH))
    order = config.get("order")
    if isinstance(order, str):
        order = [item.strip() for item in order.split(",") if item.strip()]
    elif not isinstance(order, (list, tuple)):
        order = None
    return MissionsProvider(path=path, order=order)


register_provider("missions", _factory)
