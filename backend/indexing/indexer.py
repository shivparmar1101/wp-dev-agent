from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from backend.config import Settings, get_settings
from backend.models.project import IndexStats
from backend.scanner.file_classifier import is_indexable
from backend.scanner.repository_scanner import ScanResult
from backend.utils.helpers import utcnow
from backend.utils.logging import get_logger
from backend.utils.security import is_blocked_path, looks_like_prompt_injection

from .chunker import Chunk, chunk_file

logger = get_logger(__name__)

ReadFn = Callable[[str], Awaitable[str | None]]
ProgressFn = Callable[[str, str], Awaitable[None]]

_LANGUAGE_GROUPS: dict[str, set[str]] = {
    "indexing_php": {"php"},
    "indexing_css": {"css", "scss", "sass", "less"},
    "indexing_javascript": {
        "javascript",
        "typescript",
        "jsx",
        "tsx",
        "vue",
        "svelte",
        "mjs",
        "cjs",
    },
}


@dataclass
class IndexedFile:
    path: str
    language: str | None
    category: str
    size: int
    chunk_count: int
    lines: int = 0


@dataclass
class RepositoryIndex:
    owner: str
    repo: str
    branch: str
    files: dict[str, IndexedFile] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)
    stats: IndexStats = field(default_factory=IndexStats)
    notes: list[str] = field(default_factory=list)
    lexical: "object | None" = field(default=None, repr=False)

    @property
    def key(self) -> tuple[str, str]:
        return (self.owner, self.repo)


class IndexRegistry:
    """LRU registry of in-memory repository indexes (one process)."""

    def __init__(self, max_entries: int = 5):
        self.max_entries = max_entries
        self._entries: OrderedDict[tuple[str, str], RepositoryIndex] = OrderedDict()

    def get(self, owner: str, repo: str) -> RepositoryIndex | None:
        key = (owner.lower(), repo.lower())
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
        return entry

    def put(self, index: RepositoryIndex) -> None:
        key = (index.owner.lower(), index.repo.lower())
        self._entries[key] = index
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            evicted_key, evicted = self._entries.popitem(last=False)
            logger.info("Evicted index for %s/%s", *evicted_key)

    def remove(self, owner: str, repo: str) -> None:
        self._entries.pop((owner.lower(), repo.lower()), None)

    def clear(self) -> None:
        self._entries.clear()

    def __contains__(self, item: object) -> bool:
        if isinstance(item, tuple) and len(item) == 2:
            return (str(item[0]).lower(), str(item[1]).lower()) in self._entries
        return False

    def __len__(self) -> int:
        return len(self._entries)


class RepositoryIndexer:
    """Builds a chunked, searchable index of a scanned repository."""

    def __init__(self, read: ReadFn, settings: Settings | None = None):
        self.read = read
        self.settings = settings or get_settings()

    async def build(
        self, scan: ScanResult, *, progress: ProgressFn | None = None
    ) -> RepositoryIndex:
        index = RepositoryIndex(
            owner=scan.owner, repo=scan.repo, branch=scan.ref, notes=list(scan.notes)
        )
        skipped: dict[str, int] = {}
        languages: dict[str, int] = {}

        candidates = [
            f
            for f in scan.files
            if is_indexable(f) and not is_blocked_path(f.path)
        ]
        capped = False
        if len(candidates) > self.settings.max_indexed_files:
            candidates = candidates[: self.settings.max_indexed_files]
            capped = True
            index.notes.append(
                "This repository has more files than the MVP indexes; only the "
                f"first {self.settings.max_indexed_files} supported source files were indexed."
            )

        groups: dict[str, list] = {"indexing_php": [], "indexing_css": [], "indexing_javascript": [], "other": []}
        for item in candidates:
            placed = False
            for group, langs in _LANGUAGE_GROUPS.items():
                if (item.language or "") in langs:
                    groups[group].append(item)
                    placed = True
                    break
            if not placed:
                groups["other"].append(item)

        injection_hits = 0
        total_files = 0

        for group_name, items in groups.items():
            if not items:
                if progress and group_name in _LANGUAGE_GROUPS:
                    await progress(group_name, "No matching files")
                continue
            group_files = 0
            for batch_start in range(0, len(items), 6):
                batch = items[batch_start : batch_start + 6]
                contents = await asyncio.gather(
                    *(self.read(item.path) for item in batch), return_exceptions=True
                )
                for item, content in zip(batch, contents):
                    if isinstance(content, BaseException):
                        skipped["read_error"] = skipped.get("read_error", 0) + 1
                        logger.debug("Index read failed for %s", item.path)
                        continue
                    if content is None:
                        skipped["binary_or_unreadable"] = skipped.get("binary_or_unreadable", 0) + 1
                        continue
                    if not content.strip():
                        skipped["empty"] = skipped.get("empty", 0) + 1
                        continue
                    if looks_like_prompt_injection(content):
                        injection_hits += 1

                    text = content
                    if len(text) > self.settings.max_index_file_bytes:
                        text = text[: self.settings.max_index_file_bytes]

                    chunks = chunk_file(
                        text,
                        item.path,
                        item.language,
                        max_lines=self.settings.chunk_max_lines,
                        overlap=self.settings.chunk_overlap_lines,
                        max_chars=self.settings.chunk_max_chars,
                    )
                    if not chunks:
                        skipped["no_chunks"] = skipped.get("no_chunks", 0) + 1
                        continue

                    index.files[item.path] = IndexedFile(
                        path=item.path,
                        language=item.language,
                        category=item.category,
                        size=item.size,
                        chunk_count=len(chunks),
                        lines=text.count("\n") + 1,
                    )
                    index.chunks.extend(chunks)
                    languages[item.language or "text"] = languages.get(item.language or "text", 0) + 1
                    group_files += 1
                    total_files += 1

            if progress and group_name in _LANGUAGE_GROUPS:
                label = group_name.replace("indexing_", "").upper()
                await progress(group_name, f"Indexed {group_files} {label} file(s)")
            elif progress and group_name == "other" and items:
                await progress("building_index", f"Indexed {group_files} additional file(s)")

        if capped:
            skipped["max_indexed_files"] = skipped.get("max_indexed_files", 0) + max(
                0, len(scan.files) - self.settings.max_indexed_files
            )

        index.stats = IndexStats(
            files_indexed=total_files,
            chunks=len(index.chunks),
            files_skipped=sum(skipped.values()),
            skipped_reasons=skipped,
            embeddings_enabled=False,
            languages=dict(sorted(languages.items(), key=lambda kv: -kv[1])),
            built_at=utcnow(),
        )
        if injection_hits:
            index.notes.append(
                f"{injection_hits} file(s) contain instruction-like text; "
                "repository content is always treated as untrusted data."
            )
        if not index.chunks:
            index.notes.append("No indexable source content was found.")

        index.chunks.sort(key=lambda c: (c.file_path, c.start_line))
        for position, chunk in enumerate(index.chunks):
            chunk.index = position
        return index


# Process-wide registry used by API routes.
registry = IndexRegistry()
