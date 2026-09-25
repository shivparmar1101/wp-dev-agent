from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from backend.config import Settings, get_settings
from backend.github.client import GitHubClient, GitHubEmptyRepositoryError, GitHubError
from backend.models.file import ClassifiedFile, FileNode
from backend.utils.logging import get_logger
from backend.utils.security import is_blocked_path

from .file_classifier import classify, is_indexable

logger = get_logger(__name__)

ProgressCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class ScanResult:
    owner: str
    repo: str
    ref: str
    files: list[ClassifiedFile] = field(default_factory=list)
    all_paths: list[str] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)
    tree: FileNode | None = None
    counts: dict[str, int] = field(default_factory=dict)
    total_entries: int = 0
    ignored_entries: int = 0
    blocked_entries: int = 0
    too_large: int = 0
    api_truncated: bool = False
    tree_truncated: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def source_files(self) -> list[ClassifiedFile]:
        return [f for f in self.files if f.is_source]


def build_tree(
    paths: list[str],
    *,
    max_nodes: int = 6000,
    classify_meta: dict[str, tuple[str | None, str | None, bool]] | None = None,
) -> tuple[FileNode, bool]:
    """Builds a nested file tree from flat paths. Returns (root, truncated)."""
    root = FileNode(name="", path="", type="dir")
    nodes: dict[str, FileNode] = {"": root}
    truncated = False

    for path in sorted(paths):
        if len(nodes) >= max_nodes:
            truncated = True
            break
        parts = path.split("/")
        current_path = ""
        parent = root
        for index, part in enumerate(parts):
            current_path = f"{current_path}/{part}" if current_path else part
            is_leaf = index == len(parts) - 1
            node = nodes.get(current_path)
            if node is None:
                node_type = "file" if is_leaf else "dir"
                language = category = None
                wordpress = False
                if is_leaf and classify_meta and current_path in classify_meta:
                    language, category, wordpress = classify_meta[current_path]
                node = FileNode(
                    name=part,
                    path=current_path,
                    type=node_type,  # type: ignore[arg-type]
                    language=language,
                    category=category,
                    wordpress=wordpress,
                )
                nodes[current_path] = node
                parent.children.append(node)
            parent = node
            if is_leaf:
                break
    return root, truncated


class RepositoryScanner:
    """Retrieves and filters a repository tree without downloading every file."""

    def __init__(self, client: GitHubClient, settings: Settings | None = None):
        self.client = client
        self.settings = settings or get_settings()
        self._ignored = sorted(self.settings.ignored_path_set(), key=len, reverse=True)

    def is_ignored(self, path: str) -> bool:
        lowered = path.lower()
        for segment in lowered.split("/"):
            for pattern in self._ignored:
                if fnmatch.fnmatch(segment, pattern) or segment == pattern:
                    return True
        for pattern in self._ignored:
            if "/" in pattern and fnmatch.fnmatch(lowered, pattern):
                return True
        return False

    async def scan(
        self,
        owner: str,
        repo: str,
        ref: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> ScanResult:
        result = ScanResult(owner=owner, repo=repo, ref=ref)

        if progress:
            await progress("reading_tree", f"Fetching tree for {ref}")
        try:
            tree_entries, api_truncated = await self.client.get_tree(
                owner, repo, ref, recursive=True
            )
        except GitHubEmptyRepositoryError:
            result.notes.append("Repository has no commits yet.")
            result.tree = FileNode(name="", path="", type="dir")
            return result
        except GitHubError:
            raise

        result.api_truncated = api_truncated
        if api_truncated:
            result.notes.append(
                "GitHub truncated the tree for this large repository; "
                "only part of the file structure could be read."
            )

        classified_meta: dict[str, tuple[str | None, str | None, bool]] = {}
        visible_paths: list[str] = []

        for entry in tree_entries:
            entry_type = entry.get("type")
            path = str(entry.get("path") or "")
            if not path:
                continue
            result.total_entries += 1

            if entry_type == "tree":
                if self.is_ignored(path) or is_blocked_path(path):
                    result.ignored_entries += 1
                    continue
                result.dirs.append(path)
                visible_paths.append(path)
                continue

            if entry_type != "blob":
                continue  # commits / submodules

            if self.is_ignored(path):
                result.ignored_entries += 1
                continue
            if is_blocked_path(path):
                result.blocked_entries += 1
                continue

            size = int(entry.get("size") or 0)
            classification = classify(path, size)
            visible_paths.append(path)
            result.all_paths.append(path)
            classified_meta[path] = (
                classification.language,
                classification.category,
                classification.is_wordpress_file,
            )
            result.counts[classification.category] = (
                result.counts.get(classification.category, 0) + 1
            )

            if size > self.settings.max_file_bytes:
                result.too_large += 1
                continue
            if not classification.is_source:
                continue

            result.files.append(ClassifiedFile(**classification.model_dump()))

        result.files.sort(key=lambda f: f.path)
        result.tree, result.tree_truncated = build_tree(
            visible_paths,
            max_nodes=self.settings.max_tree_nodes,
            classify_meta=classified_meta,
        )
        for node in _iter_nodes(result.tree):
            node.size = None
        if result.tree_truncated:
            result.notes.append(
                "File tree display truncated because the repository is very large."
            )
        if not result.files and not result.all_paths:
            result.notes.append("No scannable files were found in this repository.")
        return result


def _iter_nodes(node: FileNode):
    for child in node.children:
        yield child
        if child.type == "dir":
            yield from _iter_nodes(child)
