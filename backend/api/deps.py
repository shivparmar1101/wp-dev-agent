from __future__ import annotations

from typing import Annotated, AsyncIterator

from fastapi import Depends, HTTPException, Query, Request

from backend.config import Settings, get_settings
from backend.github.client import GitHubClient
from backend.indexing.indexer import IndexRegistry, registry as default_registry
from backend.indexing.search import SearchService
from backend.storage.sessions import SessionRecord, SessionStore
from backend.utils.security import RateLimiter

_limiters: dict[str, RateLimiter] = {}


def settings_dep() -> Settings:
    return get_settings()


def session_store() -> SessionStore:
    return SessionStore()


def index_registry() -> IndexRegistry:
    return default_registry


def _limiter(name: str, limit: int, window: int) -> RateLimiter:
    key = f"{name}:{limit}:{window}"
    if key not in _limiters:
        _limiters[key] = RateLimiter(limit, window)
    return _limiters[key]


def client_key(request: Request, session: SessionRecord | None) -> str:
    if session is not None:
        return f"session:{session.id}"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def enforce_rate_limit(request: Request, name: str, session: SessionRecord | None = None) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return
    if name == "chat":
        limiter = _limiter(
            "chat", settings.chat_rate_limit_requests, settings.chat_rate_limit_window_seconds
        )
    else:
        limiter = _limiter("default", settings.rate_limit_requests, settings.rate_limit_window_seconds)
    allowed, _remaining, retry_after = limiter.check(client_key(request, session))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Please wait {int(retry_after) + 1} seconds and try again.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def get_optional_session(request: Request) -> SessionRecord | None:
    settings = get_settings()
    cookie = request.cookies.get(settings.session_cookie_name)
    if not cookie:
        return None
    return session_store().get(cookie)


def require_session(request: Request) -> SessionRecord:
    session = get_optional_session(request)
    if session is None:
        raise HTTPException(
            status_code=401,
            detail="You need to sign in with GitHub to continue.",
        )
    enforce_rate_limit(request, "default", session)
    return session


def require_configured_github() -> None:
    if not get_settings().github_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and "
                "GITHUB_CLIENT_SECRET in your .env file."
            ),
        )


async def github_client(
    session: Annotated[SessionRecord, Depends(require_session)],
) -> AsyncIterator[GitHubClient]:
    settings = get_settings()
    client = GitHubClient(
        session.access_token,
        api_url=settings.github_api_url,
        user_agent=settings.http_user_agent,
    )
    try:
        yield client
    finally:
        await client.aclose()


def search_service(request: Request) -> SearchService:
    service = getattr(request.app.state, "search_service", None)
    if isinstance(service, SearchService):
        return service
    return SearchService(registry=default_registry)


SessionDep = Annotated[SessionRecord, Depends(require_session)]
GitHubDep = Annotated[GitHubClient, Depends(github_client)]
SearchDep = Annotated[SearchService, Depends(search_service)]


def parse_ref(ref: str | None = Query(default=None, max_length=255)) -> str | None:
    return ref
