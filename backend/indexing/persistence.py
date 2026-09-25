from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from backend.config import get_settings
from backend.models.project import IndexStats
from backend.utils.logging import get_logger

from .chunker import Chunk
from .indexer import IndexedFile, RepositoryIndex

logger = get_logger(__name__)

#: Bump when the on-disk layout changes; stale files are then ignored.
FORMAT_VERSION = 1

_CHUNK_FIELDS = (
    "file_path",
    "start_line",
    "end_line",
    "content",
    "language",
    "index",
    "truncated",
)


def default_directory() -> Path:
    """Directory holding persisted indexes (next to the SQLite database)."""
    return get_settings().sqlite_path().parent / "indexes"


def _path_for(owner: str, repo: str, directory: Path) -> Path:
    raw = f"{owner}__{repo}".lower()
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in raw)
    return directory / f"{safe}.json"


def save(index: RepositoryIndex, directory: Path | None = None) -> bool:
    """Persist an index to disk so it survives process restarts.

    Returns True on success. Failures are logged and swallowed: losing the
    persisted copy degrades to a re-scan, it never breaks the scan itself.
    """
    target_dir = directory if directory is not None else default_directory()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": FORMAT_VERSION,
            "owner": index.owner,
            "repo": index.repo,
            "branch": index.branch,
            "notes": index.notes,
            "stats": index.stats.model_dump(mode="json"),
            "files": {path: asdict(meta) for path, meta in index.files.items()},
            "chunks": [
                {field: getattr(chunk, field) for field in _CHUNK_FIELDS}
                for chunk in index.chunks
            ],
        }
        destination = _path_for(index.owner, index.repo, target_dir)
        tmp = destination.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, destination)
        logger.info(
            "Persisted index for %s/%s (%d chunks) -> %s",
            index.owner,
            index.repo,
            len(index.chunks),
            destination,
        )
        return True
    except Exception as exc:
        logger.warning("Could not persist index for %s/%s: %s", index.owner, index.repo, exc)
        return False


def load(owner: str, repo: str, directory: Path | None = None) -> RepositoryIndex | None:
    """Load a previously persisted index, or None when absent/corrupt.

    The derived `lexical` structure is intentionally not stored — it is rebuilt
    lazily by `SearchService` on first use.
    """
    target_dir = directory if directory is not None else default_directory()
    path = _path_for(owner, repo, target_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != FORMAT_VERSION:
            logger.info("Ignoring index with unsupported version at %s", path)
            return None
        chunks = [
            Chunk(**{field: item[field] for field in _CHUNK_FIELDS})
            for item in payload.get("chunks", [])
        ]
        files = {
            str(path_key): IndexedFile(**meta)
            for path_key, meta in payload.get("files", {}).items()
        }
        index = RepositoryIndex(
            owner=payload["owner"],
            repo=payload["repo"],
            branch=payload.get("branch", ""),
            files=files,
            chunks=chunks,
            stats=IndexStats.model_validate(payload.get("stats") or {}),
            notes=list(payload.get("notes") or []),
        )
        logger.info(
            "Loaded persisted index for %s/%s (%d chunks)", owner, repo, len(chunks)
        )
        return index
    except Exception as exc:
        logger.warning("Could not load persisted index for %s/%s: %s", owner, repo, exc)
        return None


def delete(owner: str, repo: str, directory: Path | None = None) -> None:
    target_dir = directory if directory is not None else default_directory()
    try:
        _path_for(owner, repo, target_dir).unlink(missing_ok=True)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not delete persisted index for %s/%s: %s", owner, repo, exc)
