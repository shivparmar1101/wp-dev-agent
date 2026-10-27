from __future__ import annotations

from backend.api.auth import _set_cookie, _frontend, _frontend_base
from backend.config import Settings


class FakeResponse:
    """Captures `set_cookie` kwargs the way Starlette's Response does."""

    def __init__(self) -> None:
        self.cookies: dict[str, dict] = {}

    def set_cookie(self, *, key: str, value: str, **kwargs) -> None:
        self.cookies[key] = {"value": value, **kwargs}


def _settings(monkeypatch, **overrides) -> Settings:
    base = {
        "_env_file": None,
        "database_url": "sqlite:///:memory:",
        "secret_key": "unit-test-secret",
        "ai_provider": "mock",
        "ai_api_key": "",
    }
    base.update(overrides)
    settings = Settings(**base)
    monkeypatch.setattr("backend.api.auth.get_settings", lambda: settings)
    return settings


def test_cookie_defaults_to_lax_and_not_secure_in_dev(monkeypatch):
    _settings(monkeypatch, environment="development")
    response = FakeResponse()
    _set_cookie(response, "abc123")

    cookie = response.cookies["wpdev_session"]
    assert cookie["samesite"] == "lax"
    assert cookie["secure"] is False
    assert cookie["httponly"] is True
    assert cookie["path"] == "/"


def test_cookie_is_secure_in_production(monkeypatch):
    _settings(monkeypatch, environment="production")
    response = FakeResponse()
    _set_cookie(response, "abc123")

    cookie = response.cookies["wpdev_session"]
    assert cookie["secure"] is True
    assert cookie["samesite"] == "lax"


def test_cookie_cross_site_split_forces_secure(monkeypatch):
    """Netlify frontend + Render API: SameSite=None is only legal with Secure."""
    _settings(
        monkeypatch,
        environment="production",
        session_cookie_samesite="none",
    )
    response = FakeResponse()
    _set_cookie(response, "abc123")

    cookie = response.cookies["wpdev_session"]
    assert cookie["samesite"] == "none"
    assert cookie["secure"] is True


def test_cookie_forces_secure_even_in_dev_when_samesite_none(monkeypatch):
    _settings(monkeypatch, environment="development", session_cookie_samesite="none")
    response = FakeResponse()
    _set_cookie(response, "abc123")
    assert response.cookies["wpdev_session"]["secure"] is True


def test_cookie_falls_back_to_lax_for_bogus_value(monkeypatch):
    _settings(monkeypatch, session_cookie_samesite="garbage")
    response = FakeResponse()
    _set_cookie(response, "abc123")
    assert response.cookies["wpdev_session"]["samesite"] == "lax"


def test_frontend_base_uses_first_origin_when_listed(monkeypatch):
    _settings(
        monkeypatch,
        frontend_url="https://site.netlify.app, http://localhost:3000",
    )
    assert _frontend_base() == "https://site.netlify.app"
    assert _frontend("/dashboard") == "https://site.netlify.app/dashboard"


def test_frontend_base_single_origin(monkeypatch):
    _settings(monkeypatch, frontend_url="http://localhost:3000/")
    assert _frontend_base() == "http://localhost:3000"
