"""Discovery and doctor helpers for operating reTerminal devices."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from time import perf_counter
from pathlib import Path
from typing import Any, Optional

import requests

from reterminal.app import DisplayPublisher
from reterminal.config import settings
from reterminal.device import DeviceCapabilities, ReTerminalDevice
from reterminal.pages import list_pages
from reterminal.providers import FileSceneProvider, PaperclipSceneProvider, SystemSceneProvider
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler


@dataclass(slots=True)
class DiscoveryResult:
    """Reachability result for one discovery target."""

    target: str
    reachable: bool
    status: Optional[dict[str, Any]] = None
    page_info: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None


@dataclass(slots=True)
class DoctorReport:
    """Structured operational health report for one device target."""

    configured_host: Optional[str]
    resolved_host: Optional[str] = None
    reachable: bool = False
    capabilities: Optional[DeviceCapabilities] = None
    legacy_page_issues: list[tuple[str, int]] = field(default_factory=list)
    scene_count: int = 0
    assignment_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


DEFAULT_DISCOVERY_HOSTNAMES = ("reterminal.local", "reterminal")


def build_discovery_candidates(
    configured_host: Optional[str] = None,
    *,
    candidates: Optional[list[str]] = None,
    hostnames: Optional[list[str]] = None,
    subnet: Optional[str] = None,
    start: int = 1,
    end: int = 254,
) -> list[str]:
    """Build a deduplicated discovery candidate list."""
    ordered: list[str] = []

    def add(value: Optional[str]) -> None:
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


def probe_candidate(target: str, timeout: float = 1.5) -> DiscoveryResult:
    """Probe one candidate host without the normal retry budget."""
    started = perf_counter()
    status_url = f"http://{target}/status"
    page_url = f"http://{target}/page"

    try:
        status_response = requests.get(status_url, timeout=timeout)
        status_response.raise_for_status()
        page_response = requests.get(page_url, timeout=timeout)
        page_response.raise_for_status()
        latency_ms = int((perf_counter() - started) * 1000)
        return DiscoveryResult(
            target=target,
            reachable=True,
            status=status_response.json(),
            page_info=page_response.json(),
            latency_ms=latency_ms,
        )
    except Exception as exc:
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


def find_legacy_page_issues(page_slots: int) -> list[tuple[str, int]]:
    """Return legacy fixed pages that point past the live device slot count."""
    return [
        (name, slot)
        for name, slot in list_pages().items()
        if slot >= page_slots
    ]


def run_doctor(
    host: Optional[str] = None,
    *,
    feed: Optional[Path] = None,
    paperclip_url: Optional[str] = None,
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
    report.legacy_page_issues = find_legacy_page_issues(capabilities.page_slots)

    if report.legacy_page_issues:
        report.warnings.append(
            "Legacy fixed pages exceed the live device slot count: "
            + ", ".join(f"{name}->{slot}" for name, slot in report.legacy_page_issues)
        )

    if feed is not None and "examples" in feed.resolve().parts:
        report.warnings.append("The selected feed is static demo content and will not update on its own.")

    providers = []
    if feed is not None:
        providers.append(FileSceneProvider(feed))
    if paperclip_url is not None:
        providers.append(PaperclipSceneProvider(paperclip_url))
    if include_system:
        providers.append(SystemSceneProvider())

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
