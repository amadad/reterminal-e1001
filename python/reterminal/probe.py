"""Hardware capability probe for reTerminal devices.

Use this before refactoring firmware/page architecture.

The probe intentionally separates:
- automated API checks we can run from the host
- manual physical checks that still need a human looking at the device

Page-slot probing is destructive: it overwrites stored page buffers with a test
pattern. Run it only when you are okay replacing whatever is currently cached on
the device.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from reterminal.client import ReTerminal
from reterminal.encoding import create_pattern
from reterminal.payloads import JSONObject, PageInfoPayload, StatusPayload

EXPECTED_STATUS_FIELDS = (
    "ip",
    "rssi",
    "ssid",
    "uptime_ms",
    "free_heap",
    "current_page",
    "page_name",
)

VALID_PATTERNS = ("checkerboard", "horizontal", "vertical", "diagonal")

MANUAL_CHECKS = (
    "Visually confirm the uploaded pattern appears on every stored page slot that the probe marked as supported.",
    "Press the physical previous/next/refresh buttons and confirm they navigate the same slot range as the API.",
    "Power-cycle the device and record whether stored page buffers survive reboot.",
    "Measure full-screen refresh time and note any ghosting or partial-update artifacts.",
    "If OTA is required, test one OTA flash on the same firmware build and record success/failure.",
)


@dataclass
class SlotProbeResult:
    """Result of probing a single requested page slot."""

    slot: int
    push_stored: bool
    push_displayed: bool
    selected_page_matches: bool
    push_response: JSONObject = field(default_factory=dict)
    set_response: JSONObject = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class ProbeReport:
    """Structured probe report suitable for CLI output or JSON persistence."""

    generated_at: str
    host: str
    expected_pages: int
    requested_slots: int
    upload_pages: bool
    status: StatusPayload
    status_missing_fields: list[str]
    page_info: PageInfoPayload
    original_page: int | None
    inferred_slot_count: int | None = None
    slot_results: list[SlotProbeResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manual_checks: list[str] = field(default_factory=lambda: list(MANUAL_CHECKS))

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def missing_status_fields(status: StatusPayload) -> list[str]:
    """Return expected status fields missing from the device response."""
    return [field for field in EXPECTED_STATUS_FIELDS if field not in status]


def analyze_slot_result(
    slot: int,
    push_response: JSONObject,
    set_response: JSONObject,
) -> SlotProbeResult:
    """Interpret push/set responses for a requested page slot."""
    push_stored = push_response.get("page") == slot
    push_displayed = bool(push_response.get("displayed"))
    selected_page_matches = set_response.get("page") == slot

    notes: list[str] = []
    if push_stored:
        notes.append("stored")
    elif push_displayed:
        notes.append("displayed immediately instead of storing")
    else:
        notes.append("push response did not confirm storage")

    if selected_page_matches:
        notes.append("selectable via /page")
    else:
        returned = set_response.get("page")
        notes.append(f"set_page returned {returned!r}")

    return SlotProbeResult(
        slot=slot,
        push_stored=push_stored,
        push_displayed=push_displayed,
        selected_page_matches=selected_page_matches,
        push_response=push_response,
        set_response=set_response,
        notes=notes,
    )


def infer_contiguous_slot_count(slot_results: list[SlotProbeResult]) -> int:
    """Infer the contiguous slot count supported from slot 0 upward."""
    contiguous = 0
    for result in sorted(slot_results, key=lambda item: item.slot):
        if result.slot != contiguous:
            break
        if result.push_stored and result.selected_page_matches:
            contiguous += 1
        else:
            break
    return contiguous


def run_probe(
    host: str | None = None,
    *,
    expected_pages: int = 7,
    requested_slots: int = 8,
    pattern: str = "checkerboard",
    upload_pages: bool = False,
    restore_page: bool = True,
) -> ProbeReport:
    """Run the automated portion of the device capability probe."""
    if pattern not in VALID_PATTERNS:
        raise ValueError(f"Invalid pattern: {pattern}. Choose from {', '.join(VALID_PATTERNS)}")
    if requested_slots < 1:
        raise ValueError("requested_slots must be >= 1")

    client = ReTerminal(host)
    status = client.status()
    page_info = client.get_page()
    current_page = page_info.get("page")
    original_page = current_page if isinstance(current_page, int) else None

    report = ProbeReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        host=client.host,
        expected_pages=expected_pages,
        requested_slots=requested_slots,
        upload_pages=upload_pages,
        status=status,
        status_missing_fields=missing_status_fields(status),
        page_info=page_info,
        original_page=original_page,
    )

    if report.status_missing_fields:
        report.warnings.append(
            "Status response is missing expected fields: " + ", ".join(report.status_missing_fields)
        )

    reported_total = page_info.get("total")
    if not isinstance(reported_total, int):
        report.warnings.append("GET /page did not report an integer 'total' page count.")

    if not upload_pages:
        report.warnings.append(
            "Page-slot upload probe was skipped. Re-run with --upload-pages for destructive slot verification."
        )
        return report

    raw = create_pattern(pattern)
    for slot in range(requested_slots):
        push_response = client.push_raw(raw, page=slot)
        set_response = client.set_page(slot)
        report.slot_results.append(analyze_slot_result(slot, push_response, set_response))

    report.inferred_slot_count = infer_contiguous_slot_count(report.slot_results)

    if restore_page and original_page is not None:
        try:
            client.set_page(original_page)
        except Exception as exc:  # pragma: no cover - best effort restore only
            report.warnings.append(f"Failed to restore original page {original_page}: {exc}")

    if isinstance(reported_total, int) and report.inferred_slot_count != reported_total:
        report.warnings.append(
            "Reported page total and inferred slot count differ: "
            f"GET /page total={reported_total}, inferred={report.inferred_slot_count}."
        )

    if report.inferred_slot_count < expected_pages:
        report.warnings.append(
            f"Expected {expected_pages} host-side pages, but automated probe only confirmed "
            f"{report.inferred_slot_count} contiguous firmware slots."
        )

    return report


def format_report(report: ProbeReport) -> str:
    """Render a human-readable probe summary."""
    lines = [
        f"Probe target: {report.host}",
        f"Generated: {report.generated_at}",
        "",
        "Status endpoint",
        f"  current_page: {report.status.get('current_page', '?')}",
        f"  page_name: {report.status.get('page_name', '?')}",
        f"  missing fields: {', '.join(report.status_missing_fields) if report.status_missing_fields else 'none'}",
        "",
        "Page endpoint",
        f"  page: {report.page_info.get('page', '?')}",
        f"  name: {report.page_info.get('name', '?')}",
        f"  total: {report.page_info.get('total', '?')}",
        f"  loaded: {report.page_info.get('loaded', '?')}",
    ]

    if report.upload_pages:
        lines.extend(["", "Slot probe (destructive)"])
        for result in report.slot_results:
            lines.append(
                "  "
                f"slot {result.slot}: stored={'yes' if result.push_stored else 'no'}, "
                f"displayed={'yes' if result.push_displayed else 'no'}, "
                f"selectable={'yes' if result.selected_page_matches else 'no'}"
            )
        lines.append(f"  inferred contiguous slot count: {report.inferred_slot_count}")
    else:
        lines.extend(["", "Slot probe (destructive)", "  skipped"])

    if report.warnings:
        lines.extend(["", "Warnings"])
        for warning in report.warnings:
            lines.append(f"  - {warning}")

    lines.extend(["", "Manual checks remaining"])
    for item in report.manual_checks:
        lines.append(f"  - {item}")

    return "\n".join(lines)
