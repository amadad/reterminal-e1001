"""Monochrome scene renderer with a small editorial design system."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from reterminal.config import HEIGHT, WIDTH
from reterminal.fonts import load_font
from reterminal.render.theme import DEFAULT_THEME, MonoTheme
from reterminal.scenes import SceneSpec


@dataclass(slots=True)
class MonoRenderer:
    """Render logical scenes to 800x480 monochrome bitmaps."""

    theme: MonoTheme = DEFAULT_THEME

    def render(self, scene: SceneSpec) -> Image.Image:
        img = Image.new("L", (WIDTH, HEIGHT), color=255)
        draw = ImageDraw.Draw(img)

        match scene.kind:
            case "hero":
                self._render_hero(draw, scene)
            case "metrics":
                self._render_metrics(draw, scene)
            case "bulletin":
                self._render_bulletin(draw, scene)
            case "poster":
                self._render_poster(img, draw, scene)
            case _:
                self._render_fallback(draw, scene)

        finished = ImageOps.autocontrast(img)
        return finished.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

    def _render_hero(self, draw: ImageDraw.ImageDraw, scene: SceneSpec) -> None:
        title_font = load_font(size=60)
        subtitle_font = load_font(size=24)
        metric_label_font = load_font(size=20)
        metric_value_font = load_font(size=44)
        body_font = load_font(size=28)
        footer_font = load_font(size=22)

        x = self.theme.outer_margin
        y = self.theme.outer_margin

        if scene.subtitle:
            draw.text((x, y), scene.subtitle.upper(), font=subtitle_font, fill=0)
            y += 34

        y = self._draw_wrapped(draw, scene.title, title_font, x, y, WIDTH - x * 2, line_spacing=8)
        y += 18
        draw.line((x, y, WIDTH - x, y), fill=0, width=self.theme.line_width)
        y += 26

        if scene.metric:
            box_w = 210
            box_h = 110
            draw.rectangle((x, y, x + box_w, y + box_h), outline=0, width=3)
            draw.text((x + 16, y + 12), scene.metric.label.upper(), font=metric_label_font, fill=0)
            draw.text((x + 16, y + 44), scene.metric.value, font=metric_value_font, fill=0)
            if scene.metric.detail:
                draw.text((x + 16, y + 86), scene.metric.detail, font=subtitle_font, fill=0)

            body_x = x + box_w + self.theme.gutter + 6
            body_y = y + 6
        else:
            body_x = x
            body_y = y

        for line in scene.body[:5]:
            body_y = self._draw_wrapped(
                draw,
                f"• {line}",
                body_font,
                body_x,
                body_y,
                WIDTH - body_x - x,
                line_spacing=10,
                max_lines=2,
            )
            body_y += 10

        footer = scene.footer or scene.id
        draw.text((x, HEIGHT - 42), footer, font=footer_font, fill=0)

    def _render_metrics(self, draw: ImageDraw.ImageDraw, scene: SceneSpec) -> None:
        title_font = load_font(size=34)
        metric_label_font = load_font(size=22)
        metric_value_font = load_font(size=42)
        detail_font = load_font(size=20)

        x = self.theme.outer_margin
        y = self.theme.outer_margin
        draw.text((x, y), scene.title.upper(), font=title_font, fill=0)
        if scene.subtitle:
            draw.text((WIDTH - 260, y + 8), scene.subtitle, font=detail_font, fill=0)
        y += 56
        draw.line((x, y, WIDTH - x, y), fill=0, width=self.theme.line_width)
        y += 24

        metrics = scene.metrics[:6]
        cols = 2
        rows = max(1, (len(metrics) + cols - 1) // cols)
        box_w = (WIDTH - x * 2 - self.theme.gutter) // cols
        box_h = max(108, (HEIGHT - y - 54 - (rows - 1) * self.theme.gutter) // rows)

        for index, metric in enumerate(metrics):
            col = index % cols
            row = index // cols
            left = x + col * (box_w + self.theme.gutter)
            top = y + row * (box_h + self.theme.gutter)
            draw.rectangle((left, top, left + box_w, top + box_h), outline=0, width=3)
            draw.text((left + 16, top + 14), metric.label.upper(), font=metric_label_font, fill=0)
            draw.text((left + 16, top + 48), metric.value, font=metric_value_font, fill=0)
            if metric.detail:
                draw.text((left + 16, top + box_h - 34), metric.detail, font=detail_font, fill=0)

        if scene.footer:
            draw.text((x, HEIGHT - 38), scene.footer, font=detail_font, fill=0)

    def _render_bulletin(self, draw: ImageDraw.ImageDraw, scene: SceneSpec) -> None:
        title_font = load_font(size=34)
        subtitle_font = load_font(size=22)
        item_font = load_font(size=26)
        footer_font = load_font(size=20)

        x = self.theme.outer_margin
        y = self.theme.outer_margin
        draw.text((x, y), scene.title.upper(), font=title_font, fill=0)
        y += 40
        if scene.subtitle:
            draw.text((x, y), scene.subtitle, font=subtitle_font, fill=0)
            y += 36
        draw.line((x, y, WIDTH - x, y), fill=0, width=self.theme.line_width)
        y += 26

        for idx, item in enumerate(scene.items[:6], start=1):
            badge_x2 = x + 44
            badge_y2 = y + 34
            draw.rectangle((x, y, badge_x2, badge_y2), outline=0, width=2)
            draw.text((x + 13, y + 5), str(idx), font=subtitle_font, fill=0)
            self._draw_wrapped(draw, item, item_font, badge_x2 + 18, y + 2, WIDTH - badge_x2 - x - 18, max_lines=2)
            y += 58

        footer = scene.footer or f"priority {scene.priority}"
        draw.text((x, HEIGHT - 38), footer, font=footer_font, fill=0)

    def _render_poster(self, img: Image.Image, draw: ImageDraw.ImageDraw, scene: SceneSpec) -> None:
        title_font = load_font(size=34)
        subtitle_font = load_font(size=22)
        footer_font = load_font(size=20)

        x = self.theme.outer_margin
        image_box = (x, x, WIDTH - x, 320)
        art = self._load_art(scene.image_path, image_box[2] - image_box[0], image_box[3] - image_box[1], scene)
        img.paste(art, image_box[:2])

        y = image_box[3] + 22
        self._draw_wrapped(draw, scene.title, title_font, x, y, WIDTH - x * 2, max_lines=2, line_spacing=6)
        if scene.subtitle:
            self._draw_wrapped(draw, scene.subtitle, subtitle_font, x, y + 74, WIDTH - x * 2, max_lines=2)
        footer = scene.footer or scene.id
        draw.text((x, HEIGHT - 34), footer, font=footer_font, fill=0)

    def _render_fallback(self, draw: ImageDraw.ImageDraw, scene: SceneSpec) -> None:
        title_font = load_font(size=42)
        body_font = load_font(size=24)
        x = self.theme.outer_margin
        y = self.theme.outer_margin
        draw.rectangle((x, y, WIDTH - x, HEIGHT - y), outline=0, width=4)
        y += 26
        y = self._draw_wrapped(draw, scene.title, title_font, x + 22, y, WIDTH - (x + 22) * 2)
        y += 18
        for line in scene.body or scene.items:
            y = self._draw_wrapped(draw, line, body_font, x + 22, y, WIDTH - (x + 22) * 2)
            y += 12

    def _draw_wrapped(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font,
        x: int,
        y: int,
        width: int,
        *,
        max_lines: int | None = None,
        line_spacing: int = 4,
    ) -> int:
        lines = self._wrap_text(draw, text, font, width)
        if max_lines is not None:
            lines = lines[:max_lines]
        for line in lines:
            draw.text((x, y), line, font=font, fill=0)
            bbox = draw.textbbox((x, y), line, font=font)
            y += (bbox[3] - bbox[1]) + line_spacing
        return y

    @staticmethod
    def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _load_art(self, path: str | None, width: int, height: int, scene: SceneSpec) -> Image.Image:
        if path:
            image = Image.open(Path(path)).convert("L")
        else:
            image = self._placeholder_art(width, height, scene)

        art = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        art = ImageOps.autocontrast(art)
        art = ImageEnhance.Contrast(art).enhance(1.5)
        return art.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")

    @staticmethod
    def _placeholder_art(width: int, height: int, scene: SceneSpec) -> Image.Image:
        img = Image.new("L", (width, height), color=255)
        draw = ImageDraw.Draw(img)
        for idx, stripe_y in enumerate(range(0, height, 24)):
            fill = 225 if idx % 2 == 0 else 180
            draw.rectangle((0, stripe_y, width, min(height, stripe_y + 24)), fill=fill)
        caption_font = load_font(size=28)
        caption = textwrap.shorten(scene.title.upper(), width=28, placeholder="…")
        draw.rectangle((28, height - 84, width - 28, height - 28), fill=255, outline=0, width=3)
        draw.text((44, height - 70), caption, font=caption_font, fill=0)
        return img
