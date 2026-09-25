from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RateLimitInfo(BaseModel):
    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None
    used: int | None = None
    resource: str | None = None


class Repository(BaseModel):
    id: int
    name: str
    full_name: str
    owner: str
    owner_avatar: str | None = None
    description: str | None = None
    private: bool = False
    fork: bool = False
    archived: bool = False
    disabled: bool = False
    visibility: str = "public"
    default_branch: str = "main"
    language: str | None = None
    html_url: str
    updated_at: datetime | None = None
    pushed_at: datetime | None = None
    size_kb: int = 0
    stargazers_count: int = 0
    topics: list[str] = Field(default_factory=list)

    @property
    def status_labels(self) -> list[str]:
        labels: list[str] = []
        if self.private:
            labels.append("private")
        if self.archived:
            labels.append("archived")
        if self.fork:
            labels.append("fork")
        if self.disabled:
            labels.append("disabled")
        return labels


class RepositoryListResponse(BaseModel):
    repositories: list[Repository] = Field(default_factory=list)
    page: int = 1
    per_page: int = 30
    has_more: bool = False
    total_returned: int = 0
    rate_limit: RateLimitInfo | None = None
    warnings: list[str] = Field(default_factory=list)


class ScanJobRecord(BaseModel):
    scan_id: str
    owner: str
    repo: str
    branch: str | None = None
    status: str = "pending"
    created_at: datetime
    updated_at: datetime | None = None
