"""Weather page - current conditions from Open-Meteo API (no key required)."""

import urllib.request
import json
from typing import Any, Dict

from PIL import Image
from loguru import logger

from reterminal.pages.base import BasePage
from reterminal.pages import register
from reterminal.config import WIDTH


# Default location (San Francisco)
DEFAULT_LAT = 37.7749
DEFAULT_LON = -122.4194


def get_weather_emoji(code: int) -> str:
    """Convert WMO weather code to simple description."""
    if code == 0:
        return "Clear"
    elif code in [1, 2, 3]:
        return "Cloudy"
    elif code in [45, 48]:
        return "Fog"
    elif code in [51, 53, 55, 56, 57]:
        return "Drizzle"
    elif code in [61, 63, 65, 66, 67]:
        return "Rain"
    elif code in [71, 73, 75, 77]:
        return "Snow"
    elif code in [80, 81, 82]:
        return "Showers"
    elif code in [85, 86]:
        return "Snow"
    elif code in [95, 96, 99]:
        return "Storm"
    return "Unknown"


@register("weather", page_number=6)
class WeatherPage(BasePage):
    """Display current weather conditions."""

    name = "weather"
    description = "Weather from Open-Meteo API"

    def __init__(self, host=None, lat=DEFAULT_LAT, lon=DEFAULT_LON):
        super().__init__(host)
        self.lat = lat
        self.lon = lon

    def get_data(self) -> Dict[str, Any]:
        """Fetch weather from Open-Meteo (free, no API key)."""
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={self.lat}&longitude={self.lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
            f"&timezone=auto"
        )

        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read())
                current = data.get("current", {})
                return {
                    "temp": current.get("temperature_2m", 0),
                    "humidity": current.get("relative_humidity_2m", 0),
                    "wind": current.get("wind_speed_10m", 0),
                    "code": current.get("weather_code", 0),
                    "condition": get_weather_emoji(current.get("weather_code", 0)),
                    "location": f"{self.lat:.2f}, {self.lon:.2f}",
                }
        except Exception as e:
            logger.error(f"Failed to fetch weather: {e}")
            return {"temp": 0, "humidity": 0, "wind": 0, "code": 0, "condition": "Error", "location": "Unknown"}

    def render(self, data: Dict[str, Any]) -> Image.Image:
        """Render weather to image."""
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        # Title
        draw.text((50, 30), "WEATHER", font=fonts["title"], fill=0)

        # Temperature (large, centered)
        temp_str = f"{data['temp']:.0f}°F"
        bbox = draw.textbbox((0, 0), temp_str, font=fonts["large"])
        temp_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - temp_width) // 2, 100), temp_str, font=fonts["large"], fill=0)

        # Condition
        bbox = draw.textbbox((0, 0), data["condition"], font=fonts["medium"])
        cond_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - cond_width) // 2, 180), data["condition"], font=fonts["medium"], fill=0)

        self.draw_divider(draw, 240)

        # Details
        draw.text((50, 270), f"Humidity: {data['humidity']}%", font=fonts["medium"], fill=0)
        draw.text((50, 320), f"Wind: {data['wind']:.0f} mph", font=fonts["medium"], fill=0)

        # Location
        draw.text((50, 430), data["location"], font=fonts["small"], fill=0)

        return img
