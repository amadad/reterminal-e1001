"""Small, durable delivery receipts. Serving bytes is not device confirmation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading

from reterminal.config import SLOT_COUNT


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_receipt(body: object) -> dict:
    if not isinstance(body, dict) or body.get("schema_version") != 1:
        raise ValueError("expected receipt schema_version 1")
    if not isinstance(body.get("device_id"), str) or not 1 <= len(body["device_id"]) <= 80:
        raise ValueError("expected device_id")
    if body.get("outcome") not in {"updated", "unchanged", "partial", "error"}:
        raise ValueError("invalid outcome")
    if type(body.get("current_page")) is not int or not 0 <= body["current_page"] < SLOT_COUNT:
        raise ValueError("invalid current_page")
    interval = body.get("wake_interval_s")
    if type(interval) is not int or not 1 <= interval <= 86400:
        raise ValueError("invalid wake_interval_s")
    if type(body.get("refresh_returned")) is not bool:
        raise ValueError("expected refresh_returned boolean")
    if "next_poll_in_s" in body and (type(body["next_poll_in_s"]) is not int or not 0 <= body["next_poll_in_s"] <= 86400):
        raise ValueError("invalid next_poll_in_s")
    hashes = body.get("hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("expected slot hashes")
    for slot, digest in hashes.items():
        if slot not in {f"slot-{n}" for n in range(SLOT_COUNT)}:
            raise ValueError("invalid slot")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid SHA-256")
    displayed = body.get("displayed_hash")
    if displayed is not None and (not isinstance(displayed, str) or not re.fullmatch(r"[0-9a-f]{64}", displayed)):
        raise ValueError("invalid displayed_hash")
    # Retain only protocol fields; timestamps and peer identity belong to the host.
    fields = ("schema_version", "device_id", "hostname", "firmware_version", "build_sha",
              "boot_count", "wake_reason", "wake_interval_s", "outcome", "error",
              "slot_errors", "hashes", "current_page", "refresh_returned", "uptime_ms",
              "battery_mv", "rssi", "displayed_hash", "next_poll_in_s")
    return {key: body[key] for key in fields if key in body}


class DeliveryState:
    """One bounded receipt log per publisher, persisted atomically across restarts."""

    def __init__(self, path: Path | None = None, manifest_path: Path | None = None):
        self.path = path
        self.manifest_path = manifest_path
        self.lock = threading.Lock()
        self.receipts: list[dict] = []
        self.started_at = utc_now()
        self.last_poll: dict | None = None
        self.last_download: dict | None = None
        self.rendered_at: str | None = None
        self.render_error: str | None = None
        self.config_error: str | None = None
        self.state_error: str | None = None
        if path and path.exists():
            try:
                data = json.loads(path.read_text())
                for receipt in data["receipts"][-32:]:
                    validate_receipt(receipt)
                    if datetime.fromisoformat(receipt["received_at"]).tzinfo is None:
                        raise ValueError("receipt timestamp must include timezone")
                    self.receipts.append(receipt)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.receipts = []
                self.state_error = f"Could not read previous receipts: {exc}"

    def record(self, body: object, peer: str, desired: dict | None = None) -> dict:
        receipt = validate_receipt(body)
        receipt.update(received_at=utc_now(), peer=peer)
        if desired is not None:
            receipt["matches_at_receipt"] = bool(any(desired.values())) and all(
                receipt["hashes"].get(slot) == digest for slot, digest in desired.items() if digest
            )
        with self.lock:
            receipts = [*self.receipts, receipt][-32:]
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(self.path.suffix + ".tmp")
                temporary.write_text(json.dumps({"receipts": receipts}, indent=2) + "\n")
                temporary.replace(self.path)
            self.receipts = receipts
            self.state_error = None
        return receipt

    def request(self, kind: str, peer: str, slot: int | None = None) -> None:
        evidence = {"at": utc_now(), "peer": peer}
        if slot is not None:
            evidence["slot"] = slot
        with self.lock:
            if kind == "poll":
                self.last_poll = evidence
            else:
                self.last_download = evidence

    def health(self, desired: dict, *, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        with self.lock:
            receipt = self.receipts[-1] if self.receipts else None
            age = None if receipt is None else max(0, (now - datetime.fromisoformat(receipt["received_at"])).total_seconds())
            matches = {
                slot: digest is not None and receipt is not None and receipt["hashes"].get(slot) == digest
                for slot, digest in desired.items()
            }
            if receipt is None:
                status = "unconfirmed"
            elif age > 2 * receipt["wake_interval_s"] + 120:
                status = "stale"
            elif receipt["outcome"] in {"error", "partial"}:
                status = "failed"
            elif any(desired.values()) and all(matches[slot] for slot, digest in desired.items() if digest):
                status = "stored"
            else:
                status = "pending"
            return {
                "started_at": self.started_at,
                "manifest": str(self.manifest_path) if self.manifest_path else None,
                "rendered_at": self.rendered_at,
                "render_error": self.render_error,
                "config_error": self.config_error,
                "state_error": self.state_error,
                "desired_hashes": desired,
                "last_poll": self.last_poll,
                "last_download": self.last_download,
                "delivery_status": status,
                "receipt_age_s": age,
                "matches": matches,
                "last_receipt": receipt,
                "selected_slot_matches": receipt is not None and matches.get(f"slot-{receipt['current_page']}", False),
                "reported_display_matches": receipt is not None and receipt.get("displayed_hash") is not None
                    and receipt["displayed_hash"] == desired.get(f"slot-{receipt['current_page']}"),
                "receipts": list(self.receipts),
            }
