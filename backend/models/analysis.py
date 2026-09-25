from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from .project import IndexStats


class SearchMode(str, Enum):
    hybrid = "hybrid"
    keyword = "keyword"
    exact = "exact"
    file = "file"
    semantic = "semantic"


class SearchRequest(BaseModel):
    query: str
    mode: SearchMode | str = SearchMode.hybrid
    limit: int = Field(default=10, ge=1, le=50)


class SearchHit(BaseModel):
    file_path: str
    score: float
    start_line: int | None = None
    end_line: int | None = None
    snippet: str = ""
    match_type: str = "keyword"
    language: str | None = None
    matched_terms: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    mode_requested: str
    mode_used: str
    hits: list[SearchHit] = Field(default_factory=list)
    total: int = 0
    took_ms: int = 0
    index: IndexStats | None = None
    notes: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)
    conversation_id: str | None = None


class CodeReference(BaseModel):
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    snippet: str = ""
    language: str | None = None
    note: str | None = None


class AnalysisResponse(BaseModel):
    issue: str
    relevant_files: list[CodeReference] = Field(default_factory=list)
    cause: str = ""
    suggested_solution: str = ""
    solution_language: str | None = None
    confidence: Literal["High", "Medium", "Low", "Unknown"] = "Unknown"
    explanation: str = ""
    raw: str = ""
    search_terms: list[str] = Field(default_factory=list)
    mode_used: str = "hybrid"
    files_consulted: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: str = "unknown"
    model: str | None = None
    created_at: datetime | None = None


class ChatResponse(BaseModel):
    conversation_id: str | None = None
    analysis: AnalysisResponse
    request_id: str | None = None
