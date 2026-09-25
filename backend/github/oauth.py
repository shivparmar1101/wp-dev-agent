from __future__ import annotations

from urllib.parse import urlencode

import httpx

from backend.config import Settings, get_settings
from backend.utils.logging import get_logger

from .client import GitHubError

logger = get_logger(__name__)


class OAuthError(Exception):
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class GitHubOAuth:
    """GitHub OAuth 2.0 authorization code flow (server side only)."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return self.settings.github_configured

    def build_authorize_url(self, state: str) -> str:
        if not self.configured:
            raise OAuthError(
                "GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and "
                "GITHUB_CLIENT_SECRET in your .env file."
            )
        base = f"{self.settings.github_web_url.rstrip('/')}/login/oauth/authorize"
        params = urlencode(
            {
                "client_id": self.settings.github_client_id,
                "redirect_uri": self.settings.github_redirect_uri,
                "scope": self.settings.github_scope,
                "state": state,
                "allow_signup": "true",
            }
        )
        return f"{base}?{params}"

    async def exchange_code(
        self, code: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> dict[str, str]:
        """Exchanges the authorization code for an access token (server side)."""
        if not self.configured:
            raise OAuthError("GitHub OAuth is not configured.")
        if not code:
            raise OAuthError("Missing authorization code.")

        url = f"{self.settings.github_web_url.rstrip('/')}/login/oauth/access_token"
        payload = {
            "client_id": self.settings.github_client_id,
            "client_secret": self.settings.github_client_secret,
            "code": code,
            "redirect_uri": self.settings.github_redirect_uri,
        }
        headers = {"Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=20.0, transport=transport) as client:
                response = await client.post(url, data=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("OAuth token exchange failed: %s", exc)
            raise OAuthError("Could not reach GitHub to complete sign-in.") from exc

        try:
            data = response.json()
        except Exception as exc:
            raise OAuthError("GitHub returned an invalid token response.") from exc

        if response.status_code >= 400 or "error" in data:
            description = data.get("error_description") or data.get("error") or response.text
            logger.error("OAuth error from GitHub: %s", description)
            raise OAuthError("GitHub rejected the sign-in request.", detail=str(description))

        token = data.get("access_token")
        if not token:
            raise OAuthError("GitHub did not return an access token.")
        return {
            "access_token": str(token),
            "token_type": str(data.get("token_type", "bearer")),
            "scope": str(data.get("scope", "")),
        }
