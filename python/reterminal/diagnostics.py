"""Discovery and doctor helpers for operating reTerminal devices."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
from time import perf_counter

import requests

from reterminal.app import DisplayPublisher
from reterminal.config import settings
from reterminal.device import DeviceCapabilities, ReTerminalDevice
from reterminal.payloads import PageInfoPayload, StatusPayload
from reterminal.providers import build_providers, build_scene_providers, is_manifest_shape, load_manifest
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler


@dataclass(slots=True)
class DiscoveryResult:
    """Reachability result for one discovery target."""

    target: str
    reachable: bool
    status: StatusPayload | None = None
    page_info: PageInfoPayload | None = None
    error: str | None = None
    latency_ms: int | None = None


@dataclass(slots=True)
class DoctorReport:
    """Structured operational health report for one device target."""

    configured_host: str | None
    resolved_host: str | None = None
    reachable: bool = False
    capabilities: DeviceCapabilities | None = None
    scene_count: int = 0
    assignment_count: int = 0
    repo_build_sha: str | None = None
    firmware_match: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


DEFAULT_DISCOVERY_HOSTNAMES = ("reterminal.local", "reterminal")


def current_repo_sha(repo_root: Path | None = None) -> str | None:
    """Return the current git commit SHA when running from a checkout."""
    root = repo_root or Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    if not sha:
        return None
    return f"{sha}-dirty" if status.stdout.strip() else sha


def firmware_match_status(caps: DeviceCapabilities, repo_sha: str | None = None) -> str:
    """Compare firmware-reported build SHA with the current checkout.

    Returns one of: match, mismatch, unknown.
    """
    build_sha = (caps.build_sha or "").strip()
    if not build_sha or build_sha == "unknown":
        return "unknown"
    if repo_sha is None:
        return "unknown"
    if build_sha.endswith("-dirty") or repo_sha.endswith("-dirty"):
        return "match" if build_sha == repo_sha else "mismatch"
    return "match" if repo_sha.startswith(build_sha) or build_sha.startswith(repo_sha) else "mismatch"


def build_discovery_candidates(
    configured_host: str | None = None,
    *,
    candidates: list[str] | None = None,
    hostnames: list[str] | None = None,
    subnet: str | None = None,
    start: int = 1,
    end: int = 254,
) -> list[str]:
    """Build a deduplicated discovery candidate list."""
    ordered: list[str] = []

    def add(value: str | None) -> None:
        if value is None:
            return
        normalized = value.strip()
        if normalized and normalized not in ordered:
            ordered.append(normalized)

    add(configured_host)
    for value in candidates or []:
        add(value)
    for hostname in hostnames or list(DEFAULT_DISCOVERY_HOSTNAMES):
        add(hostname)
    if subnet:
        for last_octet in range(start, end + 1):
            add(f"{subnet}.{last_octet}")

    return ordered


def _get_json(url: str, timeout: float) -> dict:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (requests.Timeout, requests.ConnectionError):
        result = subprocess.run(
            ["curl", "-fsS", "--max-time", str(timeout), url],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
            check=True,
        )
        return json.loads(result.stdout)


def probe_candidate(target: str, timeout: float = 1.5) -> DiscoveryResult:
    """Probe one candidate host without the normal retry budget."""
    started = perf_counter()
    status_url = f"http://{target}/status"
    page_url = f"http://{target}/page"

    try:
        status = _get_json(status_url, timeout)
        page_info = _get_json(page_url, timeout)
        latency_ms = int((perf_counter() - started) * 1000)
        return DiscoveryResult(
            target=target,
            reachable=True,
            status=status,
            page_info=page_info,
            latency_ms=latency_ms,
        )
    except (requests.RequestException, ValueError, subprocess.SubprocessError) as exc:
        latency_ms = int((perf_counter() - started) * 1000)
        return DiscoveryResult(
            target=target,
            reachable=False,
            error=str(exc),
            latency_ms=latency_ms,
        )


def discover_hosts(
    candidates: list[str],
    *,
    timeout: float = 1.5,
    workers: int = 16,
    include_unreachable: bool = False,
) -> list[DiscoveryResult]:
    """Probe candidate hosts in parallel and return ordered results."""
    indexed_results: dict[int, DiscoveryResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(probe_candidate, candidate, timeout): index
            for index, candidate in enumerate(candidates)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            indexed_results[index] = future.result()

    ordered_results = [indexed_results[index] for index in sorted(indexed_results)]
    if include_unreachable:
        return ordered_results
    return [result for result in ordered_results if result.reachable]


def run_doctor(
    host: str | None = None,
    *,
    feed: Path | None = None,
    paperclip_url: str | None = None,
    include_system: bool = True,
) -> DoctorReport:
    """Run operational checks against a device and optional publish inputs."""
    configured_host = (host or settings.host).strip() or None
    report = DoctorReport(configured_host=configured_host)

    if configured_host is None:
        report.errors.append("Set RETERMINAL_HOST or pass --host with the device IP")
        return report

    try:
        device = ReTerminalDevice(configured_host)
        capabilities = device.discover_capabilities(refresh=True)
    except Exception as exc:
        report.errors.append(str(exc))
        return report

    report.reachable = True
    report.resolved_host = capabilities.host
    report.capabilities = capabilities
    report.repo_build_sha = current_repo_sha()
    report.firmware_match = firmware_match_status(capabilities, report.repo_build_sha)
    if report.firmware_match == "unknown":
        report.warnings.append("Firmware build SHA is unknown; cannot compare device firmware to this checkout.")
    elif report.firmware_match == "mismatch":
        report.warnings.append(
            f"Firmware build SHA {capabilities.build_sha} does not match checkout {report.repo_build_sha}."
        )

    if feed is not None:
        try:
            manifest_feed = is_manifest_shape(json.loads(feed.read_text()))
        except (json.JSONDecodeError, OSError):
            manifest_feed = False
    else:
        manifest_feed = False

    if feed is not None and "examples" in feed.resolve().parts and not manifest_feed:
        report.warnings.append("The selected feed is static demo content and will not update on its own.")

    if manifest_feed and feed is not None:
        providers = build_providers(load_manifest(feed))
        if include_system:
            from reterminal.providers.system import SystemSceneProvider
            providers.append(SystemSceneProvider())
    else:
        providers = build_scene_providers(
            feed=feed,
            paperclip_url=paperclip_url,
            include_system=include_system,
        )
    if not providers:
        report.warnings.append("No publish providers selected; skipped pipeline dry run.")
        return report

    try:
        publisher = DisplayPublisher(
            providers=providers,
            renderer=MonoRenderer(),
            scheduler=PriorityScheduler(),
            device=None,
        )
        result = publisher.publish(push=False, slot_count=capabilities.page_slots)
        report.scene_count = len(result.scenes)
        report.assignment_count = len(result.assignments)
        if report.assignment_count == 0:
            report.warnings.append("Scene pipeline produced no slot assignments.")
    except Exception as exc:
        report.errors.append(str(exc))

    return report
