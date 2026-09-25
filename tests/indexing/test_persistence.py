from __future__ import annotations

from backend.indexing import persistence
from backend.indexing.indexer import IndexRegistry, RepositoryIndexer


async def _build(settings, wp_scan, dict_reader):
    return await RepositoryIndexer(dict_reader.read, settings).build(wp_scan)


async def test_save_then_load_roundtrip(settings, wp_scan, dict_reader, tmp_path):
    index = await _build(settings, wp_scan, dict_reader)
    assert persistence.save(index, tmp_path) is True

    loaded = persistence.load(index.owner, index.repo, tmp_path)

    assert loaded is not None
    assert (loaded.owner, loaded.repo, loaded.branch) == (
        index.owner,
        index.repo,
        index.branch,
    )
    assert loaded.chunks == index.chunks
    assert loaded.files == index.files
    assert loaded.stats == index.stats
    assert loaded.notes == index.notes
    # derived structures are rebuilt lazily, never persisted
    assert loaded.lexical is None


def test_load_returns_none_when_file_missing(tmp_path):
    assert persistence.load("nobody", "nothing", tmp_path) is None


def test_load_returns_none_for_corrupt_file(tmp_path):
    (tmp_path / "acme__site.json").write_text("{ not json", encoding="utf-8")
    assert persistence.load("acme", "site", tmp_path) is None


def test_load_ignores_unsupported_format_version(tmp_path):
    (tmp_path / "acme__site.json").write_text(
        '{"version": 999, "owner": "acme", "repo": "site"}', encoding="utf-8"
    )
    assert persistence.load("acme", "site", tmp_path) is None


def test_load_returns_none_for_directory_without_index(tmp_path):
    (tmp_path / "acme__site.json").mkdir()
    assert persistence.load("acme", "site", tmp_path) is None


async def test_registry_hydrates_from_disk_after_clear(
    settings, wp_scan, dict_reader, tmp_path
):
    registry = IndexRegistry(storage_dir=tmp_path)
    index = await _build(settings, wp_scan, dict_reader)
    registry.put(index)
    assert registry.save(index) is True

    registry.clear()
    assert registry.get(index.owner, index.repo) is None

    loaded = registry.get_or_load(index.owner, index.repo)
    assert loaded is not None
    assert loaded.chunks == index.chunks
    assert loaded.files == index.files
    # a second call serves the hydrated in-memory copy
    assert registry.get_or_load(index.owner, index.repo) is loaded


async def test_registry_get_or_load_returns_none_without_persisted_copy(tmp_path):
    registry = IndexRegistry(storage_dir=tmp_path)
    assert registry.get_or_load("acme", "missing") is None


async def test_registry_hydrates_after_lru_eviction(settings, wp_scan, dict_reader, tmp_path):
    registry = IndexRegistry(max_entries=1, storage_dir=tmp_path)
    index = await _build(settings, wp_scan, dict_reader)
    registry.put(index)
    assert registry.save(index) is True

    # Force eviction with a second index for a different repository.
    from backend.indexing.indexer import RepositoryIndex

    registry.put(RepositoryIndex(owner="other", repo="thing", branch="main"))
    assert registry.get(index.owner, index.repo) is None

    assert registry.get_or_load(index.owner, index.repo) is not None
