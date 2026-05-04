"""Inject git build metadata into PlatformIO builds."""

from __future__ import annotations

import subprocess
from pathlib import Path

Import("env")  # type: ignore[name-defined]


def _run_git(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _current_build_sha(repo_root: Path) -> str:
    sha = _run_git(repo_root, "rev-parse", "--short=12", "HEAD")
    if sha is None:
        return "unknown"
    dirty = _run_git(repo_root, "status", "--porcelain")
    return f"{sha}-dirty" if dirty else sha


def _without_build_sha(flags):
    if isinstance(flags, str):
        flags = flags.split()
    cleaned = []
    for flag in flags or []:
        if isinstance(flag, str) and flag.startswith("-DRETERMINAL_BUILD_SHA"):
            continue
        cleaned.append(flag)
    return cleaned


repo_root = Path(env.subst("$PROJECT_DIR")).resolve().parent  # noqa: F821
build_sha = _current_build_sha(repo_root)
env.Replace(BUILD_FLAGS=_without_build_sha(env.get("BUILD_FLAGS", [])))  # noqa: F821
env.Append(BUILD_FLAGS=[f'-DRETERMINAL_BUILD_SHA=\\"{build_sha}\\"'])  # noqa: F821
print(f"reTerminal build_sha={build_sha}")
