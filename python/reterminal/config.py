"""Configuration management using environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv

_env_paths = [
    Path(__file__).parent.parent / ".env",
    Path.cwd() / ".env",
]
for env_path in _env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break

WIDTH = 800
HEIGHT = 480
IMAGE_BYTES = WIDTH * HEIGHT // 8  # 48000 bytes


@dataclass
class Settings:
    """Application settings from environment variables."""

    host: str
    timeout: int
    log_level: str
    retry_attempts: int
    retry_min_wait: float
    retry_max_wait: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("RETERMINAL_HOST", "").strip(),
            timeout=int(os.getenv("RETERMINAL_TIMEOUT", "30")),
            log_level=os.getenv("RETERMINAL_LOG_LEVEL", "INFO"),
            retry_attempts=int(os.getenv("RETERMINAL_RETRY_ATTEMPTS", "3")),
            retry_min_wait=float(os.getenv("RETERMINAL_RETRY_MIN_WAIT", "1")),
            retry_max_wait=float(os.getenv("RETERMINAL_RETRY_MAX_WAIT", "10")),
        )


settings = Settings.from_env()


def get_host(override: str | None = None) -> str:
    host = (override or settings.host).strip()
    if not host:
        raise ValueError("Set RETERMINAL_HOST or pass --host with the device IP")
    return host
