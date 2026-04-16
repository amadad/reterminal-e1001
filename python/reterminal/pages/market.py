"""Market pulse page - VIX, S&P 500, Dow Jones from Schwab API."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TypedDict

from PIL import Image
from loguru import logger

from reterminal.pages import register
from reterminal.pages.base import BasePage


class QuoteSummary(TypedDict):
    price: float
    change: float
    pct: float


MarketPageData = dict[str, QuoteSummary]


def empty_quote() -> QuoteSummary:
    return {"price": 0.0, "change": 0.0, "pct": 0.0}


@register("market", page_number=0)
class MarketPage(BasePage[MarketPageData]):
    """Display market pulse: VIX, S&P 500, Dow Jones."""

    name = "market"
    description = "Market pulse from Schwab API"

    def get_data(self) -> MarketPageData:
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
                data = _parse_market_data(result.stdout.strip())
                logger.debug(f"Market data: VIX={data['$VIX']['price']:.1f}")
                return data
        except (OSError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            logger.error(f"Failed to fetch market data: {exc}")

        return {symbol: empty_quote() for symbol in ("$VIX", "$SPX", "$DJI")}

    def render(self, data: MarketPageData) -> Image.Image:
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        draw.text((50, 30), "MARKET PULSE", font=fonts["title"], fill=0)

        vix = data.get("$VIX", empty_quote())
        vix_price = vix["price"]
        vix_pct = vix["pct"]

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

        spx = data.get("$SPX", empty_quote())
        draw.text((50, 250), "S&P 500", font=fonts["medium"], fill=0)
        draw.text((300, 250), f"{spx['price']:,.0f}", font=fonts["medium"], fill=0)
        draw.text((550, 250), f"{spx['pct']:+.2f}%", font=fonts["medium"], fill=0)

        dji = data.get("$DJI", empty_quote())
        draw.text((50, 310), "DOW", font=fonts["medium"], fill=0)
        draw.text((300, 310), f"{dji['price']:,.0f}", font=fonts["medium"], fill=0)
        draw.text((550, 310), f"{dji['pct']:+.2f}%", font=fonts["medium"], fill=0)

        self.add_timestamp(draw, fonts["small"])
        return img


def _parse_market_data(raw: str) -> MarketPageData:
    parsed = json.loads(raw)
    data: MarketPageData = {}
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("expected object", raw, 0)

    for symbol in ("$VIX", "$SPX", "$DJI"):
        value = parsed.get(symbol)
        if isinstance(value, dict):
            price = value.get("price")
            change = value.get("change")
            pct = value.get("pct")
            data[symbol] = {
                "price": float(price) if isinstance(price, (int, float)) else 0.0,
                "change": float(change) if isinstance(change, (int, float)) else 0.0,
                "pct": float(pct) if isinstance(pct, (int, float)) else 0.0,
            }
        else:
            data[symbol] = empty_quote()
    return data
