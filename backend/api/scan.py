from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.github.client import GitHubError, GitHubRateLimitError
from backend.models.project import ScanStatus
from backend.scanner.scan_job import ScanJobRunner

from .deps import SessionDep

router = APIRouter(prefix="/scan", tags=["scan"])


class ScanRequest(BaseModel):
    branch: str | None = Field(default=None, max_length=255)


def _runner(request: Request) -> ScanJobRunner:
    runner: ScanJobRunner | None = getattr(request.app.state, "scan_runner", None)
    if runner is None:  # pragma: no cover - startup ordering guard
        raise HTTPException(status_code=503, detail="Scan service is not ready yet.")
    return runner


@router.post("/{owner}/{repo}", response_model=ScanStatus)
async def start_scan(
    owner: str,
    repo: str,
    request: Request,
    session: SessionDep,
    body: ScanRequest | None = None,
) -> ScanStatus:
    runner = _runner(request)
    branch = body.branch if body else None
    try:
        status = runner.start(
            owner=owner, repo=repo, token=session.access_token, branch=branch
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Could not start the repository scan.") from exc
    return status


@router.get("/{owner}/{repo}/status", response_model=ScanStatus)
async def scan_status(owner: str, repo: str, request: Request, session: SessionDep) -> ScanStatus:
    runner = _runner(request)
    status = runner.latest_status(owner, repo)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail="No analysis has been run for this repository yet.",
        )
    return status


@router.get("/{scan_id}", response_model=ScanStatus)
async def scan_status_by_id(scan_id: str, request: Request, session: SessionDep) -> ScanStatus:
    runner = _runner(request)
    status = runner.get_status(scan_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return status


def github_error_handlers(app) -> None:  # pragma: no cover - convenience
    from backend.github.client import GitHubError as _GitHubError

    @app.exception_handler(_GitHubError)
    async def _handle(request: Request, exc: _GitHubError):
        status = 502
        if isinstance(exc, GitHubRateLimitError):
            status = 429
        elif exc.status in (401, 403, 404, 409, 413):
            status = exc.status
        return HTTPException(status_code=status, detail=exc.user_message())
