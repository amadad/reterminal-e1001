"""Per-provider lint for the markdown sources feeding the kitchen display.

The four parsers (`calendar`, `missions`, `events`, `activities`) silently
drop lines they don't understand: a typo like `3:00pmm` in `calendar.md`
just doesn't appear on the display, with no error anywhere. That's fine for
the renderer (we'd rather show a stale-but-clean board than crash on a
typo) but it makes authoring brittle — you only notice when you look at
the panel and the line you typed isn't there.

`reterminal lint` re-walks each file, identifies the rendered section, and
reports lines that fail the parser's grammar. Each issue is structured so
the CLI can render a table or emit JSON.

The intent is conservative: we only flag lines that *should* have parsed.
Blank lines, comments, headings, and content under non-rendered sections
(like `## Notes`) are not issues.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from reterminal.family.activities import ISO_DATE as ACTIVITY_ISO_DATE
from reterminal.family.activities import TAG_RE as ACTIVITY_TAG_RE
from reterminal.family.calendar import TIME_RE, WHO_RE
from reterminal.family.events import ISO_DATE as EVENT_ISO_DATE
from reterminal.family.events import TAG_RE as EVENT_TAG_RE
from reterminal.family.missions import _KEYVAL


_MISSION_KEYS = {"kind", "title", "progress", "streak", "next"}
_MISSION_KINDS = {"project", "habit", "goal", "milestone"}


@dataclass(frozen=True)
class LintIssue:
    file: str
    line: int
    raw: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _strip_inline_paren(body: str) -> str:
    """Calendar labels often end with `(Ammar)` — drop trailing parens for time match."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", body).strip()


def lint_calendar(path: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    section: str | None = None
    for i, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if line.startswith("## "):
            name = line[3:].strip().lower()
            section = name if name in {"today", "tomorrow"} else None
            continue
        if section is None or not line:
            continue
        if not line.startswith("- "):
            # In a rendered section, non-bullet content is suspicious
            issues.append(LintIssue(str(path), i, raw, "expected `- ` bullet"))
            continue
        body = line[2:].strip()
        if not body:
            issues.append(LintIssue(str(path), i, raw, "empty bullet"))
            continue
        m_who = WHO_RE.search(body)
        if m_who:
            body = body[: m_who.start()].strip()
        body = _strip_inline_paren(body)
        if not TIME_RE.match(body):
            issues.append(
                LintIssue(str(path), i, raw, "missing/invalid time prefix (HH:MM[am|pm])")
            )
    return issues


def lint_events(path: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    in_section = False
    for i, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if line.startswith("## "):
            in_section = line[3:].strip().lower() == "upcoming"
            continue
        if not in_section or not line:
            continue
        if not line.startswith("- "):
            issues.append(LintIssue(str(path), i, raw, "expected `- ` bullet"))
            continue
        body = line[2:].strip()
        m_tag = EVENT_TAG_RE.search(body)
        if m_tag:
            body = body[: m_tag.start()].strip()
        if not EVENT_ISO_DATE.match(body):
            issues.append(LintIssue(str(path), i, raw, "missing/invalid ISO date (YYYY-MM-DD)"))
    return issues


def lint_activities(path: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    section: str | None = None
    for i, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if line.startswith("## "):
            name = line[3:].strip().lower()
            section = name if name in {"recent", "queue"} else None
            continue
        if section is None or not line:
            continue
        if not line.startswith("- "):
            issues.append(LintIssue(str(path), i, raw, "expected `- ` bullet"))
            continue
        body = line[2:].strip()
        if not body:
            issues.append(LintIssue(str(path), i, raw, "empty bullet"))
            continue
        m_tag = ACTIVITY_TAG_RE.search(body)
        if m_tag:
            body = body[: m_tag.start()].strip()
        if section == "recent" and not ACTIVITY_ISO_DATE.match(body):
            # Queue items don't require a date, but recent should be dated
            issues.append(
                LintIssue(str(path), i, raw, "recent items require ISO date (YYYY-MM-DD)")
            )
    return issues


def lint_missions(path: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    in_active = False
    have_current = False
    seen_keys: set[str] = set()
    current_who: str | None = None
    current_line: int | None = None
    current_kind: str | None = None

    def _flush(who: str | None, line_no: int | None, kind: str | None) -> None:
        if who is None or line_no is None:
            return
        missing = sorted({"kind", "title", "progress", "next"} - seen_keys)
        if missing:
            issues.append(
                LintIssue(str(path), line_no, f"### {who}", f"missing required keys: {', '.join(missing)}")
            )
        if kind and kind not in _MISSION_KINDS:
            issues.append(
                LintIssue(
                    str(path),
                    line_no,
                    f"### {who}",
                    f"unknown kind {kind!r}; expected one of {sorted(_MISSION_KINDS)}",
                )
            )

    for i, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.rstrip()
        if line.startswith("## "):
            if in_active:
                _flush(current_who, current_line, current_kind)
            in_active = line[3:].strip().lower() == "active"
            current_who = None
            current_line = None
            current_kind = None
            seen_keys = set()
            have_current = False
            continue
        if not in_active:
            continue
        if line.startswith("### "):
            if have_current:
                _flush(current_who, current_line, current_kind)
            current_who = line[4:].strip()
            current_line = i
            current_kind = None
            seen_keys = set()
            have_current = True
            continue
        if not line.strip():
            continue
        if not have_current:
            issues.append(LintIssue(str(path), i, raw, "content before any `### Name` heading"))
            continue
        m = _KEYVAL.match(line.strip())
        if not m:
            issues.append(LintIssue(str(path), i, raw, "expected `key: value` line"))
            continue
        key = m.group(1)
        if key not in _MISSION_KEYS:
            issues.append(
                LintIssue(str(path), i, raw, f"unknown key {key!r}; expected one of {sorted(_MISSION_KEYS)}")
            )
            continue
        seen_keys.add(key)
        if key == "kind":
            current_kind = m.group(2).strip()
    if in_active:
        _flush(current_who, current_line, current_kind)
    return issues


LINTERS: dict[str, Callable[[Path], list[LintIssue]]] = {
    "calendar": lint_calendar,
    "missions": lint_missions,
    "events": lint_events,
    "activities": lint_activities,
}


def lint_manifest_files(provider_specs: list[tuple[str, Path]]) -> list[LintIssue]:
    """Lint a list of `(type, path)` pairs, skipping types with no linter."""
    issues: list[LintIssue] = []
    for type_name, path in provider_specs:
        linter = LINTERS.get(type_name)
        if linter is None:
            continue
        if not path.exists():
            issues.append(LintIssue(str(path), 0, "", "source file missing"))
            continue
        issues.extend(linter(path))
    return issues
