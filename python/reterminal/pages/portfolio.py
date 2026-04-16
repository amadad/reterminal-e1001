"""Portfolio summary page."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from PIL import Image
from loguru import logger

from reterminal.config import WIDTH
from reterminal.pages import register
from reterminal.pages.base import BasePage

SNAPSHOT_DIR = Path.home() / "base/projects/schwab-cli-tools/private/snapshots"


class PortfolioSummary(TypedDict, total=False):
    total_value: float
    total_cash: float
    total_invested: float
    api_account_count: int
    position_count: int


class PortfolioPageData(TypedDict):
    summary: PortfolioSummary
    date: str


def format_currency(value: float) -> str:
    """Format number as currency."""
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value/1_000:.1f}K"
    return f"${value:.0f}"


@register("portfolio", page_number=4)
class PortfolioPage(BasePage[PortfolioPageData]):
    """Display portfolio summary from schwab-cli-tools snapshots."""

    name = "portfolio"
    description = "Portfolio summary from schwab-cli-tools"

    def get_data(self) -> PortfolioPageData:
        try:
            snapshots = sorted(SNAPSHOT_DIR.glob("*.json"), reverse=True)
            if snapshots:
                with snapshots[0].open() as handle:
                    data = _parse_portfolio_data(json.load(handle))
                    logger.debug(
                        f"Portfolio: {format_currency(data['summary'].get('total_value', 0.0))}"
                    )
                    return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(f"Failed to load portfolio snapshot: {exc}")

        return {"summary": {}, "date": "No data"}

    def render(self, data: PortfolioPageData) -> Image.Image:
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        summary = data["summary"]
        total = summary.get("total_value", 0.0)
        cash = summary.get("total_cash", 0.0)
        invested = summary.get("total_invested", 0.0)
        accounts = summary.get("api_account_count", 0)
        positions = summary.get("position_count", 0)
        snapshot_date = data["date"]

        draw.text((50, 30), "PORTFOLIO", font=fonts["title"], fill=0)

        total_str = format_currency(total)
        bbox = draw.textbbox((0, 0), total_str, font=fonts["large"])
        total_width = bbox[2] - bbox[0]
        draw.text(((WIDTH - total_width) // 2, 100), total_str, font=fonts["large"], fill=0)

        self.draw_divider(draw, 200)

        y = 230
        draw.text((50, y), f"Cash:     {format_currency(cash)}", font=fonts["medium"], fill=0)
        y += 50
        draw.text((50, y), f"Invested: {format_currency(invested)}", font=fonts["medium"], fill=0)
        y += 50
        draw.text((50, y), f"Accounts: {accounts}  |  Positions: {positions}", font=fonts["small"], fill=0)
        draw.text((50, 430), f"Updated: {snapshot_date}", font=fonts["small"], fill=0)

        return img


def _parse_portfolio_data(raw: object) -> PortfolioPageData:
    if not isinstance(raw, dict):
        return {"summary": {}, "date": "Unknown"}

    summary_raw = raw.get("summary")
    summary: PortfolioSummary = {}
    if isinstance(summary_raw, dict):
        total_value = summary_raw.get("total_value")
        total_cash = summary_raw.get("total_cash")
        total_invested = summary_raw.get("total_invested")
        api_account_count = summary_raw.get("api_account_count")
        position_count = summary_raw.get("position_count")

        if isinstance(total_value, (int, float)):
            summary["total_value"] = float(total_value)
        if isinstance(total_cash, (int, float)):
            summary["total_cash"] = float(total_cash)
        if isinstance(total_invested, (int, float)):
            summary["total_invested"] = float(total_invested)
        if isinstance(api_account_count, int):
            summary["api_account_count"] = api_account_count
        if isinstance(position_count, int):
            summary["position_count"] = position_count

    date_value = raw.get("date")
    return {
        "summary": summary,
        "date": str(date_value) if date_value is not None else "Unknown",
    }
