"""Render the missions slot (slot 1) as a 2x2 quadrant grid.

One quadrant per kid. Each quadrant uses a visualization primitive from
reterminal.render.viz chosen by mission kind.

Run:
    uv run python examples/preview_missions.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reterminal.render.viz import dots, heatmap, progress_bar

WIDTH, HEIGHT = 800, 480
OUT_DIR = Path("/tmp/reterminal-review")
MISSIONS_FILE = Path.home() / "madad" / "family" / "missions.md"
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(HELVETICA), size, index={"regular": 0, "bold": 1}[weight])


# ---- parsing ----

@dataclass
class Mission:
    who: str
    kind: str = ""
    title: str = ""
    progress: str = ""
    streak: list[int] = field(default_factory=list)
    next_action: str = ""


KEYVAL = re.compile(r"^([a-z_]+):\s*(.*)$")


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
        m = KEYVAL.match(line.strip())
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


# ---- progress parsing helpers ----

NUM_OF_NUM = re.compile(r"(\d+)\s*/\s*(\d+)")


def parse_fraction(s: str) -> tuple[int, int] | None:
    m = NUM_OF_NUM.search(s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_days(s: str) -> int | None:
    m = re.search(r"(\d+)\s*days?", s)
    return int(m.group(1)) if m else None


# ---- rendering ----

def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
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


def render_quadrant(
    draw: ImageDraw.ImageDraw,
    m: Mission,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
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

    # --- anchored to top: name, kind, title ---
    draw.text((cx, top), m.who.upper(), font=name_f, fill=0)
    kind_label = m.kind.upper()
    kw = draw.textlength(kind_label, font=kind_f)
    draw.text((cx + inner_w - kw, top + 4), kind_label, font=kind_f, fill=0)

    title_y = top + 32
    title_lines = wrap(draw, m.title, title_f, inner_w)[:1]
    for line in title_lines:
        draw.text((cx, title_y), line, font=title_f, fill=0)
        title_y += 38

    # --- anchored to bottom: NEXT block (two lines max) ---
    next_lines = wrap(draw, m.next_action, next_f, inner_w)[:2]
    next_block_h = 18 + 19 * len(next_lines)
    next_top = bottom - next_block_h
    draw.text((cx, next_top), "NEXT", font=next_label_f, fill=0)
    line_y = next_top + 18
    for line in next_lines:
        draw.text((cx, line_y), line, font=next_f, fill=0)
        line_y += 19

    # --- viz fills the space between title end and NEXT block ---
    viz_top = title_y + 4
    viz_bottom = next_top - 10

    if m.kind == "project":
        frac = parse_fraction(m.progress)
        if frac:
            value, total = frac
            bar_y = viz_top + 6
            progress_bar(
                draw, cx, bar_y, inner_w, 18,
                value=value, total=total, segments=total, gap=4,
            )
            draw.text(
                (cx, bar_y + 26),
                f"{value} of {total} weeks",
                font=meta_f,
                fill=0,
            )
    elif m.kind == "habit":
        days = parse_days(m.progress) or 0
        if m.streak:
            series = m.streak
        elif days > 0:
            series = [1] * days
        else:
            # Fresh habit — 30 empty cells, inviting the first fill
            series = [0] * 30
        cols = 10
        rows = (len(series) + cols - 1) // cols
        avail_h = viz_bottom - viz_top
        # Target cell 14; shrink if vertical is tight, leaving ~20px for label
        cell = 14
        gap = 3
        grid_h = rows * cell + (rows - 1) * gap
        if grid_h + 20 > avail_h:
            cell = max(8, (avail_h - 20 - (rows - 1) * gap) // rows)
            grid_h = rows * cell + (rows - 1) * gap
        # Also respect inner_w
        max_cell_w = (inner_w - (cols - 1) * gap) // cols
        cell = min(cell, max_cell_w)
        grid_h = rows * cell + (rows - 1) * gap
        heatmap(draw, cx, viz_top, series, cols=cols, cell=cell, gap=gap)
        # Streak count big, to the right of the grid
        grid_right = cx + cols * cell + (cols - 1) * gap
        streak_big = font(28, "bold")
        streak_text = f"{days}"
        if days is not None:
            draw.text((grid_right + 14, viz_top - 2), streak_text, font=streak_big, fill=0)
            draw.text(
                (grid_right + 14, viz_top + 28),
                "day streak" if days != 1 else "day streak",
                font=meta_f,
                fill=0,
            )
    elif m.kind == "milestone":
        frac = parse_fraction(m.progress)
        if frac:
            value, total = frac
            dots(draw, cx, viz_top + 4, filled=value, total=total, size=18, gap=10)
            draw.text(
                (cx, viz_top + 32),
                f"{value} of {total}",
                font=meta_f,
                fill=0,
            )
    elif m.kind == "goal":
        frac = parse_fraction(m.progress)
        if frac:
            value, total = frac
            progress_bar(draw, cx, viz_top + 6, inner_w, 14, value=value, total=total)
            draw.text(
                (cx, viz_top + 28),
                f"{value} / {total}",
                font=meta_f,
                fill=0,
            )


def render(missions: list[Mission]) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)

    # Top kicker
    draw.text((24, 14), "MISSIONS", font=font(13, "bold"), fill=0)

    # 2x2 grid, starting below the kicker
    grid_top = 38
    grid_h = HEIGHT - grid_top
    grid_w = WIDTH
    cell_w = grid_w // 2
    cell_h = grid_h // 2

    # Dividing rules
    mid_x = grid_w // 2
    mid_y = grid_top + grid_h // 2
    draw.line([(mid_x, grid_top + 10), (mid_x, HEIGHT - 10)], fill=0, width=1)
    draw.line([(20, mid_y), (WIDTH - 20, mid_y)], fill=0, width=1)

    # Render each mission in its quadrant; fixed order by household
    order = ["Laila", "Hasan", "Ammar", "Noora"]
    by_name = {m.who: m for m in missions}
    for i, name in enumerate(order):
        m = by_name.get(name)
        if m is None:
            continue
        row, col = divmod(i, 2)
        qx = col * cell_w
        qy = grid_top + row * cell_h
        render_quadrant(draw, m, qx, qy, cell_w, cell_h)

    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    missions = parse_missions(MISSIONS_FILE)
    out = OUT_DIR / "slot-1-missions.png"
    render(missions).save(out)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
