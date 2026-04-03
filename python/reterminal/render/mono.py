"""Monochrome scene renderer with measurement-aware editorial templates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import textwrap
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from reterminal.config import HEIGHT, WIDTH
from reterminal.fonts import load_mono_font
from reterminal.render.bitmap import generate_bitmap
from reterminal.render.layout import Rect, draw_text_block, fit_text_block
from reterminal.render.theme import DEFAULT_THEME, MonoTheme
from reterminal.scenes import SceneSpec


@dataclass(frozen=True, slots=True)
class SceneFrame:
    outer: Rect
    content: Rect
    footer: Rect


@dataclass(slots=True)
class MonoRenderer:
    """Render logical scenes to 800x480 monochrome bitmaps.

    The renderer uses editorial templates with explicit chrome regions so:

    - footer/folio never overlap body content
    - typography can run smaller without turning chaotic
    - scene kinds can be dense while staying readable
    - posters can use either source images or generated bitmaps
    """

    theme: MonoTheme = DEFAULT_THEME

    def render(
        self,
        scene: SceneSpec,
        *,
        slot: Optional[int] = None,
        total_slots: Optional[int] = None,
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

    def _render_hero(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = frame.content
        content = self._draw_kicker(draw, content, scene)

        header_height = 126 if scene.metric else 146
        header_rect, lower_rect = content.split_top(header_height, gap=self.theme.section_gap)
        if scene.subtitle:
            subtitle_rect, title_rect = header_rect.split_top(24, gap=6)
            self._fit_and_draw(
                draw,
                subtitle_rect,
                scene.subtitle,
                max_font_size=20,
                min_font_size=14,
                max_lines=1,
            )
        else:
            title_rect = header_rect

        self._fit_and_draw(
            draw,
            title_rect,
            scene.title,
            max_font_size=48,
            min_font_size=24,
            max_lines=3,
            line_spacing=4,
        )
        self._draw_rule(draw, lower_rect.y - self.theme.section_gap // 2, frame.outer)

        if scene.metric:
            metric_rect, body_rect = lower_rect.split_left(188, gap=self.theme.gutter)
            self._draw_metric_card(draw, metric_rect, scene.metric.label, scene.metric.value, scene.metric.detail)
        else:
            body_rect = lower_rect

        self._draw_bullet_rows(draw, body_rect, scene.body, max_items=4)

    def _render_metrics(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = self._draw_kicker(draw, frame.content, scene)
        header_rect, grid_rect = content.split_top(46, gap=self.theme.section_gap)
        title_rect, meta_rect = header_rect.split_left(int(header_rect.width * 0.62), gap=self.theme.gutter)

        self._fit_and_draw(
            draw,
            title_rect,
            scene.title.upper(),
            max_font_size=28,
            min_font_size=20,
            max_lines=1,
        )
        if scene.subtitle:
            self._fit_and_draw(
                draw,
                meta_rect,
                scene.subtitle,
                max_font_size=17,
                min_font_size=13,
                max_lines=1,
                align="right",
                valign="bottom",
            )

        self._draw_rule(draw, grid_rect.y - self.theme.section_gap // 2, frame.outer)

        display_metrics = scene.metrics[:6]
        if not display_metrics:
            self._fit_and_draw(draw, grid_rect, "No metrics available", max_font_size=22, min_font_size=16, max_lines=2)
            return

        cols = 3 if len(display_metrics) > 4 else 2
        rows = max(1, (len(display_metrics) + cols - 1) // cols)
        for row_rect, row_items in zip(grid_rect.rows(rows, gap=self.theme.gutter), self._chunk(display_metrics, cols)):
            for card_rect, metric in zip(row_rect.columns(len(row_items), gap=self.theme.gutter), row_items):
                self._draw_metric_card(draw, card_rect, metric.label, metric.value, metric.detail)

    def _render_bulletin(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = self._draw_kicker(draw, frame.content, scene)
        header_rect, list_rect = content.split_top(54 if scene.subtitle else 42, gap=self.theme.section_gap)

        if scene.subtitle:
            title_rect, subtitle_rect = header_rect.split_top(28, gap=4)
            self._fit_and_draw(
                draw,
                title_rect,
                scene.title.upper(),
                max_font_size=28,
                min_font_size=20,
                max_lines=1,
            )
            self._fit_and_draw(
                draw,
                subtitle_rect,
                scene.subtitle,
                max_font_size=17,
                min_font_size=13,
                max_lines=1,
            )
        else:
            self._fit_and_draw(
                draw,
                header_rect,
                scene.title.upper(),
                max_font_size=28,
                min_font_size=20,
                max_lines=1,
            )

        self._draw_rule(draw, list_rect.y - self.theme.section_gap // 2, frame.outer)
        items = scene.items[:6]
        if len(items) <= 3:
            self._draw_numbered_rows(draw, list_rect, items, start_index=1, max_items=3)
            return

        columns = list_rect.columns(2, gap=self.theme.gutter)
        left_items = items[:3]
        right_items = items[3:6]
        self._draw_numbered_rows(draw, columns[0], left_items, start_index=1, max_items=3)
        if right_items:
            self._draw_numbered_rows(draw, columns[1], right_items, start_index=1 + len(left_items), max_items=3)

    def _render_poster(self, img: Image.Image, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = self._draw_kicker(draw, frame.content, scene)
        image_rect, caption_rect = content.split_bottom(108, gap=self.theme.section_gap)
        art = self._load_art(scene.image_path, image_rect.width, image_rect.height, scene)
        img.paste(art, (image_rect.x, image_rect.y))

        draw.rectangle((caption_rect.x, caption_rect.y, caption_rect.right, caption_rect.bottom), fill=255, outline=0, width=2)
        caption_inner = caption_rect.inset(self.theme.card_padding)
        title_height = 52 if scene.subtitle else caption_inner.height
        title_rect, subtitle_rect = caption_inner.split_top(title_height, gap=6)

        self._fit_and_draw(
            draw,
            title_rect,
            scene.title,
            max_font_size=30,
            min_font_size=18,
            max_lines=2,
            line_spacing=4,
        )
        if scene.subtitle:
            self._fit_and_draw(
                draw,
                subtitle_rect,
                scene.subtitle,
                max_font_size=16,
                min_font_size=12,
                max_lines=2,
            )

    def _render_fallback(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = self._draw_kicker(draw, frame.content, scene)
        title_rect, body_rect = content.split_top(94, gap=self.theme.section_gap)
        draw.rectangle((frame.outer.x, frame.outer.y, frame.outer.right, frame.footer.y - self.theme.section_gap), outline=0, width=2)
        self._fit_and_draw(draw, title_rect, scene.title, max_font_size=34, min_font_size=20, max_lines=3)
        self._draw_bullet_rows(draw, body_rect, scene.body or scene.items, max_items=4)

    def _draw_kicker(self, draw: ImageDraw.ImageDraw, rect: Rect, scene: SceneSpec) -> Rect:
        kicker = self._meta(scene, "kicker") or self._meta(scene, "eyebrow")
        if not kicker:
            return rect

        kicker_rect, rest = rect.split_top(self.theme.kicker_height, gap=6)
        mono_font = load_mono_font(size=14)
        draw.text((kicker_rect.x, kicker_rect.y), str(kicker).upper(), font=mono_font, fill=0)
        self._draw_rule(draw, rest.y - 4, Rect(rect.x, rect.y, rect.width, rect.height))
        return rest

    def _draw_metric_card(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        label: str,
        value: str,
        detail: str | None,
    ) -> None:
        draw.rectangle((rect.x, rect.y, rect.right, rect.bottom), outline=0, width=2)
        inner = rect.inset(self.theme.card_padding)
        label_rect, value_region = inner.split_top(18, gap=8)
        detail_height = 16 if detail else 1
        value_rect, detail_rect = value_region.split_bottom(detail_height, gap=6 if detail else 0)

        mono_font = load_mono_font(size=13)
        draw.text((label_rect.x, label_rect.y), label.upper(), font=mono_font, fill=0)
        self._fit_and_draw(
            draw,
            value_rect,
            value,
            max_font_size=34,
            min_font_size=18,
            max_lines=2,
            valign="center",
        )
        if detail:
            self._fit_and_draw(
                draw,
                detail_rect,
                detail,
                max_font_size=14,
                min_font_size=11,
                max_lines=1,
            )

    def _draw_bullet_rows(self, draw: ImageDraw.ImageDraw, rect: Rect, items: list[str], *, max_items: int) -> None:
        if not items:
            self._fit_and_draw(draw, rect, "No items available", max_font_size=20, min_font_size=14, max_lines=2)
            return

        budget = min(len(items), max_items, max(1, rect.height // 54))
        for row_rect, item in zip(rect.rows(budget, gap=6), items[:budget]):
            bullet_rect, text_rect = row_rect.split_left(18, gap=8)
            center_y = bullet_rect.y + bullet_rect.height // 2
            draw.rectangle((bullet_rect.x, center_y - 4, bullet_rect.x + 8, center_y + 4), fill=0)
            self._fit_and_draw(
                draw,
                text_rect,
                item,
                max_font_size=20,
                min_font_size=14,
                max_lines=2,
                valign="center",
            )

    def _draw_numbered_rows(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        items: list[str],
        *,
        start_index: int,
        max_items: int,
    ) -> None:
        if not items:
            self._fit_and_draw(draw, rect, "No feed items available", max_font_size=20, min_font_size=14, max_lines=2)
            return

        budget = min(len(items), max_items, max(1, rect.height // 62))
        number_font = load_mono_font(size=14)
        for offset, (row_rect, item) in enumerate(zip(rect.rows(budget, gap=8), items[:budget])):
            badge_rect, text_rect = row_rect.split_left(32, gap=10)
            draw.rectangle((badge_rect.x, badge_rect.y + 2, badge_rect.right, badge_rect.bottom - 2), outline=0, width=2)
            badge = str(start_index + offset)
            bbox = draw.textbbox((0, 0), badge, font=number_font)
            tx = badge_rect.x + (badge_rect.width - (bbox[2] - bbox[0])) // 2
            ty = badge_rect.y + (badge_rect.height - (bbox[3] - bbox[1])) // 2 - 1
            draw.text((tx, ty), badge, font=number_font, fill=0)
            self._fit_and_draw(
                draw,
                text_rect,
                item,
                max_font_size=18,
                min_font_size=13,
                max_lines=2,
                valign="center",
            )

    def _draw_footer_bar(
        self,
        draw: ImageDraw.ImageDraw,
        scene: SceneSpec,
        rect: Rect,
        *,
        slot: Optional[int],
        total_slots: Optional[int],
    ) -> None:
        draw.line((rect.x, rect.y - self.theme.rule_inset, rect.right, rect.y - self.theme.rule_inset), fill=0, width=self.theme.line_width)
        left_rect, right_rect = rect.split_right(74, gap=self.theme.gutter)
        footer_left, footer_center = left_rect.split_left(int(left_rect.width * 0.68), gap=self.theme.gutter)

        left_text = self._meta(scene, "footer_left") or scene.footer or scene.kind
        center_text = self._meta(scene, "footer_center") or self._meta(scene, "stamp") or self._meta(scene, "updated_at")
        footer_right = self._meta(scene, "footer_right")

        self._fit_and_draw(
            draw,
            footer_left,
            str(left_text),
            max_font_size=14,
            min_font_size=11,
            max_lines=1,
        )
        if center_text:
            self._fit_and_draw(
                draw,
                footer_center,
                str(center_text),
                max_font_size=13,
                min_font_size=10,
                max_lines=1,
                align="center",
            )
        if footer_right:
            mono_font = load_mono_font(size=14)
            bbox = draw.textbbox((0, 0), str(footer_right), font=mono_font)
            x = right_rect.right - (bbox[2] - bbox[0])
            y = right_rect.y + max(0, (right_rect.height - (bbox[3] - bbox[1])) // 2) - 1
            draw.text((x, y), str(footer_right), font=mono_font, fill=0)

    def _fit_and_draw(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        text: str,
        *,
        max_font_size: int,
        min_font_size: int,
        max_lines: int,
        line_spacing: int = 4,
        align: str = "left",
        valign: str = "top",
    ) -> None:
        fitted = fit_text_block(
            draw,
            text,
            rect,
            max_font_size=max_font_size,
            min_font_size=min_font_size,
            max_lines=max_lines,
            line_spacing=line_spacing,
        )
        draw_text_block(
            draw,
            rect,
            fitted,
            align=align,
            valign=valign,
            line_spacing=line_spacing,
        )

    def _load_art(self, path: str | None, width: int, height: int, scene: SceneSpec) -> Image.Image:
        bitmap_spec = scene.meta.get("bitmap") if isinstance(scene.meta, dict) else None
        if path:
            image = Image.open(Path(path)).convert("L")
        elif isinstance(bitmap_spec, dict):
            image = generate_bitmap(bitmap_spec, width, height)
        else:
            image = self._placeholder_art(width, height, scene)

        art = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        art = ImageOps.autocontrast(art)
        art = ImageEnhance.Contrast(art).enhance(1.5)
        return art.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")

    def _placeholder_art(self, width: int, height: int, scene: SceneSpec) -> Image.Image:
        img = Image.new("L", (width, height), color=255)
        draw = ImageDraw.Draw(img)
        stripe_height = max(18, height // 10)
        for idx, stripe_y in enumerate(range(0, height, stripe_height)):
            fill = 232 if idx % 2 == 0 else 196
            draw.rectangle((0, stripe_y, width, min(height, stripe_y + stripe_height)), fill=fill)

        label = textwrap.shorten((self._meta(scene, "kicker") or scene.kind).upper(), width=16, placeholder="…")
        mono_font = load_mono_font(size=16)
        draw.rectangle((18, 18, 18 + 84, 18 + 28), fill=255, outline=0, width=2)
        draw.text((28, 24), label, font=mono_font, fill=0)
        return img

    def _draw_rule(self, draw: ImageDraw.ImageDraw, y: int, rect: Rect) -> None:
        draw.line((rect.x, y, rect.right, y), fill=0, width=self.theme.line_width)

    @staticmethod
    def _meta(scene: SceneSpec, key: str) -> object | None:
        return scene.meta.get(key) if isinstance(scene.meta, dict) else None

    @staticmethod
    def _chunk(items: list, size: int) -> list[list]:
        return [items[index : index + size] for index in range(0, len(items), size)]
