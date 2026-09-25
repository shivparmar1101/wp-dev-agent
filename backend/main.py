from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.ai.client import MockProvider
from backend.ai.provider import AIError, AIProvider, create_provider
from backend.api import auth, chat, projects, repositories, scan, search
from backend.config import get_settings
from backend.github.client import GitHubError
from backend.indexing.search import SearchService
from backend.scanner.scan_job import ScanJobRunner
from backend.storage.db import init_db
from backend.storage.sessions import SessionStore
from backend.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)

VERSION = "0.1.0"


def _build_provider(settings) -> AIProvider:
    try:
        return create_provider(settings)
    except AIError as exc:
        logger.warning("AI provider unavailable (%s); falling back to mock mode.", exc.message)
        return MockProvider(settings)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not create AI provider (%s); using mock mode.", exc)
        return MockProvider(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()

    try:
        SessionStore().purge_expired()
    except Exception:  # pragma: no cover
        logger.debug("Session purge failed", exc_info=True)

    provider = _build_provider(settings)
    embeddings_enabled = bool(provider.supports_embeddings() and provider.configured)
    app.state.ai_provider = provider
    app.state.search_service = SearchService(
        embeddings=provider if embeddings_enabled else None
    )
    app.state.scan_runner = ScanJobRunner(
        settings, embeddings_enabled=embeddings_enabled
    )
    app.state.settings = settings

    if not settings.github_configured:
        logger.warning(
            "GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET are not set - GitHub sign-in "
            "will be unavailable."
        )
    if not settings.ai_configured:
        logger.warning(
            "AI_API_KEY is not set - AI analysis will run in retrieval-only mode."
        )
    logger.info("WP Dev Agent backend started (%s)", settings.environment)
    yield
    logger.info("WP Dev Agent backend shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="WP Dev Agent API",
        version=VERSION,
        description="GitHub-based AI WordPress/Elementor development agent (Foundation MVP)",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.environment != "production" else None,
        openapi_url="/api/openapi.json" if settings.environment != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(repositories.router, prefix=prefix)
    app.include_router(projects.router, prefix=prefix)
    app.include_router(scan.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)

    @app.get(f"{prefix}/health")
    async def health() -> dict:
        current = get_settings()
        provider: AIProvider | None = getattr(app.state, "ai_provider", None)
        return {
            "status": "ok",
            "version": VERSION,
            "github_configured": current.github_configured,
            "ai_provider": provider.name if provider else current.ai_provider,
            "ai_configured": bool(provider and provider.configured),
            "environment": current.environment,
        }

    # --- error handlers ---------------------------------------------------
    @app.exception_handler(GitHubError)
    async def github_error_handler(request: Request, exc: GitHubError):
        status = 502
        if exc.status in (400, 401, 403, 404, 409, 413, 422):
            status = exc.status
        if exc.kind == "rate_limit":
            status = 429
        if exc.kind == "empty_repository":
            status = 409
        logger.warning("GitHub error (%s): %s", exc.kind, exc.message)
        return JSONResponse(
            status_code=status,
            content={"detail": exc.user_message(), "kind": exc.kind},
        )

    @app.exception_handler(AIError)
    async def ai_error_handler(request: Request, exc: AIError):
        from backend.api.chat import _status_for

        logger.warning("AI error (%s): %s", exc.kind, exc.message)
        return JSONResponse(
            status_code=_status_for(exc),
            content={"detail": exc.user_message(), "kind": exc.kind},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected server error occurred. Please try again."},
        )

    return app


app = create_app()


def run() -> None:  # pragma: no cover - dev entry point
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
