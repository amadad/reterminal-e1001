"""Renderer + SceneProvider for a full-bleed photo slot.

Watches a folder of images, picks one (newest-by-mtime or daily-deterministic),
Floyd-Steinberg dithers it to fill the 800x480 panel, and optionally surfaces
a caption from a sidecar `.txt` next to the image (e.g. `family.jpg` +
`family.txt`).

Manifest example:

    {"type": "photo", "path": "~/madad/photos/wall", "slot": 3, "mode": "daily"}

Selection modes:

- `newest`  — newest file by mtime (default). Drop a photo in, it shows.
- `daily`   — deterministic by date; same photo all day, rotates at midnight.
              Useful when you have a curated folder and want a daily wall.

Notes on the medium: 1-bit ePaper at 800x480 turns most photos into
dot-matrix mush. What survives Floyd-Steinberg well: high-contrast portraits,
strong silhouettes, line art, and B&W photography. Phone snapshots and busy
color images do not. Curating the source folder matters more than the
renderer.

FSEvents caveat: the live publisher's path watcher fires on file paths
declared in the manifest. When `path` is a folder, individual file
add/remove events do not currently re-trigger immediately; the 5-min
sanity tick will catch new photos. To force an immediate update, `touch`
the folder itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from reterminal.payloads import JSONValue
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import (
    HEIGHT,
    WIDTH,
    font,
    render_notice,
    to_1bit,
)
from reterminal.scenes import SceneSpec


PHOTO_EXTS: tuple[str, ...] = ("jpg", "jpeg", "png")
CAPTION_STRIP_HEIGHT = 60
EPOCH = date(2026, 1, 1)


def _list_photos(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    photos: list[Path] = []
    for ext in PHOTO_EXTS:
        photos.extend(folder.glob(f"*.{ext}"))
        photos.extend(folder.glob(f"*.{ext.upper()}"))
    return photos


def _select_photo(folder: Path, mode: str, today: date | None = None) -> Path | None:
    photos = _list_photos(folder)
    if not photos:
        return None
    if mode == "daily":
        sorted_photos = sorted(photos)
        idx = ((today or date.today()) - EPOCH).days % len(sorted_photos)
        return sorted_photos[idx]
    # default: newest-by-mtime
    return max(photos, key=lambda p: p.stat().st_mtime)


def _read_caption(photo: Path) -> str | None:
    sidecar = photo.with_suffix(".txt")
    if not sidecar.exists():
        return None
    text = sidecar.read_text().strip()
    return text or None


def _dither_full_bleed(path: Path, *, target_w: int, target_h: int) -> Image.Image:
    """Cover-fit a photo into target size, then Floyd-Steinberg to 1-bit."""
    src = Image.open(path).convert("L")
    src = ImageOps.exif_transpose(src)
    src_ratio = src.width / src.height
    tgt_ratio = target_w / target_h
    if src_ratio > tgt_ratio:
        h = target_h
        w = int(h * src_ratio)
    else:
        w = target_w
        h = int(w / src_ratio)
    src = src.resize((w, h), Image.LANCZOS)
    left = (w - target_w) // 2
    top = (h - target_h) // 2
    src = src.crop((left, top, left + target_w, top + target_h))
    src = ImageOps.autocontrast(src, cutoff=2)
    src = ImageEnhance.Brightness(src).enhance(1.10)
    src = ImageEnhance.Contrast(src).enhance(1.5)
    return src.convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def render_photo(photo: Path) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    caption = _read_caption(photo)

    if caption:
        photo_h = HEIGHT - CAPTION_STRIP_HEIGHT
        dithered = _dither_full_bleed(photo, target_w=WIDTH, target_h=photo_h)
        img.paste(dithered, (0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, photo_h, WIDTH, HEIGHT], fill=255)
        draw.line([(0, photo_h), (WIDTH, photo_h)], fill=0, width=1)
        caption_f = font(22, "bold")
        text = caption
        while draw.textlength(text, font=caption_f) > WIDTH - 48 and len(text) > 4:
            text = text[:-2] + "…"
        draw.text((24, photo_h + 18), text, font=caption_f, fill=0)
    else:
        dithered = _dither_full_bleed(photo, target_w=WIDTH, target_h=HEIGHT)
        img.paste(dithered, (0, 0))

    return to_1bit(img)


class PhotoProvider:
    name = "photo"

    def __init__(self, folder: Path | str, mode: str = "newest"):
        self.folder = Path(folder).expanduser()
        if mode not in {"newest", "daily"}:
            raise ValueError(f"photo provider: unknown mode {mode!r} (expected 'newest' or 'daily')")
        self.mode = mode

    def fetch(self) -> list[SceneSpec]:
        photo = _select_photo(self.folder, self.mode)
        if photo is None:
            image = render_notice("Photo", "no photos in folder", str(self.folder))
        else:
            image = render_photo(photo)
        return [
            SceneSpec(
                id="photo",
                kind="prerendered",
                title="Photo",
                priority=70,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, JSONValue]) -> PhotoProvider:
    folder = config.get("path") or config.get("folder")
    if not isinstance(folder, str):
        raise ValueError("photo provider requires 'path' (folder string) in config")
    mode = config.get("mode", "newest")
    if not isinstance(mode, str):
        raise ValueError("photo provider 'mode' must be a string")
    return PhotoProvider(folder=folder, mode=mode)


register_provider("photo", _factory)
