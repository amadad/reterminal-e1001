"""Scene providers for the host-rendered display pipeline."""

from reterminal.providers.base import SceneProvider
from reterminal.providers.factory import build_scene_providers
from reterminal.providers.file_feed import FileSceneProvider
from reterminal.providers.manifest import (
    FeedManifest,
    ProviderEntry,
    build_providers,
    is_manifest_shape,
    load_manifest,
    register_provider,
)
from reterminal.providers.paperclip import PaperclipSceneProvider
from reterminal.providers.system import SystemSceneProvider

# Importing these registers their factories with the manifest registry.
# Order does not matter; each module calls register_provider() at import time.
from reterminal.providers import activities as _activities  # noqa: F401
from reterminal.providers import calendar as _calendar  # noqa: F401
from reterminal.providers import events as _events  # noqa: F401
from reterminal.providers import missions as _missions  # noqa: F401

__all__ = [
    "SceneProvider",
    "FileSceneProvider",
    "PaperclipSceneProvider",
    "SystemSceneProvider",
    "build_scene_providers",
    "FeedManifest",
    "ProviderEntry",
    "build_providers",
    "is_manifest_shape",
    "load_manifest",
    "register_provider",
]
