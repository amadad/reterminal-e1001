"""Built-in provider for local system-oriented scenes."""

from __future__ import annotations

import socket
from datetime import datetime

from reterminal.scenes import Metric, SceneSpec


class SystemSceneProvider:
    """Provide a simple ambient scene for demos and default operation."""

    name = "system"

    def fetch(self) -> list[SceneSpec]:
        now = datetime.now()
        return [
            SceneSpec(
                id="system-now",
                kind="hero",
                title=now.strftime("%H:%M"),
                subtitle=now.strftime("%A • %B %d"),
                priority=10,
                metric=Metric(label="Host", value=socket.gethostname()),
                body=[
                    "Host-rendered scene pipeline",
                    "4-slot hardware scheduler",
                ],
                footer="system provider",
            )
        ]
