"""Helpers for building scene-provider lists."""

from __future__ import annotations

from pathlib import Path

from reterminal.providers.base import SceneProvider
from reterminal.providers.file_feed import FileSceneProvider
from reterminal.providers.paperclip import PaperclipSceneProvider
from reterminal.providers.system import SystemSceneProvider


def build_scene_providers(
    *,
    feed: Path | None = None,
    paperclip_url: str | None = None,
    include_system: bool = True,
) -> list[SceneProvider]:
    """Build the ordered provider list for doctor/publish flows."""
    providers: list[SceneProvider] = []
    if feed is not None:
        providers.append(FileSceneProvider(feed))
    if paperclip_url is not None:
        providers.append(PaperclipSceneProvider(paperclip_url))
    if include_system:
        providers.append(SystemSceneProvider())
    return providers
