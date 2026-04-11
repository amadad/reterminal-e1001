#!/usr/bin/env python3
"""Smoke-test the installed reterminal CLI from outside the source tree."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_FEED = REPO_ROOT / "python" / "examples" / "agent-feed.json"


def run(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"Command failed ({result.returncode}): {' '.join(command)}\n\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )
    return result.stdout


def load_json(command: list[str], *, cwd: Path) -> dict:
    stdout = run(command, cwd=cwd)
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Expected JSON output, got:\n{stdout}") from exc


def main() -> int:
    cli = shutil.which("reterminal")
    if not cli:
        raise SystemExit("`reterminal` is not on PATH. Install it first with `uv tool install -e ./python` or `pipx install ./python`.")

    with tempfile.TemporaryDirectory(prefix="reterminal-agent-cli-") as temp_dir:
        cwd = Path(temp_dir)
        preview_file = cwd / "preview.png"
        preview_dir = cwd / "previews"

        run([cli, "--help"], cwd=cwd)
        load_json([cli, "config", "--output", "json"], cwd=cwd)
        load_json([cli, "discover", "--output", "json", "--timeout", "0.2"], cwd=cwd)

        push_payload = load_json(
            [cli, "push", "--text", "hello", "--preview", str(preview_file), "--output", "json"],
            cwd=cwd,
        )
        assert push_payload["preview_path"] == str(preview_file)
        assert preview_file.exists()

        publish_payload = load_json(
            [
                cli,
                "publish",
                "--feed",
                str(EXAMPLE_FEED),
                "--preview",
                str(preview_dir),
                "--output",
                "json",
            ],
            cwd=cwd,
        )
        assert publish_payload["mode"] == "preview"
        assert publish_payload["preview_paths"]

        print("reterminal agent CLI verification passed")
        print(f"verified from: {cwd}")
        print(f"preview file: {preview_file}")
        print(f"publish previews: {preview_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
