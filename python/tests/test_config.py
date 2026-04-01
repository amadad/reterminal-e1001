import pytest

from reterminal.config import Settings, get_host, settings


def test_settings_from_env_does_not_bake_in_a_default_host(monkeypatch):
    monkeypatch.delenv("RETERMINAL_HOST", raising=False)

    settings = Settings.from_env()

    assert settings.host == ""


def test_get_host_requires_an_explicit_host_when_none_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "host", "")

    with pytest.raises(ValueError, match="RETERMINAL_HOST"):
        get_host()


def test_get_host_uses_configured_host_or_override(monkeypatch):
    monkeypatch.setattr(settings, "host", "192.168.7.76")

    assert get_host() == "192.168.7.76"
    assert get_host("192.168.7.80") == "192.168.7.80"
