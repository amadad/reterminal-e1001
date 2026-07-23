"""Tests for the summer-camp table parser + provider."""

from __future__ import annotations

import os
from pathlib import Path

from reterminal.encoding import pil_to_raw
from reterminal.family.camps import parse_camps
from reterminal.providers.camps import CampsProvider

TABLE = """\
| Week   | Ammar + Hasan (together) | Laila     | Notes     |
| ------ | ------------------------ | --------- | --------- |
| Jun 29 | 🏖️ Maryland              | —         |           |
| Jul 06 | CoderSchool: Indy 3D 🏎️  | Camp Rock | $649 × 2  |
| Aug 31 | ✈️ Family Trip           |           |           |
"""


def test_parse_camps_reads_three_columns_and_drops_costs(tmp_path: Path):
    md = tmp_path / "camps.md"
    md.write_text(TABLE)
    camps = parse_camps(md)

    assert len(camps) == 3  # header + separator skipped
    assert camps[0].week == "Jun 29"
    assert camps[0].boys == "🏖️ Maryland"  # parser keeps emoji; renderer strips
    assert camps[0].laila == "—"
    assert camps[1].boys == "CoderSchool: Indy 3D 🏎️"
    # The Notes/cost column is never surfaced as a Camp field.
    assert not any("649" in (c.boys + c.laila) for c in camps)


def test_parse_camps_skips_separator_and_blank_weeks(tmp_path: Path):
    md = tmp_path / "camps.md"
    md.write_text("| Week | A | B |\n|---|:--:|---|\n|  |  |  |\n| Jul 06 | x | y |\n")
    camps = parse_camps(md)
    assert [c.week for c in camps] == ["Jul 06"]


def test_camps_provider_bitmap_does_not_depend_on_file_mtime(tmp_path: Path):
    path = tmp_path / "camps.md"
    path.write_text(TABLE)
    provider = CampsProvider(path=path)
    first = provider.fetch()[0].prerendered
    os.utime(path, (2_000_000_000, 2_000_000_000))
    second = provider.fetch()[0].prerendered

    assert first is not None and second is not None
    assert pil_to_raw(first) == pil_to_raw(second)


def test_camps_provider_missing_source_renders_notice(tmp_path: Path):
    provider = CampsProvider(path=tmp_path / "nope.md")
    scenes = provider.fetch()
    assert len(scenes) == 1
    assert scenes[0].prerendered is not None  # "camps source missing" notice
