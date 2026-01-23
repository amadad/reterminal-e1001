"""Market pulse page - VIX, S&P 500, Dow Jones from Schwab API."""

import subprocess
import json
from pathlib import Path
from typing import Any, Dict

from PIL import Image
from loguru import logger

from reterminal.pages.base import BasePage
from reterminal.pages import register


@register("market", page_number=0)
class MarketPage(BasePage):
    """Display market pulse: VIX, S&P 500, Dow Jones."""

    name = "market"
    description = "Market pulse from Schwab API"

    def get_data(self) -> Dict[str, Any]:
        """Fetch market data from Schwab via schwab-cli-tools."""
        script = '''
from src.schwab_client import get_authenticated_client
import json

client = get_authenticated_client()
resp = client.get_quotes("$SPX,$DJI,$VIX")

if resp.status_code == 200:
    data = resp.json()
    result = {}
    for sym in ["$SPX", "$DJI", "$VIX"]:
        q = data.get(sym, {}).get("quote", {})
        result[sym] = {
            "price": q.get("lastPrice", q.get("closePrice", 0)),
            "change": q.get("netChange", 0),
            "pct": q.get("netPercentChange", 0)
        }
    print(json.dumps(result))
'''
        try:
            result = subprocess.run(
                ["uv", "run", "python", "-c", script],
                cwd=Path.home() / "base/projects/schwab-cli-tools",
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout.strip())
                logger.debug(f"Market data: VIX={data['$VIX']['price']:.1f}")
                return data
        except Exception as e:
            logger.error(f"Failed to fetch market data: {e}")

        return {"$VIX": {}, "$SPX": {}, "$DJI": {}}

    def render(self, data: Dict[str, Any]) -> Image.Image:
        """Render market data to image."""
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        # Title
        draw.text((50, 30), "MARKET PULSE", font=fonts["title"], fill=0)

        # VIX
        vix = data.get("$VIX", {})
        vix_price = vix.get("price", 0)
        vix_pct = vix.get("pct", 0)

        # VIX interpretation
        if vix_price < 15:
            vix_mood = "LOW FEAR"
        elif vix_price < 20:
            vix_mood = "NORMAL"
        elif vix_price < 30:
            vix_mood = "ELEVATED"
        else:
            vix_mood = "HIGH FEAR"

        draw.text((50, 100), "VIX", font=fonts["medium"], fill=0)
        draw.text((50, 140), f"{vix_price:.1f}", font=fonts["large"], fill=0)
        draw.text((250, 160), f"{vix_pct:+.1f}%  {vix_mood}", font=fonts["medium"], fill=0)

        self.draw_divider(draw, 220)

        # S&P 500
        spx = data.get("$SPX", {})
        draw.text((50, 250), "S&P 500", font=fonts["medium"], fill=0)
        draw.text((300, 250), f"{spx.get('price', 0):,.0f}", font=fonts["medium"], fill=0)
        draw.text((550, 250), f"{spx.get('pct', 0):+.2f}%", font=fonts["medium"], fill=0)

        # Dow Jones
        dji = data.get("$DJI", {})
        draw.text((50, 310), "DOW", font=fonts["medium"], fill=0)
        draw.text((300, 310), f"{dji.get('price', 0):,.0f}", font=fonts["medium"], fill=0)
        draw.text((550, 310), f"{dji.get('pct', 0):+.2f}%", font=fonts["medium"], fill=0)

        self.add_timestamp(draw, fonts["small"])
        return img
