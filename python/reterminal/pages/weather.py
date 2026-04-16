"""Weather page - current conditions from Open-Meteo API (no key required)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TypedDict

from PIL import Image
from loguru import logger

from reterminal.config import WIDTH
from reterminal.pages import register
from reterminal.pages.base import BasePage

DEFAULT_LAT = 37.7749
DEFAULT_LON = -122.4194


class WeatherPageData(TypedDict):
    temp: float
    humidity: int
    wind: float
    code: int
    condition: str
    location: str


def get_weather_emoji(code: int) -> str:
    """Convert WMO weather code to simple description."""
    if code == 0:
        return "Clear"
    if code in [1, 2, 3]:
        return "Cloudy"
    if code in [45, 48]:
        return "Fog"
    if code in [51, 53, 55, 56, 57]:
        return "Drizzle"
    if code in [61, 63, 65, 66, 67]:
        return "Rain"
    if code in [71, 73, 75, 77]:
        return "Snow"
    if code in [80, 81, 82]:
        return "Showers"
    if code in [85, 86]:
        return "Snow"
    if code in [95, 96, 99]:
        return "Storm"
    return "Unknown"


@register("weather", page_number=6)
class WeatherPage(BasePage[WeatherPageData]):
    """Display current weather conditions."""

    name = "weather"
    description = "Weather from Open-Meteo API"

    def __init__(self, host: str | None = None, lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON):
        super().__init__(host)
        self.lat = lat
        self.lon = lon

    def get_data(self) -> WeatherPageData:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={self.lat}&longitude={self.lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
            f"&timezone=auto"
        )

        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                raw_data = json.loads(response.read())
                current = raw_data.get("current", {}) if isinstance(raw_data, dict) else {}
                temperature = current.get("temperature_2m") if isinstance(current, dict) else None
                humidity = current.get("relative_humidity_2m") if isinstance(current, dict) else None
                wind = current.get("wind_speed_10m") if isinstance(current, dict) else None
                code = current.get("weather_code") if isinstance(current, dict) else None
                weather_code = code if isinstance(code, int) else 0
                return {
                    "temp": float(temperature) if isinstance(temperature, (int, float)) else 0.0,
                    "humidity": int(humidity) if isinstance(humidity, (int, float)) else 0,
                    "wind": float(wind) if isinstance(wind, (int, float)) else 0.0,
                    "code": weather_code,
                    "condition": get_weather_emoji(weather_code),
                    "location": f"{self.lat:.2f}, {self.lon:.2f}",
                }
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            logger.error(f"Failed to fetch weather: {exc}")
            return {
                "temp": 0.0,
                "humidity": 0,
                "wind": 0.0,
                "code": 0,
                "condition": "Error",
                "location": "Unknown",
            }

    def render(self, data: WeatherPageData) -> Image.Image:
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        draw.text((50, 30), "WEATHER", font=fonts["title"], fill=0)

        temp_str = f"{data['temp']:.0f}°F"
        bbox = draw.textbbox((0, 0), temp_str, font=fonts["large"])
        temp_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - temp_width) // 2, 100), temp_str, font=fonts["large"], fill=0)

        bbox = draw.textbbox((0, 0), data["condition"], font=fonts["medium"])
        cond_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - cond_width) // 2, 180), data["condition"], font=fonts["medium"], fill=0)

        self.draw_divider(draw, 240)
        draw.text((50, 270), f"Humidity: {data['humidity']}%", font=fonts["medium"], fill=0)
        draw.text((50, 320), f"Wind: {data['wind']:.0f} mph", font=fonts["medium"], fill=0)
        draw.text((50, 430), data["location"], font=fonts["small"], fill=0)

        return img
