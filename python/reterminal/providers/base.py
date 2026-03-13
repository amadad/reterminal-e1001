"""Provider interfaces for scene sources."""

from __future__ import annotations

from typing import Protocol

from reterminal.scenes import SceneSpec


class SceneProvider(Protocol):
    """A source of logical scenes for the display scheduler."""

    name: str

    def fetch(self) -> list[SceneSpec]:
        """Return available scenes ordered by provider preference."""
