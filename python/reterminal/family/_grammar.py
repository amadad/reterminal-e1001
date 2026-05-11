"""Shared regex grammar primitives for the family-state markdown parsers.

`events.md` and `activities.md` share the same `- YYYY-MM-DD Label [tag]` line
shape, so the ISO-date and trailing-tag patterns live here once. Calendar uses a
different per-section date convention (`## YYYY-MM-DD` headers, no per-line
date), so it owns its own grammar in `family.calendar`.
"""

from __future__ import annotations

import re

ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(.*)$")
TAG_RE = re.compile(r"\[([^\]]+)\]\s*$")
