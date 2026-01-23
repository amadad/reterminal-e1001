"""Portfolio summary page."""

import json
from pathlib import Path
from typing import Any, Dict

from PIL import Image
from loguru import logger

from reterminal.pages.base import BasePage
from reterminal.pages import register
from reterminal.config import WIDTH

SNAPSHOT_DIR = Path.home() / "base/projects/schwab-cli-tools/private/snapshots"


def format_currency(value: float) -> str:
    """Format number as currency."""
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:.1f}K"
    else:
        return f"${value:.0f}"


@register("portfolio", page_number=4)
class PortfolioPage(BasePage):
    """Display portfolio summary from schwab-cli-tools snapshots."""

    name = "portfolio"
    description = "Portfolio summary from schwab-cli-tools"

    def get_data(self) -> Dict[str, Any]:
        """Get latest portfolio snapshot."""
        try:
            snapshots = sorted(SNAPSHOT_DIR.glob("*.json"), reverse=True)
            if snapshots:
                with open(snapshots[0]) as f:
                    data = json.load(f)
                    logger.debug(f"Portfolio: {format_currency(data.get('summary', {}).get('total_value', 0))}")
                    return data
        except Exception as e:
            logger.error(f"Failed to load portfolio snapshot: {e}")

        return {"summary": {}, "date": "No data"}

    def render(self, data: Dict[str, Any]) -> Image.Image:
        """Render portfolio summary to image."""
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        summary = data.get("summary", {})
        total = summary.get("total_value", 0)
        cash = summary.get("total_cash", 0)
        invested = summary.get("total_invested", 0)
        accounts = summary.get("api_account_count", 0)
        positions = summary.get("position_count", 0)
        snapshot_date = data.get("date", "Unknown")

        # Title
        draw.text((50, 30), "PORTFOLIO", font=fonts["title"], fill=0)

        # Total value (large, centered)
        total_str = format_currency(total)
        bbox = draw.textbbox((0, 0), total_str, font=fonts["large"])
        total_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - total_width) // 2, 100), total_str, font=fonts["large"], fill=0)

        self.draw_divider(draw, 200)

        # Details
        y = 230
        draw.text((50, y), f"Cash:     {format_currency(cash)}", font=fonts["medium"], fill=0)
        y += 50
        draw.text((50, y), f"Invested: {format_currency(invested)}", font=fonts["medium"], fill=0)
        y += 50
        draw.text((50, y), f"Accounts: {accounts}  |  Positions: {positions}", font=fonts["small"], fill=0)

        # Date at bottom
        draw.text((50, 430), f"Updated: {snapshot_date}", font=fonts["small"], fill=0)

        return img
