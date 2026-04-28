from pathlib import Path

from reterminal.device import DeviceCapabilities
from reterminal.diagnostics import (
    DiscoveryResult,
    build_discovery_candidates,
    discover_hosts,
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
            host=self.host or "192.168.7.76",
            page_slots=4,
            current_page=1,
            current_page_name="clock",
            uptime_ms=1234,
        )


class BrokenDevice:
    def __init__(self, host=None):
        self.host = host

    def discover_capabilities(self, refresh=False):
        raise RuntimeError("device offline")



def test_build_discovery_candidates_dedupes_and_expands_subnet():
    candidates = build_discovery_candidates(
        configured_host="192.168.7.76",
        candidates=["reterminal.local", "192.168.7.76"],
        subnet="192.168.7",
        start=76,
        end=78,
    )

    assert candidates == [
        "192.168.7.76",
        "reterminal.local",
        "reterminal",
        "192.168.7.77",
        "192.168.7.78",
    ]



def test_discover_hosts_returns_only_reachable_results(monkeypatch):
    def fake_probe(candidate, timeout=1.5):
        if candidate == "reterminal.local":
            return DiscoveryResult(target=candidate, reachable=True, status={"ip": "192.168.7.76"})
        return DiscoveryResult(target=candidate, reachable=False, error="offline")

    monkeypatch.setattr("reterminal.diagnostics.probe_candidate", fake_probe)

    results = discover_hosts(["reterminal.local", "192.168.7.77"], timeout=0.1, workers=2)

    assert [result.target for result in results] == ["reterminal.local"]




def test_run_doctor_reports_pipeline_health_and_example_feed_warnings(monkeypatch, tmp_path: Path):
    feed = tmp_path / "examples" / "feed.json"
    feed.parent.mkdir(parents=True)
    feed.write_text('{"scenes": []}')

    monkeypatch.setattr("reterminal.diagnostics.ReTerminalDevice", StubDevice)
    monkeypatch.setattr("reterminal.diagnostics.DisplayPublisher", StubPublisher)

    report = run_doctor(host="192.168.7.76", feed=feed)

    assert report.reachable is True
    assert report.resolved_host == "192.168.7.76"
    assert report.assignment_count == 2
    assert any("static demo content" in warning for warning in report.warnings)


def test_run_doctor_reports_connectivity_errors(monkeypatch):
    monkeypatch.setattr("reterminal.diagnostics.ReTerminalDevice", BrokenDevice)

    report = run_doctor(host="192.168.7.76")

    assert report.reachable is False
    assert report.errors == ["device offline"]
