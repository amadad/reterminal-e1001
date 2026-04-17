"""Monochrome scene renderer with dense editorial templates."""

from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import textwrap

import requests

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from reterminal.config import HEIGHT, WIDTH
from reterminal.fonts import load_font, load_mono_font
from reterminal.render.bitmap import generate_bitmap
from reterminal.payloads import JSONValue
from reterminal.render.layout import Rect, TextAlign, VerticalAlign, draw_text_block, fit_text_block
from reterminal.render.theme import DEFAULT_THEME, MonoTheme
from reterminal.scenes import SceneSpec


@dataclass(frozen=True, slots=True)
class SceneFrame:
    outer: Rect
    content: Rect
    footer: Rect


@dataclass(slots=True)
class MonoRenderer:
    """Render logical scenes to 800x480 monochrome bitmaps."""

    theme: MonoTheme = DEFAULT_THEME

    def render(
        self,
        scene: SceneSpec,
        *,
        slot: int | None = None,
        total_slots: int | None = None,
    ) -> Image.Image:
        img = Image.new("L", (WIDTH, HEIGHT), color=255)
        draw = ImageDraw.Draw(img)
        frame = self._build_frame()

        match scene.kind:
            case "hero":
                self._render_hero(draw, scene, frame)
            case "metrics":
                self._render_metrics(draw, scene, frame)
            case "bulletin":
                self._render_bulletin(draw, scene, frame)
            case "poster":
                self._render_poster(img, draw, scene, frame)
            case _:
                self._render_fallback(draw, scene, frame)

        self._draw_footer_bar(draw, scene, frame.footer, slot=slot, total_slots=total_slots)
        finished = ImageOps.autocontrast(img)
        return finished.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

    def _build_frame(self) -> SceneFrame:
        margin = self.theme.outer_margin
        outer = Rect(margin, margin, WIDTH - margin * 2, HEIGHT - margin * 2)
        content, footer = outer.split_bottom(self.theme.footer_height, gap=self.theme.section_gap)
        return SceneFrame(outer=outer, content=content, footer=footer)

    # === Hero: big title, optional metric sidebar, body bullets ===

    def _render_hero(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = frame.content
        content = self._draw_header_band(draw, content, scene)

        header_height = 110 if scene.metric else 130
        header_rect, lower_rect = content.split_top(header_height, gap=self.theme.section_gap)

        if scene.subtitle:
            subtitle_rect, title_rect = header_rect.split_top(22, gap=4)
            self._fit_and_draw(draw, subtitle_rect, scene.subtitle, max_font_size=18, min_font_size=13, max_lines=1)
        else:
            title_rect = header_rect

        self._fit_and_draw(draw, title_rect, scene.title, max_font_size=56, min_font_size=28, max_lines=3, line_spacing=2)
        draw.line((lower_rect.x, lower_rect.y - 4, lower_rect.x + lower_rect.width, lower_rect.y - 4), fill=0, width=1)

        if scene.metric:
            metric_rect, body_rect = lower_rect.split_left(170, gap=self.theme.gutter)
            self._draw_metric_block(draw, metric_rect, scene.metric.label, scene.metric.value, scene.metric.detail)
        else:
            body_rect = lower_rect

        self._draw_body_rows(draw, body_rect, scene.body, max_items=5)

    # === Metrics: dense grid with inverted label headers ===

    def _render_metrics(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = frame.content
        content = self._draw_header_band(draw, content, scene)

        header_rect, grid_rect = content.split_top(36, gap=self.theme.section_gap)
        title_rect, meta_rect = header_rect.split_left(int(header_rect.width * 0.6), gap=self.theme.gutter)

        self._fit_and_draw(draw, title_rect, scene.title.upper(), max_font_size=24, min_font_size=18, max_lines=1)
        if scene.subtitle:
            self._fit_and_draw(draw, meta_rect, scene.subtitle, max_font_size=15, min_font_size=12, max_lines=1, align="right", valign="bottom")

        draw.line((grid_rect.x, grid_rect.y - 4, grid_rect.x + grid_rect.width, grid_rect.y - 4), fill=0, width=1)

        display_metrics = scene.metrics[:6]
        if not display_metrics:
            self._fit_and_draw(draw, grid_rect, "No metrics", max_font_size=20, min_font_size=16, max_lines=1)
            return

        cols = 3 if len(display_metrics) > 4 else 2
        rows = max(1, (len(display_metrics) + cols - 1) // cols)
        for row_rect, row_items in zip(grid_rect.rows(rows, gap=self.theme.gutter), self._chunk(display_metrics, cols)):
            for card_rect, metric in zip(row_rect.columns(len(row_items), gap=self.theme.gutter), row_items):
                self._draw_metric_block(draw, card_rect, metric.label, metric.value, metric.detail)

    # === Bulletin: single-column agenda with time/event rows ===

    def _render_bulletin(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = frame.content
        content = self._draw_header_band(draw, content, scene)

        header_rect, list_rect = content.split_top(40 if scene.subtitle else 32, gap=self.theme.section_gap)

        if scene.subtitle:
            title_rect, subtitle_rect = header_rect.split_top(24, gap=2)
            self._fit_and_draw(draw, title_rect, scene.title.upper(), max_font_size=24, min_font_size=18, max_lines=1)
            self._fit_and_draw(draw, subtitle_rect, scene.subtitle, max_font_size=14, min_font_size=11, max_lines=1)
        else:
            self._fit_and_draw(draw, header_rect, scene.title.upper(), max_font_size=24, min_font_size=18, max_lines=1)

        draw.line((list_rect.x, list_rect.y - 4, list_rect.x + list_rect.width, list_rect.y - 4), fill=0, width=1)

        items = scene.items[:8]
        if not items:
            self._fit_and_draw(draw, list_rect, "No items", max_font_size=18, min_font_size=14, max_lines=1)
            return

        budget = min(len(items), max(1, list_rect.height // 42))
        for row_rect, item in zip(list_rect.rows(budget, gap=4), items[:budget]):
            # Thin separator between rows
            if row_rect.y > list_rect.y + 2:
                draw.line((row_rect.x, row_rect.y - 2, row_rect.x + row_rect.width, row_rect.y - 2), fill=200, width=1)
            self._fit_and_draw(draw, row_rect, item, max_font_size=20, min_font_size=14, max_lines=2, valign="center")

    # === Poster: image with caption overlay ===

    def _render_poster(self, img: Image.Image, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = self._draw_header_band(draw, frame.content, scene)
        image_rect, caption_rect = content.split_bottom(90, gap=self.theme.section_gap)
        art = self._load_art(scene.image_path, image_rect.width, image_rect.height, scene)
        img.paste(art, (image_rect.x, image_rect.y))

        caption_inner = caption_rect.inset(4)
        title_height = 44 if scene.subtitle else caption_inner.height
        title_rect, subtitle_rect = caption_inner.split_top(title_height, gap=4)

        self._fit_and_draw(draw, title_rect, scene.title, max_font_size=28, min_font_size=18, max_lines=2, line_spacing=2)
        if scene.subtitle:
            self._fit_and_draw(draw, subtitle_rect, scene.subtitle, max_font_size=15, min_font_size=11, max_lines=2)

    # === Fallback ===

    def _render_fallback(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = self._draw_header_band(draw, frame.content, scene)
        title_rect, body_rect = content.split_top(80, gap=self.theme.section_gap)
        self._fit_and_draw(draw, title_rect, scene.title, max_font_size=32, min_font_size=20, max_lines=3)
        self._draw_body_rows(draw, body_rect, scene.body or scene.items, max_items=5)

    # === Shared components ===

    def _draw_header_band(self, draw: ImageDraw.ImageDraw, rect: Rect, scene: SceneSpec) -> Rect:
        """Inverted kicker band — white text on black bar. Compact and high-contrast."""
        kicker = self._meta(scene, "kicker") or self._meta(scene, "eyebrow")
        stamp = self._meta(scene, "stamp")
        if not kicker:
            return rect

        band_rect, rest = rect.split_top(self.theme.kicker_height, gap=4)
        # Filled black band
        draw.rectangle((band_rect.x, band_rect.y, band_rect.right, band_rect.bottom), fill=0)
        mono_font = load_mono_font(size=12)
        draw.text((band_rect.x + 6, band_rect.y + 4), str(kicker).upper(), font=mono_font, fill=255)
        if stamp:
            stamp_text = str(stamp)
            bbox = draw.textbbox((0, 0), stamp_text, font=mono_font)
            sx = band_rect.right - (bbox[2] - bbox[0]) - 6
            draw.text((sx, band_rect.y + 4), stamp_text, font=mono_font, fill=255)
        return rest

    def _draw_metric_block(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        label: str,
        value: str,
        detail: str | None,
    ) -> None:
        """Metric card with inverted label header strip and large value."""
        # Inverted label strip at top
        label_height = 20
        label_rect, value_region = rect.split_top(label_height, gap=0)
        draw.rectangle((label_rect.x, label_rect.y, label_rect.right, label_rect.bottom), fill=0)
        mono_font = load_mono_font(size=11)
        draw.text((label_rect.x + 6, label_rect.y + 3), label.upper(), font=mono_font, fill=255)

        # Border around value area
        draw.rectangle((rect.x, label_rect.bottom, rect.right, rect.bottom), outline=0, width=1)
        inner = Rect(rect.x + 6, label_rect.bottom + 4, rect.width - 12, rect.bottom - label_rect.bottom - 8)

        if detail:
            value_rect, detail_rect = inner.split_bottom(14, gap=2)
        else:
            value_rect = inner
            detail_rect = None

        self._fit_and_draw(draw, value_rect, value, max_font_size=32, min_font_size=16, max_lines=2, valign="center")
        if detail_rect:
            self._fit_and_draw(draw, detail_rect, detail, max_font_size=12, min_font_size=10, max_lines=1)

    def _draw_body_rows(self, draw: ImageDraw.ImageDraw, rect: Rect, items: list[str], *, max_items: int) -> None:
        if not items:
            self._fit_and_draw(draw, rect, "No items available", max_font_size=18, min_font_size=14, max_lines=1)
            return

        budget = min(len(items), max_items, max(1, rect.height // 42))
        for row_rect, item in zip(rect.rows(budget, gap=4), items[:budget]):
            # Small dash bullet
            dash_y = row_rect.y + row_rect.height // 2
            draw.line((row_rect.x, dash_y, row_rect.x + 8, dash_y), fill=0, width=2)
            text_rect = Rect(row_rect.x + 14, row_rect.y, row_rect.width - 14, row_rect.height)
            self._fit_and_draw(draw, text_rect, item, max_font_size=18, min_font_size=13, max_lines=2, valign="center")

    def _draw_footer_bar(
        self,
        draw: ImageDraw.ImageDraw,
        scene: SceneSpec,
        rect: Rect,
        *,
        slot: int | None,
        total_slots: int | None,
    ) -> None:
        mono_font = load_mono_font(size=10)
        left_text = self._meta(scene, "footer_left") or scene.footer or scene.kind
        stamp_text = self._meta(scene, "stamp") or self._meta(scene, "footer_center")

        draw.text((rect.x, rect.y + 2), str(left_text)[:60], font=mono_font, fill=0)
        if stamp_text:
            stamp_str = str(stamp_text)
            bbox = draw.textbbox((0, 0), stamp_str, font=mono_font)
            sx = rect.right - (bbox[2] - bbox[0])
            draw.text((sx, rect.y + 2), stamp_str, font=mono_font, fill=0)

    # === Helpers ===

    def _fit_and_draw(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        text: str,
        *,
        max_font_size: int,
        min_font_size: int,
        max_lines: int,
        line_spacing: int = 2,
        align: TextAlign = "left",
        valign: VerticalAlign = "top",
    ) -> None:
        fitted = fit_text_block(
            draw, text, rect,
            max_font_size=max_font_size, min_font_size=min_font_size,
            max_lines=max_lines, line_spacing=line_spacing,
        )
        draw_text_block(draw, rect, fitted, align=align, valign=valign, line_spacing=line_spacing)

    def _load_art(self, path: str | None, width: int, height: int, scene: SceneSpec) -> Image.Image:
        bitmap_spec = scene.meta.get("bitmap") if isinstance(scene.meta, dict) else None
        if path:
            image = Image.open(Path(path)).convert("L")
        elif scene.image_url:
            image = self._download_art(scene.image_url)
            if image is None:
                image = generate_bitmap(bitmap_spec, width, height) if isinstance(bitmap_spec, dict) else self._placeholder_art(width, height, scene)
        elif isinstance(bitmap_spec, dict):
            image = generate_bitmap(bitmap_spec, width, height)
        else:
            image = self._placeholder_art(width, height, scene)

        art = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        art = ImageOps.autocontrast(art)
        art = ImageEnhance.Contrast(art).enhance(1.5)
        return art.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")

    @staticmethod
    def _download_art(url: str) -> Image.Image | None:
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("L")
        except Exception:
            return None

    def _placeholder_art(self, width: int, height: int, scene: SceneSpec) -> Image.Image:
        img = Image.new("L", (width, height), color=240)
        draw = ImageDraw.Draw(img)
        label = str(self._meta(scene, "kicker") or scene.kind).upper()[:12]
        mono_font = load_mono_font(size=14)
        draw.text((12, 12), label, font=mono_font, fill=0)
        return img

    @staticmethod
    def _meta(scene: SceneSpec, key: str) -> JSONValue:
        return scene.meta.get(key)

    @staticmethod
    def _chunk(items: list, size: int) -> list[list]:
        return [items[index : index + size] for index in range(0, len(items), size)]
