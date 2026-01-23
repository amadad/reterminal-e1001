"""GitHub activity page."""

import subprocess
import json
from typing import Any, Dict

from PIL import Image
from loguru import logger

from reterminal.pages.base import BasePage
from reterminal.pages import register


@register("github", page_number=2)
class GitHubPage(BasePage):
    """Display GitHub activity and stats."""

    name = "github"
    description = "GitHub activity from gh CLI"

    def get_data(self) -> Dict[str, Any]:
        """Fetch GitHub stats via gh CLI."""
        data = {"user": "amadad", "repos": 0, "followers": 0, "recent": []}

        try:
            # Get user stats
            result = subprocess.run(
                ["gh", "api", "users/amadad", "--jq", "{public_repos, followers}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                stats = json.loads(result.stdout)
                data["repos"] = stats.get("public_repos", 0)
                data["followers"] = stats.get("followers", 0)

            # Get recent activity
            result = subprocess.run(
                ["gh", "api", "users/amadad/events", "--jq", '.[0:3] | .[] | "\\(.type)|\\(.repo.name)"'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if "|" in line:
                        event_type, repo = line.split("|", 1)
                        event_type = event_type.replace("Event", "")
                        repo = repo.split("/")[-1] if "/" in repo else repo
                        data["recent"].append({"type": event_type, "repo": repo})

            logger.debug(f"GitHub: {data['repos']} repos, {data['followers']} followers")
        except Exception as e:
            logger.error(f"Failed to fetch GitHub data: {e}")

        return data

    def render(self, data: Dict[str, Any]) -> Image.Image:
        """Render GitHub stats to image."""
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        # Title
        draw.text((50, 30), "GITHUB", font=fonts["title"], fill=0)

        # Username
        draw.text((50, 90), f"@{data['user']}", font=fonts["large"], fill=0)

        # Stats
        draw.text((50, 170), f"{data['repos']} repos", font=fonts["medium"], fill=0)
        draw.text((300, 170), f"{data['followers']} followers", font=fonts["medium"], fill=0)

        self.draw_divider(draw, 230)

        # Recent activity
        draw.text((50, 250), "Recent Activity", font=fonts["medium"], fill=0)

        y = 300
        for activity in data["recent"][:3]:
            draw.text((50, y), f"{activity['type']}: {activity['repo']}", font=fonts["small"], fill=0)
            y += 40

        self.add_timestamp(draw, fonts["small"])
        return img
