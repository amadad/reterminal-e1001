"""Scene provider backed by a local JSON feed file."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from reterminal.payloads import JSONValue
from reterminal.scenes import SceneSpec


class FileSceneProvider:
    """Load scenes from a JSON document.

    Expected format:

    {
      "scenes": [
        {
          "id": "agent-overview",
          "kind": "hero",
          "title": "Agents online",
          "priority": 90,
          "body": ["orb shipping", "kara reviewing"]
        }
      ]
    }
    """

    name = "file"

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            raise FileNotFoundError(f"Feed file not found: {self.path}")

        data: JSONValue = json.loads(self.path.read_text())
        scenes_data = self._extract_scenes(data)
        return [SceneSpec.from_dict(item, base_dir=self.path.parent) for item in scenes_data]

    @staticmethod
    def _extract_scenes(data: JSONValue) -> list[Mapping[str, JSONValue]]:
        if isinstance(data, Mapping):
            scenes = data.get("scenes")
            if isinstance(scenes, list):
                return [item for item in scenes if isinstance(item, Mapping)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, Mapping)]
        raise ValueError("Feed JSON must be a list of scenes or an object with a 'scenes' list")
