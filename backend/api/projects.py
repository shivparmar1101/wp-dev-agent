from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from backend.github.client import GitHubError, GitHubRateLimitError
from backend.github.files import FileService
from backend.indexing.indexer import registry as index_registry
from backend.models.file import FileContent, FileNode
from backend.models.project import ProjectSummary
from backend.storage.scans import ProjectStore

from .deps import GitHubDep, SearchDep, SessionDep

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
async def list_projects(session: SessionDep) -> list[ProjectSummary]:
    return ProjectStore().list()


@router.get("/{owner}/{repo}", response_model=ProjectSummary)
async def get_project(owner: str, repo: str, session: SessionDep) -> ProjectSummary:
    summary = ProjectStore().get(owner, repo)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail="This repository has not been analyzed yet. Start an analysis first.",
        )
    index = index_registry.get_or_load(owner, repo)
    if index is not None:
        summary = summary.model_copy(update={"index": index.stats})
    return summary


@router.get("/{owner}/{repo}/tree", response_model=FileNode)
async def get_tree(owner: str, repo: str, session: SessionDep) -> FileNode:
    index = index_registry.get_or_load(owner, repo)
    if index is None:
        raise HTTPException(
            status_code=409,
            detail="Repository index not available. Run an analysis first.",
        )
    from backend.scanner.repository_scanner import build_tree

    paths = sorted(index.files.keys())
    meta = {
        path: (info.language, info.category, False)
        for path, info in index.files.items()
    }
    root, truncated = build_tree(paths, max_nodes=6000, classify_meta=meta)
    if truncated:
        root.children.append(
            FileNode(name="… (tree truncated)", path="…", type="file")
        )
    return root


@router.get("/{owner}/{repo}/file", response_model=FileContent)
async def get_file(
    owner: str,
    repo: str,
    request: Request,
    client: GitHubDep,
    session: SessionDep,
    path: str = Query(..., min_length=1, max_length=1024),
    ref: str | None = Query(default=None, max_length=255),
    for_ai: bool = Query(default=False),
) -> FileContent:
    from backend.utils.security import is_blocked_path, is_safe_path

    if not is_safe_path(path):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if is_blocked_path(path):
        raise HTTPException(
            status_code=403,
            detail="This file is protected (secrets/credentials) and cannot be opened.",
        )
    store = ProjectStore()
    summary = store.get(owner, repo)
    resolved_ref = ref or (summary.branch if summary else None)

    service = FileService(client)
    try:
        content = await service.read_file(
            owner, repo, path, resolved_ref, for_ai=for_ai
        )
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=429, detail=exc.user_message()) from exc
    except GitHubError as exc:
        status = exc.status if exc.status in (400, 403, 404, 413) else 502
        raise HTTPException(status_code=status, detail=exc.user_message()) from exc

    if content is None:
        raise HTTPException(
            status_code=404,
            detail="File not found or the file is not readable text.",
        )

    from backend.scanner.file_classifier import classify

    meta = classify(path, content.size)
    content.language = meta.language
    content.category = meta.category
    return content
