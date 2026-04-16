"""GitHub activity page."""

from __future__ import annotations

import json
import subprocess
from typing import TypedDict

from PIL import Image
from loguru import logger

from reterminal.pages import register
from reterminal.pages.base import BasePage


class RecentActivity(TypedDict):
    type: str
    repo: str


class GitHubPageData(TypedDict):
    user: str
    repos: int
    followers: int
    recent: list[RecentActivity]


@register("github", page_number=2)
class GitHubPage(BasePage[GitHubPageData]):
    """Display GitHub activity and stats."""

    name = "github"
    description = "GitHub activity from gh CLI"

    def get_data(self) -> GitHubPageData:
        data: GitHubPageData = {"user": "amadad", "repos": 0, "followers": 0, "recent": []}

        try:
            result = subprocess.run(
                ["gh", "api", "users/amadad", "--jq", "{public_repos, followers}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                stats = json.loads(result.stdout)
                if isinstance(stats, dict):
                    public_repos = stats.get("public_repos")
                    followers = stats.get("followers")
                    if isinstance(public_repos, int):
                        data["repos"] = public_repos
                    if isinstance(followers, int):
                        data["followers"] = followers

            result = subprocess.run(
                ["gh", "api", "users/amadad/events", "--jq", '.[0:3] | .[] | "\\(.type)|\\(.repo.name)"'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if "|" not in line:
                        continue
                    event_type, repo = line.split("|", 1)
                    repo_name = repo.split("/")[-1] if "/" in repo else repo
                    data["recent"].append({"type": event_type.replace("Event", ""), "repo": repo_name})

            logger.debug(f"GitHub: {data['repos']} repos, {data['followers']} followers")
        except (OSError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            logger.error(f"Failed to fetch GitHub data: {exc}")

        return data

    def render(self, data: GitHubPageData) -> Image.Image:
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        draw.text((50, 30), "GITHUB", font=fonts["title"], fill=0)
        draw.text((50, 90), f"@{data['user']}", font=fonts["large"], fill=0)
        draw.text((50, 170), f"{data['repos']} repos", font=fonts["medium"], fill=0)
        draw.text((300, 170), f"{data['followers']} followers", font=fonts["medium"], fill=0)

        self.draw_divider(draw, 230)
        draw.text((50, 250), "Recent Activity", font=fonts["medium"], fill=0)

        y = 300
        for activity in data["recent"][:3]:
            draw.text((50, y), f"{activity['type']}: {activity['repo']}", font=fonts["small"], fill=0)
            y += 40

        self.add_timestamp(draw, fonts["small"])
        return img
