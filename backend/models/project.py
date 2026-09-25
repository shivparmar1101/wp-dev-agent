from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DetectionResult(BaseModel):
    """Generic multi-signal detection result."""

    detected: bool | None = None  # None => unknown
    confidence: float = 0.0
    indicators: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    signals: dict[str, float] = Field(default_factory=dict)


class WordPressDetection(BaseModel):
    is_wordpress: bool = False
    confidence: float = 0.0
    indicators: list[str] = Field(default_factory=list)
    signals: dict[str, float] = Field(default_factory=dict)
    content_markers: list[str] = Field(default_factory=list)
    wp_content_paths: list[str] = Field(default_factory=list)


class ThemeInfo(BaseModel):
    name: str
    slug: str
    location: str
    version: str | None = None
    author: str | None = None
    description: str | None = None
    theme_type: Literal["custom", "child", "parent", "known", "unknown"] = "unknown"
    parent_theme: str | None = None
    block_theme: bool = False
    has_functions_php: bool = False
    text_domain: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class PluginInfo(BaseModel):
    name: str
    slug: str
    location: str
    version: str | None = None
    author: str | None = None
    description: str | None = None
    text_domain: str | None = None
    main_file: str | None = None
    known: bool = False
    metadata_source: Literal["plugin_header", "directory", "unknown"] = "unknown"
    headers: dict[str, str] = Field(default_factory=dict)


class ElementorDetection(BaseModel):
    elementor: Literal["detected", "not_detected", "unknown"] = "unknown"
    elementor_pro: Literal["detected", "not_detected", "unknown"] = "unknown"
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    signals: dict[str, float] = Field(default_factory=dict)


class IndexStats(BaseModel):
    files_indexed: int = 0
    chunks: int = 0
    files_skipped: int = 0
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
    embeddings_enabled: bool = False
    languages: dict[str, int] = Field(default_factory=dict)
    built_at: datetime | None = None


class ProjectSummary(BaseModel):
    repository: str
    owner: str
    repo: str
    branch: str
    description: str | None = None
    project_types: list[str] = Field(default_factory=list)
    is_wordpress: bool = False
    wordpress_confidence: float = 0.0
    wordpress_indicators: list[str] = Field(default_factory=list)
    elementor: ElementorDetection = Field(default_factory=ElementorDetection)
    themes: list[ThemeInfo] = Field(default_factory=list)
    plugins: list[PluginInfo] = Field(default_factory=list)
    file_counts: dict[str, int] = Field(default_factory=dict)
    total_files: int = 0
    source_files: int = 0
    languages: list[str] = Field(default_factory=list)
    tech: dict[str, bool] = Field(default_factory=dict)
    index: IndexStats | None = None
    notes: list[str] = Field(default_factory=list)
    scanned_at: datetime


class StageStatus(BaseModel):
    id: str
    label: str
    status: Literal["pending", "running", "done", "error", "skipped"] = "pending"
    detail: str | None = None


class ScanStatus(BaseModel):
    scan_id: str
    owner: str
    repo: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    progress: float = 0.0
    stages: list[StageStatus] = Field(default_factory=list)
    error: str | None = None
    error_details: str | None = None
    branch: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: ProjectSummary | None = None
