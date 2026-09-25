from __future__ import annotations

import httpx
import pytest

from backend.github.oauth import GitHubOAuth, OAuthError


def test_authorize_url_contains_required_params(settings):
    settings.github_client_id = "cid"
    settings.github_client_secret = "sec"
    oauth = GitHubOAuth(settings)
    url = oauth.build_authorize_url("state123")
    assert "/login/oauth/authorize" in url
    assert "client_id=cid" in url
    assert "state=state123" in url
    assert "scope=repo+read%3Auser" in url or "scope=repo%20read%3Auser" in url
    assert "redirect_uri=" in url


def test_authorize_url_requires_configuration(settings):
    settings.github_client_id = ""
    oauth = GitHubOAuth(settings)
    with pytest.raises(OAuthError):
        oauth.build_authorize_url("state")


async def test_exchange_code_success(settings):
    settings.github_client_id = "cid"
    settings.github_client_secret = "sec"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/login/oauth/access_token"
        return httpx.Response(
            200, json={"access_token": "gho_abc", "token_type": "bearer", "scope": "repo"}
        )

    oauth = GitHubOAuth(settings)
    result = await oauth.exchange_code("code123", transport=httpx.MockTransport(handler))
    assert result["access_token"] == "gho_abc"
    assert result["scope"] == "repo"


async def test_exchange_code_error_response(settings):
    settings.github_client_id = "cid"
    settings.github_client_secret = "sec"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "bad_verification_code"})

    oauth = GitHubOAuth(settings)
    with pytest.raises(OAuthError):
        await oauth.exchange_code("bad", transport=httpx.MockTransport(handler))


async def test_exchange_requires_code(settings):
    settings.github_client_id = "cid"
    settings.github_client_secret = "sec"
    oauth = GitHubOAuth(settings)
    with pytest.raises(OAuthError):
        await oauth.exchange_code("")


def test_configured_property(settings):
    settings.github_client_id = "cid"
    settings.github_client_secret = "sec"
    assert GitHubOAuth(settings).configured is True
    settings.github_client_secret = ""
    assert GitHubOAuth(settings).configured is False
