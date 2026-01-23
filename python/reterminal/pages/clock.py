"""Clock page - time and date display."""

from datetime import datetime
from typing import Any, Dict

from PIL import Image
from loguru import logger

from reterminal.pages.base import BasePage
from reterminal.pages import register
from reterminal.config import WIDTH, HEIGHT


@register("clock", page_number=1)
class ClockPage(BasePage):
    """Display current time and date."""

    name = "clock"
    description = "Time and date display"

    def get_data(self) -> Dict[str, Any]:
        """Get current time and date."""
        now = datetime.now()
        return {
            "time": now.strftime("%H:%M"),
            "weekday": now.strftime("%A"),
            "date": now.strftime("%B %d, %Y"),
        }

    def render(self, data: Dict[str, Any]) -> Image.Image:
        """Render clock to image."""
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        # Time (large, centered)
        time_str = data["time"]
        bbox = draw.textbbox((0, 0), time_str, font=fonts["large"])
        time_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - time_width) // 2, 120), time_str, font=fonts["large"], fill=0)

        # Weekday
        bbox = draw.textbbox((0, 0), data["weekday"], font=fonts["medium"])
        weekday_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - weekday_width) // 2, 220), data["weekday"], font=fonts["medium"], fill=0)

        # Date
        bbox = draw.textbbox((0, 0), data["date"], font=fonts["medium"])
        date_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - date_width) // 2, 280), data["date"], font=fonts["medium"], fill=0)

        return img
