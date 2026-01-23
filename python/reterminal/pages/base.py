"""Base class for reTerminal display pages."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw
from loguru import logger

from reterminal.client import ReTerminal
from reterminal.config import WIDTH, HEIGHT, settings
from reterminal.encoding import pil_to_raw
from reterminal.fonts import load_font_family


class BasePage(ABC):
    """
    Abstract base class for display pages.

    Subclasses must implement:
        - get_data(): Fetch data needed for the page
        - render(data): Render data to a PIL Image

    Inherited methods:
        - refresh(host, page): Full cycle: fetch -> render -> push
        - create_canvas(): Create blank image with draw context
        - add_timestamp(draw, fonts): Add timestamp footer
    """

    # Page metadata (override in subclass)
    name: str = "base"
    description: str = "Base page"

    def __init__(self, host: Optional[str] = None):
        """
        Initialize page.

        Args:
            host: Device IP (uses RETERMINAL_HOST if not set)
        """
        self.host = host
        self._client: Optional[ReTerminal] = None

    @property
    def client(self) -> ReTerminal:
        """Lazy-loaded ReTerminal client."""
        if self._client is None:
            self._client = ReTerminal(self.host)
        return self._client

    @abstractmethod
    def get_data(self) -> Dict[str, Any]:
        """
        Fetch data needed for the page.

        Returns:
            Dictionary of data to pass to render()
        """
        pass

    @abstractmethod
    def render(self, data: Dict[str, Any]) -> Image.Image:
        """
        Render data to PIL Image.

        Args:
            data: Data from get_data()

        Returns:
            PIL Image in mode "1" (1-bit)
        """
        pass

    def refresh(self, page: Optional[int] = None) -> dict:
        """
        Full refresh cycle: fetch data, render, push to device.

        Args:
            page: Page number to store (0-3), or None for immediate display

        Returns:
            Response from device
        """
        logger.info(f"Refreshing {self.name} page")

        # Fetch data
        logger.debug(f"Fetching data for {self.name}")
        data = self.get_data()

        # Render image
        logger.debug(f"Rendering {self.name}")
        img = self.render(data)

        # Convert to raw and push
        raw = pil_to_raw(img)
        result = self.client.push_raw(raw, page=page)

        logger.info(f"{self.name} page refreshed successfully")
        return result

    @staticmethod
    def create_canvas(background: int = 1) -> Tuple[Image.Image, ImageDraw.Draw]:
        """
        Create a blank canvas for drawing.

        Args:
            background: Background color (1=white, 0=black)

        Returns:
            Tuple of (PIL Image, ImageDraw object)
        """
        img = Image.new("1", (WIDTH, HEIGHT), color=background)
        draw = ImageDraw.Draw(img)
        return img, draw

    @staticmethod
    def load_fonts() -> dict:
        """
        Load standard font family.

        Returns:
            Dict with keys: title, large, medium, small
        """
        return load_font_family()

    @staticmethod
    def add_timestamp(
        draw: ImageDraw.Draw,
        font,
        y: int = None,
        prefix: str = "Updated: ",
    ):
        """
        Add timestamp footer to the image.

        Args:
            draw: ImageDraw object
            font: Font to use
            y: Y position (default: HEIGHT - 50)
            prefix: Text prefix before time
        """
        if y is None:
            y = HEIGHT - 50

        now = datetime.now().strftime("%H:%M")
        draw.text((50, y), f"{prefix}{now}", font=font, fill=0)

    @staticmethod
    def draw_divider(draw: ImageDraw.Draw, y: int, margin: int = 50, width: int = 2):
        """
        Draw a horizontal divider line.

        Args:
            draw: ImageDraw object
            y: Y position
            margin: Left/right margin
            width: Line width
        """
        draw.line([(margin, y), (WIDTH - margin, y)], fill=0, width=width)
