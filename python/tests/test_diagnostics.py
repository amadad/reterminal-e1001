from pathlib import Path
from types import SimpleNamespace

import requests

from reterminal.device import DeviceCapabilities
from reterminal.diagnostics import (
    DiscoveryResult,
    build_discovery_candidates,
    discover_hosts,
    firmware_match_status,
    probe_candidate,
    run_doctor,
)


class StubPublisherResult:
    def __init__(self, scenes, assignments):
        self.scenes = scenes
        self.assignments = assignments


class StubPublisher:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def publish(self, **kwargs):
        return StubPublisherResult(scenes=[object(), object()], assignments={0: object(), 1: object()})


class StubDevice:
    def __init__(self, host=None):
        self.host = host

    def discover_capabilities(self, refresh=False):
        return DeviceCapabilities(
            host=self.host or "192.0.2.76",
            page_slots=4,
            current_page=1,
            current_page_name="clock",
            uptime_ms=1234,
            build_sha="abcdef1",
            firmware_version="test",
        )


class BrokenDevice:
    def __init__(self, host=None):
        self.host = host

    def discover_capabilities(self, refresh=False):
        raise RuntimeError("device offline")



def test_build_discovery_candidates_dedupes_and_expands_subnet():
    candidates = build_discovery_candidates(
        configured_host="192.0.2.76",
        candidates=["reterminal.local", "192.0.2.76"],
        subnet="192.0.2",
        start=76,
        end=78,
    )

    assert candidates == [
        "192.0.2.76",
        "reterminal.local",
        "reterminal",
        "192.0.2.77",
        "192.0.2.78",
    ]



def test_probe_candidate_falls_back_to_curl_when_requests_fails(monkeypatch):
    def broken_get(*args, **kwargs):
        raise requests.ConnectionError("no route")

    def fake_run(cmd, **kwargs):
        if cmd[-1].endswith("/status"):
            return SimpleNamespace(returncode=0, stdout='{"ip":"192.0.2.76"}', stderr="")
        return SimpleNamespace(returncode=0, stdout='{"page":0,"total":4}', stderr="")

    monkeypatch.setattr("reterminal.diagnostics.requests.get", broken_get)
    monkeypatch.setattr("reterminal.diagnostics.subprocess.run", fake_run)

    result = probe_candidate("192.0.2.76", timeout=0.1)

    assert result.reachable is True
    assert result.status == {"ip": "192.0.2.76"}
    assert result.page_info == {"page": 0, "total": 4}



def test_discover_hosts_returns_only_reachable_results(monkeypatch):
    def fake_probe(candidate, timeout=1.5):
        if candidate == "reterminal.local":
            return DiscoveryResult(target=candidate, reachable=True, status={"ip": "192.0.2.76"})
        return DiscoveryResult(target=candidate, reachable=False, error="offline")

    monkeypatch.setattr("reterminal.diagnostics.probe_candidate", fake_probe)

    results = discover_hosts(["reterminal.local", "192.0.2.77"], timeout=0.1, workers=2)

    assert [result.target for result in results] == ["reterminal.local"]




def test_firmware_match_status_compares_prefixes():
    assert firmware_match_status(DeviceCapabilities(host="x", build_sha="abcdef1"), "abcdef123456") == "match"
    assert firmware_match_status(DeviceCapabilities(host="x", build_sha="abcdef123456-dirty"), "abcdef123456-dirty") == "match"
    assert firmware_match_status(DeviceCapabilities(host="x", build_sha="abcdef123456"), "abcdef123456-dirty") == "mismatch"
    assert firmware_match_status(DeviceCapabilities(host="x", build_sha="deadbee"), "abcdef123456") == "mismatch"
    assert firmware_match_status(DeviceCapabilities(host="x", build_sha="unknown"), "abcdef123456") == "unknown"



def test_run_doctor_reports_pipeline_health_and_example_feed_warnings(monkeypatch, tmp_path: Path):
    feed = tmp_path / "examples" / "feed.json"
    feed.parent.mkdir(parents=True)
    feed.write_text('{"scenes": []}')

    monkeypatch.setattr("reterminal.diagnostics.ReTerminalDevice", StubDevice)
    monkeypatch.setattr("reterminal.diagnostics.DisplayPublisher", StubPublisher)
    monkeypatch.setattr("reterminal.diagnostics.current_repo_sha", lambda: "abcdef123456")

    report = run_doctor(host="192.0.2.76", feed=feed)

    assert report.reachable is True
    assert report.resolved_host == "192.0.2.76"
    assert report.assignment_count == 2
    assert report.firmware_match == "match"
    assert any("static demo content" in warning for warning in report.warnings)


def test_run_doctor_accepts_provider_manifest(monkeypatch, tmp_path: Path):
    feed = tmp_path / "kitchen.json"
    feed.write_text('{"providers": [{"type": "missions", "path": "missing.md"}]}')

    monkeypatch.setattr("reterminal.diagnostics.ReTerminalDevice", StubDevice)
    monkeypatch.setattr("reterminal.diagnostics.DisplayPublisher", StubPublisher)
    monkeypatch.setattr("reterminal.diagnostics.current_repo_sha", lambda: "abcdef123456")

    report = run_doctor(host="192.0.2.76", feed=feed, include_system=False)

    assert report.reachable is True
    assert report.errors == []
    assert report.assignment_count == 2
    assert not any("static demo content" in warning for warning in report.warnings)



def test_run_doctor_reports_connectivity_errors(monkeypatch):
    monkeypatch.setattr("reterminal.diagnostics.ReTerminalDevice", BrokenDevice)

    report = run_doctor(host="192.0.2.76")

    assert report.reachable is False
    assert report.errors == ["device offline"]
