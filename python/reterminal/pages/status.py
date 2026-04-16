"""System and clawdbot status page."""

from __future__ import annotations

import subprocess
from typing import TypedDict

from PIL import Image
from loguru import logger

from reterminal.pages import register
from reterminal.pages.base import BasePage


class StatusPageData(TypedDict):
    hostname: str
    clawdbot: str
    telegram: str
    uptime: str


@register("status", page_number=3)
class StatusPage(BasePage[StatusPageData]):
    """Display system and clawdbot status."""

    name = "status"
    description = "System and clawdbot status"

    def get_data(self) -> StatusPageData:
        data: StatusPageData = {
            "hostname": "unknown",
            "clawdbot": "unknown",
            "telegram": "unknown",
            "uptime": "unknown",
        }

        try:
            result = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                data["hostname"] = result.stdout.strip()

            result = subprocess.run(
                ["clawdbot", "health"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                output = result.stdout
                if "Telegram: ok" in output:
                    for line in output.split("\n"):
                        if "Telegram:" in line and "@" in line:
                            data["telegram"] = line.split("(")[1].split(")")[0] if "(" in line else "connected"
                            break
                    data["clawdbot"] = "running"
                else:
                    data["clawdbot"] = "running"
            else:
                data["clawdbot"] = "stopped"

            result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                uptime = result.stdout.strip()
                if "up" in uptime:
                    data["uptime"] = uptime.split("up")[1].split(",")[0].strip()

            logger.debug(f"Status: {data['hostname']}, clawdbot={data['clawdbot']}")
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(f"Failed to fetch status: {exc}")

        return data

    def render(self, data: StatusPageData) -> Image.Image:
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        draw.text((50, 30), "STATUS", font=fonts["title"], fill=0)
        draw.text((50, 90), data["hostname"], font=fonts["large"], fill=0)

        self.draw_divider(draw, 160)

        y = 190
        draw.text((50, y), f"Clawdbot: {data['clawdbot']}", font=fonts["medium"], fill=0)
        y += 50
        draw.text((50, y), f"Telegram: {data['telegram']}", font=fonts["medium"], fill=0)
        y += 50
        draw.text((50, y), f"Uptime: {data['uptime']}", font=fonts["medium"], fill=0)
        y += 50
        draw.text((50, y), f"Display: {self.host or 'default'}", font=fonts["medium"], fill=0)

        self.add_timestamp(draw, fonts["small"])
        return img
