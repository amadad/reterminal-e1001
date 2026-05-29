"""Parser for a summer-camp markdown table (e.g. the Madad Wiki
`family-summer-2026-camps.md`).

The source is a GitHub-flavored markdown table whose first three columns are
week, the boys' (together) activity, and Laila's activity. A trailing Notes
column carries private cost info and is intentionally dropped here — it must
never reach a shared kitchen wall.

    | Week   | Ammar + Hasan (together) | Laila     | Notes     |
    | ------ | ------------------------ | --------- | --------- |
    | Jul 06 | CoderSchool: Indy 3D     | Camp Rock | $649 ...  |

The parser is pure and tolerant: non-table lines, the header row, and the
`---` separator are skipped; emoji are left intact (the renderer strips them).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_PATH = Path.home() / "reterminal-content" / "family" / "summer-camps.md"

__all__ = ["DEFAULT_PATH", "Camp", "parse_camps"]


@dataclass(frozen=True)
class Camp:
    week: str
    boys: str
    laila: str


def _cells(line: str) -> list[str]:
    # Drop the empty strings produced by the leading/trailing pipes.
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_camps(path: Path) -> list[Camp]:
    camps: list[Camp] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        if not cells or not cells[0]:
            continue
        week = cells[0]
        # Skip the header row and the |---| separator.
        if week.lower() == "week" or set(week) <= {"-", ":"}:
            continue
        boys = cells[1] if len(cells) > 1 else ""
        laila = cells[2] if len(cells) > 2 else ""
        camps.append(Camp(week=week, boys=boys, laila=laila))
    return camps
