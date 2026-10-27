from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from backend.config import get_settings
from backend.github.client import GitHubClient, GitHubError
from backend.github.oauth import GitHubOAuth, OAuthError
from backend.storage.sessions import OAuthStateStore, SessionStore
from backend.utils.logging import get_logger

from .deps import enforce_rate_limit, get_optional_session, require_configured_github

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _frontend_base() -> str:
    """First configured frontend origin (FRONTEND_URL may list several)."""
    return get_settings().frontend_url.split(",")[0].strip().rstrip("/")


def _frontend(path: str) -> str:
    return _frontend_base() + path


def _set_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    samesite = settings.session_cookie_samesite.lower()
    if samesite not in ("lax", "strict", "none"):
        samesite = "lax"
    # `None` is only accepted by browsers alongside `Secure` (HTTPS).
    secure = settings.environment == "production" or samesite == "none"
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite=samesite,
        secure=secure,
        path="/",
    )


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    require_configured_github()
    enforce_rate_limit(request, "default")
    oauth = GitHubOAuth()
    state = OAuthStateStore().create()
    url = oauth.build_authorize_url(state)
    return RedirectResponse(url, status_code=307)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    require_configured_github()
    if error:
        logger.info("GitHub OAuth returned error=%s", error)
        return RedirectResponse(_frontend("/login?error=github_denied"), status_code=302)
    if not code:
        return RedirectResponse(_frontend("/login?error=missing_code"), status_code=302)
    if not OAuthStateStore().consume(state):
        return RedirectResponse(_frontend("/login?error=invalid_state"), status_code=302)

    oauth = GitHubOAuth()
    try:
        token_response = await oauth.exchange_code(code)
    except OAuthError as exc:
        logger.warning("OAuth exchange failed: %s", exc.message)
        return RedirectResponse(_frontend("/login?error=exchange_failed"), status_code=302)

    token = token_response["access_token"]
    scope = token_response.get("scope", "")
    try:
        async with GitHubClient(
            token,
            api_url=get_settings().github_api_url,
            user_agent=get_settings().http_user_agent,
        ) as client:
            user = await client.get_user()
    except GitHubError as exc:
        logger.error("Failed to load GitHub user after OAuth: %s", exc.message)
        return RedirectResponse(_frontend("/login?error=user_lookup_failed"), status_code=302)

    session = SessionStore().create(
        login=str(user.get("login") or ""),
        name=user.get("name") or user.get("login"),
        avatar=user.get("avatar_url"),
        token=token,
        scope=scope,
    )
    logger.info("Created session for GitHub user %s", session.github_login)
    response = RedirectResponse(_frontend("/dashboard"), status_code=302)
    _set_cookie(response, session.id)
    return response


@router.get("/me")
async def me(request: Request) -> JSONResponse:
    session = get_optional_session(request)
    if session is None:
        return JSONResponse({"authenticated": False, "user": None})
    return JSONResponse({"authenticated": True, "user": session.public})


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    settings = get_settings()
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        SessionStore().delete(cookie)
    response = JSONResponse({"ok": True})
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
