"""Monochrome scene renderer with dense editorial templates."""

from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path

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
        if scene.prerendered is not None:
            return self._finalize_prerendered(scene.prerendered)
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
            case "agenda":
                self._render_agenda(draw, scene, frame)
            case "poster":
                self._render_poster(img, draw, scene, frame)
            case _:
                self._render_fallback(draw, scene, frame)

        if not self._meta_flag(scene, "hide_footer"):
            self._draw_footer_bar(draw, scene, frame.footer, slot=slot, total_slots=total_slots)
        finished = ImageOps.autocontrast(img)
        if scene.kind == "poster":
            return finished.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        return finished.point(lambda x: 255 if x >= 192 else 0, mode="1")

    def _finalize_prerendered(self, image: Image.Image) -> Image.Image:
        """Coerce a provider-supplied bitmap to the device contract (800x480 mode "1")."""
        if image.size != (WIDTH, HEIGHT):
            image = image.resize((WIDTH, HEIGHT))
        if image.mode == "1":
            return image
        if image.mode != "L":
            image = image.convert("L")
        return image.point(lambda x: 255 if x >= 192 else 0, mode="1")

    def _build_frame(self) -> SceneFrame:
        margin = self.theme.outer_margin
        outer = Rect(margin, margin, WIDTH - margin * 2, HEIGHT - margin * 2)
        content, footer = outer.split_bottom(self.theme.footer_height, gap=self.theme.section_gap)
        return SceneFrame(outer=outer, content=content, footer=footer)

    # === Hero: big title, optional metric sidebar, body bullets ===

    def _render_hero(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        if self._meta(scene, "hero_style") == "focus":
            self._render_focus_hero(draw, scene, frame)
            return

        content = frame.content
        content = self._draw_header_band(draw, content, scene)

        header_height = 96 if scene.metric else 118
        header_rect, lower_rect = content.split_top(header_height, gap=self.theme.section_gap)

        if scene.subtitle:
            subtitle_rect, title_rect = header_rect.split_top(18, gap=2)
            self._fit_and_draw(draw, subtitle_rect, scene.subtitle, max_font_size=17, min_font_size=13, max_lines=1)
        else:
            title_rect = header_rect

        self._fit_and_draw(draw, title_rect, scene.title, max_font_size=62, min_font_size=34, max_lines=3, line_spacing=1)
        draw.line((lower_rect.x, lower_rect.y - 2, lower_rect.x + lower_rect.width, lower_rect.y - 2), fill=0, width=1)

        if scene.metric:
            metric_rect, body_rect = lower_rect.split_left(190, gap=self.theme.gutter)
            self._draw_metric_block(draw, metric_rect, scene.metric.label, scene.metric.value, scene.metric.detail)
        else:
            body_rect = lower_rect

        self._draw_body_rows(draw, body_rect, scene.body, max_items=4)

    def _render_focus_hero(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = frame.content
        content = self._draw_header_band(draw, content, scene)

        title_height = min(110, max(78, content.height // 4))
        title_rect, remainder = content.split_top(title_height, gap=18)
        if "\n" in scene.title:
            self._draw_explicit_lines(
                draw,
                title_rect,
                scene.title,
                max_font_size=80,
                min_font_size=40,
                line_spacing=2,
            )
        else:
            self._fit_and_draw(
                draw,
                title_rect,
                scene.title,
                max_font_size=68,
                min_font_size=28,
                max_lines=1,
                line_spacing=1,
                valign="center",
            )

        focus_value = ""
        if scene.metric and scene.metric.value:
            focus_value = str(scene.metric.value)
        elif scene.body:
            focus_value = scene.body[0]
        elif scene.subtitle:
            focus_value = scene.subtitle

        if not focus_value:
            return

        value_height = min(150, max(86, remainder.height // 3))
        value_rect, _ = remainder.split_top(value_height, gap=0)
        self._fit_and_draw(
            draw,
            value_rect,
            focus_value,
            max_font_size=52,
            min_font_size=28,
            max_lines=3,
            line_spacing=1,
            valign="center",
        )

    # === Metrics: dense grid with inverted label headers ===

    def _render_metrics(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = frame.content
        content = self._draw_header_band(draw, content, scene)

        header_rect, grid_rect = content.split_top(32, gap=self.theme.section_gap)
        title_rect, meta_rect = header_rect.split_left(int(header_rect.width * 0.6), gap=self.theme.gutter)

        self._fit_and_draw(draw, title_rect, scene.title.upper(), max_font_size=26, min_font_size=18, max_lines=1)
        if scene.subtitle:
            self._fit_and_draw(draw, meta_rect, scene.subtitle, max_font_size=14, min_font_size=11, max_lines=1, align="right", valign="bottom")

        draw.line((grid_rect.x, grid_rect.y - 2, grid_rect.x + grid_rect.width, grid_rect.y - 2), fill=0, width=1)

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

        header_rect, list_rect = content.split_top(34 if scene.subtitle else 28, gap=self.theme.section_gap)

        if scene.subtitle:
            title_rect, subtitle_rect = header_rect.split_top(20, gap=1)
            self._fit_and_draw(draw, title_rect, scene.title, max_font_size=28, min_font_size=18, max_lines=1)
            self._fit_and_draw(draw, subtitle_rect, scene.subtitle, max_font_size=14, min_font_size=11, max_lines=1)
        else:
            self._fit_and_draw(draw, header_rect, scene.title, max_font_size=28, min_font_size=18, max_lines=1)

        if not self._meta_flag(scene, "hide_title_rule"):
            draw.line((list_rect.x, list_rect.y - 2, list_rect.x + list_rect.width, list_rect.y - 2), fill=0, width=1)

        items = scene.items[:8]
        if not items:
            self._fit_and_draw(draw, list_rect, "No items", max_font_size=18, min_font_size=14, max_lines=1)
            return

        self._draw_bulletin_rows(draw, scene, list_rect, items)

    def _render_agenda(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        style = str(self._meta(scene, "agenda_style") or "grouped").lower()
        if style == "two_day":
            self._render_two_day_agenda(draw, scene, frame)
            return
        self._render_grouped_agenda(draw, scene, frame)

    def _render_two_day_agenda(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = frame.content
        dinner_height = 112
        upper_rect, dinner_rect = content.split_bottom(dinner_height, gap=12)
        left_rect, right_rect = upper_rect.columns(2, gap=18)
        divider_x = left_rect.right + 9
        draw.line((divider_x, upper_rect.y, divider_x, upper_rect.bottom), fill=0, width=2)

        today_rows = self._meta_rows(scene, "today_rows")
        tomorrow_rows = self._meta_rows(scene, "tomorrow_rows")
        shared_row_count = max(len(today_rows), len(tomorrow_rows), 1)
        _, left_rows_rect = left_rect.split_top(28, gap=8)
        row_height = min(52, max(38, left_rows_rect.height // shared_row_count))

        self._draw_agenda_column(
            draw,
            left_rect,
            str(self._meta(scene, "today_label") or "Today"),
            today_rows,
            row_height=row_height,
        )
        self._draw_agenda_column(
            draw,
            right_rect,
            str(self._meta(scene, "tomorrow_label") or "Tomorrow"),
            tomorrow_rows,
            row_height=row_height,
        )
        self._draw_dinner_block(
            draw,
            dinner_rect,
            str(self._meta(scene, "dinner_label") or "Dinner"),
            str(self._meta(scene, "dinner_value") or "Plan dinner"),
            str(self._meta(scene, "dinner_icon") or ""),
        )

    def _render_grouped_agenda(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, frame: SceneFrame) -> None:
        content = frame.content
        title = scene.title.strip()
        if title and not self._meta_flag(scene, "hide_title"):
            title_rect, content = content.split_top(28, gap=10)
            self._fit_and_draw(draw, title_rect, title, max_font_size=28, min_font_size=20, max_lines=1)

        sections = self._meta_sections(scene)
        if not sections:
            self._fit_and_draw(draw, content, "No upcoming events", max_font_size=24, min_font_size=18, max_lines=2)
            return

        section_gap = 14
        y = content.y
        remaining_height = content.height
        for index, section in enumerate(sections):
            if remaining_height < 48:
                break
            day_height = 26
            rows = section.get("rows") if isinstance(section, dict) else None
            row_count = len(rows) if isinstance(rows, list) and rows else 1
            row_height = 40
            section_height = day_height + 8 + row_count * row_height + max(0, row_count - 1) * 2
            section_height = min(section_height, remaining_height)
            section_rect = Rect(content.x, y, content.width, section_height)
            self._draw_agenda_section(draw, section_rect, section)
            y += section_height + section_gap
            remaining_height = content.bottom - y
            if index < len(sections) - 1 and remaining_height > 12:
                draw.line((content.x, y - 7, content.right, y - 7), fill=0, width=2)

    def _draw_agenda_column(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        label: str,
        rows: list[dict[str, object]],
        *,
        row_height: int | None = None,
    ) -> None:
        label_rect, rows_rect = rect.split_top(28, gap=8)
        self._fit_and_draw(draw, label_rect, label, max_font_size=32, min_font_size=22, max_lines=1)
        if row_height is None:
            row_height = 44 if len(rows) >= 6 else 50 if len(rows) >= 5 else 52
        self._draw_agenda_rows(draw, rows_rect, rows, row_height=row_height, row_gap=0, separator_width=2)

    def _draw_agenda_section(self, draw: ImageDraw.ImageDraw, rect: Rect, section: object) -> None:
        label = "Later"
        rows: list[dict[str, object]] = []
        if isinstance(section, dict):
            label = str(section.get("label") or label)
            raw_rows = section.get("rows")
            if isinstance(raw_rows, list):
                rows = [row for row in raw_rows if isinstance(row, dict)]

        label_rect, rows_rect = rect.split_top(26, gap=8)
        self._fit_and_draw(draw, label_rect, label, max_font_size=26, min_font_size=18, max_lines=1)
        self._draw_agenda_rows(draw, rows_rect, rows, row_height=40, row_gap=2, separator_width=1)

    def _draw_agenda_rows(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        rows: list[dict[str, object]],
        *,
        row_height: int,
        row_gap: int,
        separator_width: int,
    ) -> None:
        if not rows:
            self._fit_and_draw(draw, rect, "No events", max_font_size=22, min_font_size=16, max_lines=1)
            return

        visible_rows = rows
        y = rect.y
        rendered_rows: list[dict[str, object]] = []
        for row in visible_rows:
            remaining = rect.bottom - y
            if remaining < 28:
                break
            rendered_rows.append(row)
            y += min(row_height, remaining) + row_gap

        y = rect.y
        for index, row in enumerate(rendered_rows):
            remaining = rect.bottom - y
            if remaining < 28:
                break
            current_height = min(row_height, remaining)
            row_rect = Rect(rect.x, y, rect.width, current_height)
            self._draw_event_row(draw, row_rect, row)
            y += current_height + row_gap
            if index < len(rendered_rows) - 1 and y < rect.bottom:
                draw.line((rect.x, y - max(1, row_gap // 2), rect.right, y - max(1, row_gap // 2)), fill=0, width=separator_width)

    def _draw_event_row(self, draw: ImageDraw.ImageDraw, rect: Rect, row: dict[str, object]) -> None:
        chip = str(row.get("chip") or "F")[:1].upper()
        icon = str(row.get("icon") or "event")
        time_text = str(row.get("time") or "").strip()
        title = str(row.get("title") or "Event")

        chip_size = 24
        icon_size = 16
        chip_rect = Rect(rect.x, rect.y + max(0, (rect.height - chip_size) // 2), chip_size, chip_size)
        self._draw_chip(draw, chip_rect, chip)

        icon_rect = Rect(chip_rect.right + 8, rect.y + max(0, (rect.height - icon_size) // 2), icon_size, icon_size)
        self._draw_event_icon(draw, icon_rect, icon)

        text_x = icon_rect.right + 8
        if time_text:
            time_rect = Rect(text_x, rect.y, 92, rect.height)
            self._fit_and_draw(draw, time_rect, time_text, max_font_size=18, min_font_size=14, max_lines=1, valign="center")
            title_rect = Rect(time_rect.right + 10, rect.y, max(1, rect.right - (time_rect.right + 10)), rect.height)
        else:
            title_rect = Rect(text_x, rect.y, max(1, rect.right - text_x), rect.height)

        self._fit_and_draw(draw, title_rect, title, max_font_size=24, min_font_size=18, max_lines=2, valign="center")

    def _draw_chip(self, draw: ImageDraw.ImageDraw, rect: Rect, chip: str) -> None:
        draw.rectangle((rect.x, rect.y, rect.right, rect.bottom), fill=0)
        font = load_font(size=15)
        bbox = draw.textbbox((0, 0), chip, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        x = rect.x + max(0, (rect.width - width) // 2)
        y = rect.y + max(0, (rect.height - height) // 2)
        draw.text((x, y), chip, font=font, fill=255)

    def _draw_event_icon(self, draw: ImageDraw.ImageDraw, rect: Rect, icon: str) -> None:
        x0, y0, x1, y1 = rect.x, rect.y, rect.right, rect.bottom
        cx = x0 + rect.width // 2
        cy = y0 + rect.height // 2
        if icon in {"sports", "sports_practice", "sports_game"}:
            draw.ellipse((x0 + 1, y0 + 1, x1 - 1, y1 - 1), outline=0, width=2)
            draw.arc((x0 + 2, y0 + 2, x1 - 2, y1 - 2), start=45, end=135, fill=0, width=1)
            draw.arc((x0 + 2, y0 + 2, x1 - 2, y1 - 2), start=225, end=315, fill=0, width=1)
            if icon == "sports_practice":
                draw.line((cx - 2, cy, cx + 2, cy), fill=0, width=1)
            elif icon == "sports_game":
                draw.line((cx - 3, cy - 3, cx + 3, cy + 3), fill=0, width=1)
                draw.line((cx - 3, cy + 3, cx + 3, cy - 3), fill=0, width=1)
        elif icon == "health":
            draw.rectangle((x0 + 1, y0 + 1, x1 - 1, y1 - 1), outline=0, width=1)
            draw.line((cx, y0 + 3, cx, y1 - 3), fill=0, width=2)
            draw.line((x0 + 3, cy, x1 - 3, cy), fill=0, width=2)
        elif icon == "school":
            draw.rectangle((x0 + 1, y0 + 2, x1 - 1, y1 - 1), outline=0, width=1)
            draw.line((cx, y0 + 2, cx, y1 - 1), fill=0, width=1)
        elif icon == "faith":
            draw.ellipse((x0 + 2, y0 + 1, x1 - 2, y1 - 1), outline=0, width=2)
            draw.ellipse((x0 + 6, y0 + 1, x1 + 2, y1 - 1), fill=255, outline=255)
        elif icon == "family":
            draw.polygon([(cx, y0 + 1), (x1 - 1, y0 + 6), (x1 - 1, y1 - 1), (x0 + 1, y1 - 1), (x0 + 1, y0 + 6)], outline=0)
            draw.line((x0 + 2, y0 + 6, cx, y0 + 2), fill=0, width=1)
            draw.line((x1 - 2, y0 + 6, cx, y0 + 2), fill=0, width=1)
        elif icon == "food":
            draw.ellipse((x0 + 1, y0 + 3, x1 - 5, y1 - 1), outline=0, width=1)
            draw.line((x1 - 3, y0 + 2, x1 - 3, y1 - 2), fill=0, width=1)
            draw.line((x1 - 5, y0 + 2, x1 - 5, y0 + 6), fill=0, width=1)
            draw.line((x1 - 1, y0 + 2, x1 - 1, y0 + 6), fill=0, width=1)
        else:
            draw.ellipse((x0 + 4, y0 + 4, x1 - 4, y1 - 4), fill=0)

    def _draw_dinner_block(self, draw: ImageDraw.ImageDraw, rect: Rect, label: str, value: str, icon: str) -> None:
        draw.line((rect.x, rect.y, rect.right, rect.y), fill=0, width=2)
        inner = rect.inset(2)
        label_rect, value_rect = inner.split_left(108, gap=14)
        label_text_rect = label_rect
        if icon:
            icon_rect = Rect(label_rect.x, label_rect.y + max(0, (label_rect.height - 18) // 2), 18, 18)
            self._draw_event_icon(draw, icon_rect, icon)
            label_text_rect = Rect(icon_rect.right + 8, label_rect.y, max(1, label_rect.right - (icon_rect.right + 8)), label_rect.height)
        self._fit_and_draw(draw, label_text_rect, label, max_font_size=26, min_font_size=16, max_lines=1, valign="center")
        self._fit_and_draw(draw, value_rect, value, max_font_size=30, min_font_size=16, max_lines=3, line_spacing=1, valign="center")

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
        if not kicker or self._meta_flag(scene, "hide_header"):
            return rect

        band_rect, rest = rect.split_top(self.theme.kicker_height, gap=2)
        draw.rectangle((band_rect.x, band_rect.y, band_rect.right, band_rect.bottom), fill=0)
        mono_font = load_mono_font(size=11)
        draw.text((band_rect.x + 5, band_rect.y + 2), str(kicker).upper(), font=mono_font, fill=255)
        if stamp:
            stamp_text = str(stamp)
            bbox = draw.textbbox((0, 0), stamp_text, font=mono_font)
            sx = band_rect.right - (bbox[2] - bbox[0]) - 5
            draw.text((sx, band_rect.y + 2), stamp_text, font=mono_font, fill=255)
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
        label_height = 18
        label_rect, value_region = rect.split_top(label_height, gap=0)
        draw.rectangle((label_rect.x, label_rect.y, label_rect.right, label_rect.bottom), fill=0)
        mono_font = load_mono_font(size=10)
        draw.text((label_rect.x + 5, label_rect.y + 2), label.upper(), font=mono_font, fill=255)

        draw.rectangle((rect.x, label_rect.bottom, rect.right, rect.bottom), outline=0, width=1)
        inner = Rect(rect.x + 5, label_rect.bottom + 3, rect.width - 10, rect.bottom - label_rect.bottom - 6)

        if detail:
            value_rect, detail_rect = inner.split_bottom(12, gap=1)
        else:
            value_rect = inner
            detail_rect = None

        self._fit_and_draw(draw, value_rect, value, max_font_size=34, min_font_size=18, max_lines=2, valign="center", line_spacing=1)
        if detail_rect:
            self._fit_and_draw(draw, detail_rect, detail, max_font_size=11, min_font_size=9, max_lines=1)

    def _draw_body_rows(self, draw: ImageDraw.ImageDraw, rect: Rect, items: list[str], *, max_items: int) -> None:
        if not items:
            self._fit_and_draw(draw, rect, "No items available", max_font_size=18, min_font_size=14, max_lines=1)
            return

        gap = 2
        budget = min(len(items), max_items, max(1, rect.height // 34))
        row_height = min(54, max(34, (rect.height - gap * max(0, budget - 1)) // budget))
        y = rect.y
        for item in items[:budget]:
            remaining = rect.bottom - y
            if remaining < 20:
                break
            current_height = min(row_height, remaining)
            row_rect = Rect(rect.x, y, rect.width, current_height)
            dash_y = row_rect.y + row_rect.height // 2
            draw.line((row_rect.x, dash_y, row_rect.x + 8, dash_y), fill=0, width=2)
            text_rect = Rect(row_rect.x + 14, row_rect.y, row_rect.width - 14, row_rect.height)
            self._fit_and_draw(draw, text_rect, item, max_font_size=22, min_font_size=15, max_lines=2, valign="center", line_spacing=1)
            y += current_height + gap

    def _draw_bulletin_rows(self, draw: ImageDraw.ImageDraw, scene: SceneSpec, rect: Rect, items: list[str]) -> None:
        gap = self._meta_int(scene, "item_gap", default=2)
        max_lines = self._meta_int(scene, "item_max_lines", default=2)
        max_font_size = self._meta_int(scene, "item_max_font_size", default=24)
        min_font_size = self._meta_int(scene, "item_min_font_size", default=16)
        budget = min(len(items), max(1, rect.height // 34))
        row_height = min(64, max(34, (rect.height - gap * max(0, budget - 1)) // budget))
        y = rect.y
        for index, item in enumerate(items[:budget]):
            remaining = rect.bottom - y
            if remaining < 20:
                break
            current_height = min(row_height, remaining)
            row_rect = Rect(rect.x, y, rect.width, current_height)
            if index > 0 and not self._meta_flag(scene, "hide_row_rules"):
                draw.line((row_rect.x, row_rect.y - 1, row_rect.x + row_rect.width, row_rect.y - 1), fill=220, width=1)
            self._fit_and_draw(
                draw,
                row_rect,
                item,
                max_font_size=max_font_size,
                min_font_size=min_font_size,
                max_lines=max_lines,
                valign="center",
                line_spacing=1,
            )
            y += current_height + gap

    def _draw_explicit_lines(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        text: str,
        *,
        max_font_size: int,
        min_font_size: int,
        line_spacing: int,
    ) -> None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return

        chosen_font = load_font(size=min_font_size)
        chosen_line_height = 0
        chosen_height = 0
        for size in range(max_font_size, min_font_size - 1, -2):
            font = load_font(size=size)
            line_height = max((draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1]) for line in lines)
            total_height = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing
            max_width = max(draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0] for line in lines)
            if total_height <= rect.height and max_width <= rect.width:
                chosen_font = font
                chosen_line_height = line_height
                chosen_height = total_height
                break
        if chosen_line_height == 0:
            chosen_line_height = max((draw.textbbox((0, 0), line, font=chosen_font)[3] - draw.textbbox((0, 0), line, font=chosen_font)[1]) for line in lines)
            chosen_height = len(lines) * chosen_line_height + max(0, len(lines) - 1) * line_spacing

        y = rect.y + max(0, (rect.height - chosen_height) // 2)
        for line in lines:
            draw.text((rect.x, y), line, font=chosen_font, fill=0)
            y += chosen_line_height + line_spacing

    def _draw_footer_bar(
        self,
        draw: ImageDraw.ImageDraw,
        scene: SceneSpec,
        rect: Rect,
        *,
        slot: int | None,
        total_slots: int | None,
    ) -> None:
        mono_font = load_mono_font(size=9)
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
        line_spacing: int = 1,
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
        except (requests.RequestException, OSError, Image.UnidentifiedImageError):
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
    def _meta_flag(scene: SceneSpec, key: str) -> bool:
        value = scene.meta.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return False

    @staticmethod
    def _meta_rows(scene: SceneSpec, key: str) -> list[dict[str, object]]:
        value = scene.meta.get(key)
        if not isinstance(value, list):
            return []
        return [row for row in value if isinstance(row, dict)]

    @staticmethod
    def _meta_sections(scene: SceneSpec) -> list[dict[str, object]]:
        value = scene.meta.get("sections")
        if not isinstance(value, list):
            return []
        return [section for section in value if isinstance(section, dict)]

    @staticmethod
    def _meta_int(scene: SceneSpec, key: str, *, default: int) -> int:
        value = scene.meta.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float, str)):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    @staticmethod
    def _chunk(items: list, size: int) -> list[list]:
        return [items[index : index + size] for index in range(0, len(items), size)]
