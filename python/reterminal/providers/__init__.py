"""Scene providers for the host-rendered display pipeline."""

from reterminal.providers.base import SceneProvider
from reterminal.providers.file_feed import FileSceneProvider
from reterminal.providers.paperclip import PaperclipSceneProvider
from reterminal.providers.system import SystemSceneProvider

__all__ = ["SceneProvider", "FileSceneProvider", "PaperclipSceneProvider", "SystemSceneProvider"]
