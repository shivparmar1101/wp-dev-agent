from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.models.repository import Repository, RepositoryListResponse

from .client import GitHubClient, GitHubError


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_repository(raw: dict[str, Any]) -> Repository:
    owner = raw.get("owner") or {}
    return Repository(
        id=int(raw.get("id") or 0),
        name=str(raw.get("name") or ""),
        full_name=str(raw.get("full_name") or ""),
        owner=str(owner.get("login") or raw.get("full_name", "").split("/")[0]),
        owner_avatar=owner.get("avatar_url"),
        description=raw.get("description"),
        private=bool(raw.get("private")),
        fork=bool(raw.get("fork")),
        archived=bool(raw.get("archived")),
        disabled=bool(raw.get("disabled")),
        visibility=str(raw.get("visibility") or ("private" if raw.get("private") else "public")),
        default_branch=str(raw.get("default_branch") or "main"),
        language=raw.get("language"),
        html_url=str(raw.get("html_url") or ""),
        updated_at=_parse_dt(raw.get("updated_at")),
        pushed_at=_parse_dt(raw.get("pushed_at")),
        size_kb=int(raw.get("size") or 0),
        stargazers_count=int(raw.get("stargazers_count") or 0),
        topics=[str(t) for t in (raw.get("topics") or [])],
    )


class RepositoryService:
    def __init__(self, client: GitHubClient):
        self.client = client

    async def list(
        self,
        *,
        page: int = 1,
        per_page: int = 30,
        query: str | None = None,
        visibility: str = "all",
    ) -> RepositoryListResponse:
        warnings: list[str] = []
        if query and query.strip():
            # GitHub search API: restrict to repositories the token can see.
            user = await self.client.get_user()
            login = user.get("login", "")
            search_query = f"{query.strip()} user:{login}"
            raw_items = await self.client.search_repositories(
                search_query, page=page, per_page=per_page
            )
            has_more = len(raw_items) >= per_page
        else:
            raw_items = await self.client.list_repositories(
                page=page, per_page=per_page, visibility=visibility
            )
            has_more = bool(self.client.last_links.get("next"))

        repositories: list[Repository] = []
        for item in raw_items:
            try:
                repositories.append(to_repository(item))
            except Exception:
                warnings.append("Skipped a repository with an unexpected payload.")
        return RepositoryListResponse(
            repositories=repositories,
            page=page,
            per_page=per_page,
            has_more=has_more,
            total_returned=len(repositories),
            rate_limit=self.client.last_rate_limit,
            warnings=warnings,
        )

    async def get(self, owner: str, repo: str) -> Repository:
        raw = await self.client.get_repository(owner, repo)
        return to_repository(raw)

    async def default_branch(self, owner: str, repo: str) -> str:
        try:
            raw = await self.client.get_repository(owner, repo)
            return str(raw.get("default_branch") or "main")
        except GitHubError:
            return "main"
