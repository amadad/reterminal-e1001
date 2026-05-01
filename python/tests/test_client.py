import io
import subprocess
from types import SimpleNamespace

import pytest
import requests

from reterminal.client import ReTerminal


def test_request_falls_back_to_curl_when_requests_route_fails(monkeypatch):
    client = ReTerminal("192.0.2.10")

    def broken_request(*args, **kwargs):
        raise requests.ConnectionError("no route")

    def fake_run(cmd, **kwargs):
        body_path = cmd[cmd.index("-o") + 1]
        with open(body_path, "wb") as f:
            f.write(b'{"ok": true}')
        return SimpleNamespace(returncode=0, stdout="200", stderr="")

    monkeypatch.setattr(client._session, "request", broken_request)
    monkeypatch.setattr(subprocess, "run", fake_run)

    response = client._request("GET", "/status")

    assert response.json() == {"ok": True}


def test_curl_fallback_rewinds_file_payload_after_requests_failure(monkeypatch):
    client = ReTerminal("192.0.2.10")
    payload = io.BytesIO(b"abc123")
    payload.read()
    observed = {}

    def broken_request(*args, **kwargs):
        raise requests.ConnectionError("no route")

    def fake_run(cmd, **kwargs):
        form = cmd[cmd.index("-F") + 1]
        upload_path = form.split("@", 1)[1].split(";", 1)[0]
        with open(upload_path, "rb") as f:
            observed["upload"] = f.read()
        body_path = cmd[cmd.index("-o") + 1]
        with open(body_path, "wb") as f:
            f.write(b'{"success": true}')
        return SimpleNamespace(returncode=0, stdout="200", stderr="")

    monkeypatch.setattr(client._session, "request", broken_request)
    monkeypatch.setattr(subprocess, "run", fake_run)

    response = client._request(
        "POST",
        "/imageraw?page=0",
        files={"image": ("image.raw", payload, "application/octet-stream")},
    )

    assert response.json() == {"success": True}
    assert observed["upload"] == b"abc123"


def test_request_preserves_curl_http_errors(monkeypatch):
    client = ReTerminal("192.0.2.10")

    def broken_request(*args, **kwargs):
        raise requests.ConnectionError("no route")

    def fake_run(cmd, **kwargs):
        body_path = cmd[cmd.index("-o") + 1]
        with open(body_path, "wb") as f:
            f.write(b'{"error":"missing"}')
        return SimpleNamespace(returncode=0, stdout="404", stderr="")

    monkeypatch.setattr(client._session, "request", broken_request)
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(requests.HTTPError) as exc_info:
        client._request("GET", "/snapshot")

    assert exc_info.value.response.status_code == 404
