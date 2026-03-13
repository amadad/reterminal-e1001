"""Paperclip-ready provider that fetches a remote scene feed over HTTP."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

from reterminal.providers.file_feed import FileSceneProvider
from reterminal.scenes import SceneSpec


class PaperclipSceneProvider:
    """Fetch a scene feed from a remote Paperclip-compatible HTTP endpoint.

    The endpoint is expected to return the same JSON scene format as FileSceneProvider.
    """

    name = "paperclip"

    def __init__(self, url: str, *, token: Optional[str] = None, token_env: str = "PAPERCLIP_TOKEN"):
        self.url = url
        self.token = token
        self.token_env = token_env

    def fetch(self) -> list[SceneSpec]:
        request = urllib.request.Request(self.url)
        token = self.token or os.getenv(self.token_env)
        if token:
            request.add_header("Authorization", f"Bearer {token}")

        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
        scenes_data = FileSceneProvider._extract_scenes(payload)
        return [SceneSpec.from_dict(item) for item in scenes_data]
