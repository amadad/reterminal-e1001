"""Simple dashboard page - system info.

Note: This file fixes the pixel inversion bug from the original dashboard.py.
The original had `if pixels[x, y]:` which is inverted - should be `if not pixels[x, y]:`.
This is now handled correctly by the shared pil_to_raw() function.
"""

import subprocess
from datetime import datetime
from typing import Any, Dict

from PIL import Image
from loguru import logger

from reterminal.pages.base import BasePage
from reterminal.pages import register
from reterminal.config import WIDTH


@register("dashboard", page_number=5)
class DashboardPage(BasePage):
    """Display simple system dashboard."""

    name = "dashboard"
    description = "Simple system dashboard"

    def get_data(self) -> Dict[str, Any]:
        """Gather system information."""
        info = {
            "hostname": "unknown",
            "load": "N/A",
            "time": datetime.now().strftime("%H:%M"),
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

        try:
            # Hostname
            result = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                info["hostname"] = result.stdout.strip()

            # Load average
            result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                uptime = result.stdout.strip()
                if "load average" in uptime:
                    info["load"] = uptime.split("load average:")[-1].strip()

            logger.debug(f"Dashboard: {info['hostname']}, load={info['load']}")
        except Exception as e:
            logger.error(f"Failed to gather system info: {e}")

        return info

    def render(self, data: Dict[str, Any]) -> Image.Image:
        """Render dashboard to image."""
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        # Time (large, centered)
        time_bbox = draw.textbbox((0, 0), data["time"], font=fonts["large"])
        time_width = time_bbox[2] - time_bbox[0]
        draw.text(((WIDTH - time_width) // 2, 60), data["time"], font=fonts["large"], fill=0)

        # Date
        date_bbox = draw.textbbox((0, 0), data["date"], font=fonts["medium"])
        date_width = date_bbox[2] - date_bbox[0]
        draw.text(((WIDTH - date_width) // 2, 160), data["date"], font=fonts["medium"], fill=0)

        self.draw_divider(draw, 220)

        # Hostname
        draw.text((50, 260), f"Host: {data['hostname']}", font=fonts["small"], fill=0)

        # Load
        draw.text((50, 300), f"Load: {data['load']}", font=fonts["small"], fill=0)

        return img
