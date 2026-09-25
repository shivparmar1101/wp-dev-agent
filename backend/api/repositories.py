from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from backend.github.client import GitHubError, GitHubRateLimitError
from backend.github.repositories import RepositoryService

from .deps import GitHubDep, SessionDep

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("")
async def list_repositories(
    request: Request,
    client: GitHubDep,
    session: SessionDep,
    page: int = Query(default=1, ge=1, le=100),
    per_page: int = Query(default=30, ge=1, le=100),
    q: str | None = Query(default=None, max_length=120),
    visibility: str = Query(default="all", pattern="^(all|public|private)$"),
):
    service = RepositoryService(client)
    try:
        result = await service.list(
            page=page, per_page=per_page, query=q, visibility=visibility
        )
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=429, detail=exc.user_message()) from exc
    except GitHubError as exc:
        raise HTTPException(status_code=_status_for(exc), detail=exc.user_message()) from exc
    return result


@router.get("/{owner}/{repo}")
async def get_repository(owner: str, repo: str, client: GitHubDep, session: SessionDep):
    service = RepositoryService(client)
    try:
        return await service.get(owner, repo)
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=429, detail=exc.user_message()) from exc
    except GitHubError as exc:
        raise HTTPException(status_code=_status_for(exc), detail=exc.user_message()) from exc


def _status_for(exc: GitHubError) -> int:
    if exc.status in (401, 403, 404, 409, 413, 422):
        return exc.status if exc.status != 401 else 401
    return 502
