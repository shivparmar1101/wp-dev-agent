from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FileClassification(BaseModel):
    path: str
    name: str
    extension: str = ""
    category: str = "other"
    language: str | None = None
    is_source: bool = False
    is_binary: bool = False
    is_wordpress_file: bool = False
    size: int | None = None


class ClassifiedFile(FileClassification):
    """A repository file selected for scanning/indexing."""


class FileNode(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"]
    size: int | None = None
    language: str | None = None
    category: str | None = None
    wordpress: bool = False
    children: list["FileNode"] = Field(default_factory=list)


class FileContent(BaseModel):
    path: str
    content: str
    size: int = 0
    language: str | None = None
    category: str = "other"
    encoding: str = "utf-8"
    truncated: bool = False
    redacted: bool = False
    ref: str | None = None


class FileListResponse(BaseModel):
    files: list[ClassifiedFile] = Field(default_factory=list)
    total: int = 0
    skipped: int = 0
    truncated_tree: bool = False
    notes: list[str] = Field(default_factory=list)


FileNode.model_rebuild()
