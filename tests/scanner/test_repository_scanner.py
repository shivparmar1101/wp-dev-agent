from __future__ import annotations

from backend.models.file import ClassifiedFile
from backend.scanner.file_classifier import classify
from backend.scanner.repository_scanner import RepositoryScanner, ScanResult, build_tree


class FakeGitHubClient:
    def __init__(self, entries, truncated: bool = False):
        self.entries = entries
        self.truncated = truncated
        self.calls: list[tuple] = []

    async def get_tree(self, owner, repo, ref, recursive=True):
        self.calls.append((owner, repo, ref, recursive))
        return self.entries, self.truncated


ENTRIES = [
    {"path": "wp-config.php", "type": "blob", "size": 100},
    {"path": "index.php", "type": "blob", "size": 50},
    {"path": "wp-content", "type": "tree"},
    {"path": "wp-content/themes", "type": "tree"},
    {"path": "wp-content/themes/custom-theme", "type": "tree"},
    {"path": "wp-content/themes/custom-theme/functions.php", "type": "blob", "size": 400},
    {"path": "wp-content/themes/custom-theme/logo.png", "type": "blob", "size": 9000},
    {"path": "node_modules", "type": "tree"},
    {"path": "node_modules/lodash/index.js", "type": "blob", "size": 70000},
    {"path": "vendor/autoload.php", "type": "blob", "size": 10},
    {"path": "src/app.php", "type": "blob", "size": 10_000_000},
    {"path": ".env", "type": "blob", "size": 40},
]


def test_is_ignored_patterns(settings):
    scanner = RepositoryScanner(FakeGitHubClient([]), settings)
    assert scanner.is_ignored("node_modules/lodash/index.js")
    assert scanner.is_ignored("vendor/pkg/src.php")
    assert scanner.is_ignored("dist/bundle.js")
    assert scanner.is_ignored(".git/config")
    assert not scanner.is_ignored("wp-content/themes/custom-theme/functions.php")


async def test_scan_filters_and_classifies(settings):
    scanner = RepositoryScanner(FakeGitHubClient(ENTRIES), settings)
    result = await scanner.scan("acme", "site", "main")

    paths = set(result.all_paths)
    # ignored directories and blocked files are excluded
    assert not any(p.startswith("node_modules") for p in paths)
    assert not any(p.startswith("vendor/") for p in paths)
    assert ".env" not in paths
    assert result.blocked_entries >= 1
    assert result.ignored_entries >= 2

    # oversized files are in the tree but not in the read set
    source_paths = {f.path for f in result.files}
    assert "src/app.php" not in source_paths
    assert result.too_large == 1

    # binary files are excluded from the read set too
    assert "wp-content/themes/custom-theme/logo.png" not in source_paths
    assert "wp-content/themes/custom-theme/functions.php" in source_paths

    # counts include binary categories (tree info) but files list stays source-only
    assert result.counts["image"] == 1
    assert result.tree is not None


async def test_scan_handles_truncated_tree(settings):
    scanner = RepositoryScanner(FakeGitHubClient(ENTRIES, truncated=True), settings)
    result = await scanner.scan("acme", "site", "main")
    assert result.api_truncated is True
    assert any("truncated" in note.lower() for note in result.notes)


def test_build_tree_structure():
    root, truncated = build_tree(
        ["wp-content/themes/custom-theme/functions.php", "wp-config.php"]
    )
    names = {child.name for child in root.children}
    assert names == {"wp-content", "wp-config.php"}
    wp_content = next(c for c in root.children if c.name == "wp-content")
    assert wp_content.type == "dir"
    assert truncated is False


def test_build_tree_truncation_limit():
    paths = [f"dir/file{i}.php" for i in range(50)]
    root, truncated = build_tree(paths, max_nodes=10)
    assert truncated is True


def test_scan_result_source_files_property():
    scan = ScanResult(owner="a", repo="b", ref="main")
    scan.files.append(ClassifiedFile(**classify("a.php").model_dump()))
    scan.files.append(ClassifiedFile(**classify("a.png").model_dump()))
    assert [f.path for f in scan.source_files] == ["a.php"]
