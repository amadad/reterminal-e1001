"""Tests for the photo SceneProvider."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from reterminal.providers.photos import (
    PhotoProvider,
    _list_photos,
    _select_photo,
    render_photo,
)


WIDTH, HEIGHT = 800, 480


def _write_photo(path: Path, *, size: tuple[int, int] = (1200, 800), color: int = 128) -> Path:
    img = Image.new("L", size, color=color)
    img.save(path, format="JPEG")
    return path


def test_provider_returns_full_bleed_bitmap(tmp_path: Path):
    folder = tmp_path / "photos"
    folder.mkdir()
    _write_photo(folder / "shot.jpg")
    scenes = PhotoProvider(folder=folder).fetch()
    assert len(scenes) == 1
    s = scenes[0]
    assert s.id == "photo"
    assert s.kind == "prerendered"
    assert s.prerendered is not None
    assert s.prerendered.size == (WIDTH, HEIGHT)
    assert s.prerendered.mode == "1"


def test_provider_renders_notice_when_folder_is_empty(tmp_path: Path):
    folder = tmp_path / "empty"
    folder.mkdir()
    scenes = PhotoProvider(folder=folder).fetch()
    s = scenes[0]
    assert s.prerendered.size == (WIDTH, HEIGHT)
    assert s.prerendered.mode == "1"


def test_provider_renders_notice_when_folder_missing(tmp_path: Path):
    scenes = PhotoProvider(folder=tmp_path / "nope").fetch()
    s = scenes[0]
    assert s.prerendered.size == (WIDTH, HEIGHT)
    assert s.prerendered.mode == "1"


def test_newest_mode_picks_most_recently_modified(tmp_path: Path):
    folder = tmp_path / "photos"
    folder.mkdir()
    older = _write_photo(folder / "old.jpg", color=64)
    newer = _write_photo(folder / "new.jpg", color=192)
    # Bump newer's mtime explicitly.
    now = time.time()
    older.touch()
    import os
    os.utime(older, (now - 60, now - 60))
    os.utime(newer, (now, now))
    selected = _select_photo(folder, mode="newest")
    assert selected == newer


def test_daily_mode_is_deterministic_per_day(tmp_path: Path):
    folder = tmp_path / "photos"
    folder.mkdir()
    a = _write_photo(folder / "a.jpg")
    b = _write_photo(folder / "b.jpg")
    c = _write_photo(folder / "c.jpg")
    sorted_photos = sorted([a, b, c])
    # Three different days should map to three different photos in sorted order.
    chosen = {_select_photo(folder, "daily", today=date(2026, 1, 1 + i)) for i in range(3)}
    assert chosen == set(sorted_photos)


def test_caption_sidecar_is_rendered(tmp_path: Path):
    folder = tmp_path / "photos"
    folder.mkdir()
    photo = _write_photo(folder / "shot.jpg")
    photo.with_suffix(".txt").write_text("Saturday at the lake")
    image = render_photo(photo)
    assert image.size == (WIDTH, HEIGHT)
    assert image.mode == "1"


def test_unknown_mode_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown mode"):
        PhotoProvider(folder=tmp_path, mode="random")


def test_factory_via_manifest_registry(tmp_path: Path):
    """Verify the provider is registered as type 'photo' in the manifest."""
    import reterminal.providers  # noqa: F401  triggers registration
    from reterminal.providers.manifest import build_providers, FeedManifest, ProviderEntry

    folder = tmp_path / "photos"
    folder.mkdir()
    _write_photo(folder / "shot.jpg")

    manifest = FeedManifest(providers=[
        ProviderEntry(type="photo", config={"path": str(folder), "mode": "newest"}, slot=3),
    ])
    providers = build_providers(manifest)
    assert len(providers) == 1
    scenes = providers[0].fetch()
    assert len(scenes) == 1
    assert scenes[0].preferred_slot == 3


def test_list_photos_finds_all_extensions(tmp_path: Path):
    folder = tmp_path / "photos"
    folder.mkdir()
    a = _write_photo(folder / "one.jpg")
    b = _write_photo(folder / "two.jpeg")
    Image.new("L", (200, 200)).save(folder / "three.png", format="PNG")
    c = folder / "three.png"
    found = sorted(_list_photos(folder))
    assert set(found) >= {a, b, c}
