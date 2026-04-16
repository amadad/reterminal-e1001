"""Base class for legacy fixed-page renderers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, TypeVar

from PIL import Image, ImageDraw
from loguru import logger

from reterminal.client import ReTerminal
from reterminal.config import HEIGHT, WIDTH
from reterminal.encoding import pil_to_raw
from reterminal.fonts import load_font_family

PageDataT = TypeVar("PageDataT")


class BasePage(ABC, Generic[PageDataT]):
    """Common fetch/render/push workflow for legacy pages."""

    name: str = "base"
    description: str = "Base page"

    def __init__(self, host: str | None = None):
        self.host = host
        self._client: ReTerminal | None = None

    @property
    def client(self) -> ReTerminal:
        if self._client is None:
            self._client = ReTerminal(self.host)
        return self._client

    @abstractmethod
    def get_data(self) -> PageDataT:
        """Fetch data for the page."""

    @abstractmethod
    def render(self, data: PageDataT) -> Image.Image:
        """Render page data into a 1-bit image."""

    def refresh(self, page: int | None = None) -> dict[str, object]:
        """Fetch, render, and push a page in one call."""
        logger.info(f"Refreshing {self.name} page")
        data = self.get_data()
        img = self.render(data)
        raw = pil_to_raw(img)
        result = self.client.push_raw(raw, page=page)
        logger.info(f"{self.name} page refreshed successfully")
        return result

    @staticmethod
    def create_canvas(background: int = 1) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        img = Image.new("1", (WIDTH, HEIGHT), color=background)
        draw = ImageDraw.Draw(img)
        return img, draw

    @staticmethod
    def load_fonts() -> dict[str, object]:
        return load_font_family()

    @staticmethod
    def add_timestamp(
        draw: ImageDraw.ImageDraw,
        font: object,
        y: int | None = None,
        prefix: str = "Updated: ",
    ) -> None:
        if y is None:
            y = HEIGHT - 50

        now = datetime.now().strftime("%H:%M")
        draw.text((50, y), f"{prefix}{now}", font=font, fill=0)

    @staticmethod
    def draw_divider(draw: ImageDraw.ImageDraw, y: int, margin: int = 50, width: int = 2) -> None:
        draw.line([(margin, y), (WIDTH - margin, y)], fill=0, width=width)
