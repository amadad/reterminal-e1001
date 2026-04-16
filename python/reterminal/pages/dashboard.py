"""Simple dashboard page with local system information."""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import TypedDict

from PIL import Image
from loguru import logger

from reterminal.config import WIDTH
from reterminal.pages import register
from reterminal.pages.base import BasePage


class DashboardPageData(TypedDict):
    hostname: str
    load: str
    time: str
    date: str


@register("dashboard", page_number=5)
class DashboardPage(BasePage[DashboardPageData]):
    """Display simple system dashboard."""

    name = "dashboard"
    description = "Simple system dashboard"

    def get_data(self) -> DashboardPageData:
        info: DashboardPageData = {
            "hostname": "unknown",
            "load": "N/A",
            "time": datetime.now().strftime("%H:%M"),
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

        try:
            result = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                info["hostname"] = result.stdout.strip()

            result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                uptime = result.stdout.strip()
                if "load average" in uptime:
                    info["load"] = uptime.split("load average:")[-1].strip()

            logger.debug(f"Dashboard: {info['hostname']}, load={info['load']}")
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(f"Failed to gather system info: {exc}")

        return info

    def render(self, data: DashboardPageData) -> Image.Image:
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        time_bbox = draw.textbbox((0, 0), data["time"], font=fonts["large"])
        time_width = time_bbox[2] - time_bbox[0]
        draw.text(((WIDTH - time_width) // 2, 60), data["time"], font=fonts["large"], fill=0)

        date_bbox = draw.textbbox((0, 0), data["date"], font=fonts["medium"])
        date_width = date_bbox[2] - date_bbox[0]
        draw.text(((WIDTH - date_width) // 2, 160), data["date"], font=fonts["medium"], fill=0)

        self.draw_divider(draw, 220)
        draw.text((50, 260), f"Host: {data['hostname']}", font=fonts["small"], fill=0)
        draw.text((50, 300), f"Load: {data['load']}", font=fonts["small"], fill=0)
        return img
