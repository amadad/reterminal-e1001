"""Clock page - time and date display."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from PIL import Image

from reterminal.config import WIDTH
from reterminal.pages import register
from reterminal.pages.base import BasePage


class ClockPageData(TypedDict):
    time: str
    weekday: str
    date: str


@register("clock", page_number=1)
class ClockPage(BasePage[ClockPageData]):
    """Display current time and date."""

    name = "clock"
    description = "Time and date display"

    def get_data(self) -> ClockPageData:
        now = datetime.now()
        return {
            "time": now.strftime("%H:%M"),
            "weekday": now.strftime("%A"),
            "date": now.strftime("%B %d, %Y"),
        }

    def render(self, data: ClockPageData) -> Image.Image:
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        time_str = data["time"]
        bbox = draw.textbbox((0, 0), time_str, font=fonts["large"])
        time_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - time_width) // 2, 120), time_str, font=fonts["large"], fill=0)

        bbox = draw.textbbox((0, 0), data["weekday"], font=fonts["medium"])
        weekday_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - weekday_width) // 2, 220), data["weekday"], font=fonts["medium"], fill=0)

        bbox = draw.textbbox((0, 0), data["date"], font=fonts["medium"])
        date_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - date_width) // 2, 280), data["date"], font=fonts["medium"], fill=0)

        return img
