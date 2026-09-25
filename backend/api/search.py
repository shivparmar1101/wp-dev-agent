from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.models.analysis import SearchRequest, SearchResponse

from .deps import SearchDep, SessionDep

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/{owner}/{repo}", response_model=SearchResponse)
async def search_repository(
    owner: str,
    repo: str,
    request: Request,
    session: SessionDep,
    search: SearchDep,
    body: SearchRequest,
) -> SearchResponse:
    from .deps import enforce_rate_limit

    enforce_rate_limit(request, "default", session)
    try:
        return await search.search(
            owner, repo, body.query, mode=body.mode, limit=body.limit
        )
    except LookupError:
        raise HTTPException(
            status_code=409,
            detail=(
                "Repository index not available. Analyze the repository before "
                "running searches."
            ),
        ) from None
