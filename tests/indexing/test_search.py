from __future__ import annotations

import pytest

from backend.indexing.indexer import RepositoryIndexer
from backend.indexing.search import SearchService, query_terms, tokenize


@pytest.fixture
async def service(settings, wp_scan, dict_reader, registry_clean):
    index = await RepositoryIndexer(dict_reader.read, settings).build(wp_scan)
    registry_clean.put(index)
    return SearchService(registry=registry_clean)


def test_tokenize_splits_identifiers():
    tokens = tokenize("wp_enqueue_style and .header-container mobileMenu")
    assert "wp" in tokens and "enqueue" in tokens and "style" in tokens
    assert "header" in tokens and "container" in tokens
    assert "mobile" in tokens and "menu" in tokens


def test_query_terms_drop_stopwords():
    assert query_terms("Why is the mobile header overflowing on phones?") == [
        "mobile", "header", "overflowing", "phones"
    ]


async def test_keyword_search_ranks_relevant_file_first(service):
    response = await service.search(
        "acme", "client-wordpress-site", "mobile header overflow", mode="keyword", limit=5
    )
    assert response.hits
    assert response.hits[0].file_path.endswith("responsive.css")
    assert response.mode_used == "keyword"
    assert response.hits[0].start_line is not None


async def test_exact_search_finds_selector(service):
    response = await service.search(
        "acme", "client-wordpress-site", ".header-container", mode="exact", limit=5
    )
    assert response.mode_used == "exact"
    paths = {h.file_path for h in response.hits}
    assert any(p.endswith("responsive.css") for p in paths)
    assert all(h.match_type.startswith("exact") for h in response.hits)


async def test_exact_search_reports_missing_matches(service):
    response = await service.search(
        "acme", "client-wordpress-site", ".no-such-selector-zzz", mode="exact", limit=5
    )
    assert response.hits == []


async def test_file_search_by_name(service):
    response = await service.search(
        "acme", "client-wordpress-site", "functions.php", mode="file", limit=5
    )
    assert response.hits
    assert response.hits[0].file_path.endswith("functions.php")


async def test_hybrid_search_without_embeddings_uses_keyword(service):
    response = await service.search(
        "acme", "client-wordpress-site", "where is the contact form email configured",
        mode="hybrid", limit=5,
    )
    assert response.mode_used == "keyword"
    assert any("Semantic search is not configured" in note for note in response.notes)


class FakeEmbeddings:
    """Deterministic vectors so cosine ranking is stable across runs."""

    async def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * 8
            vector[sum(ord(char) for char in text) % 8] = 1.0
            vectors.append(vector)
        return vectors


class BrokenEmbeddings:
    async def embed(self, texts):
        return None


async def test_hybrid_search_with_embeddings_is_ranked_semantically(
    settings, wp_scan, dict_reader, registry_clean
):
    index = await RepositoryIndexer(dict_reader.read, settings).build(wp_scan)
    registry_clean.put(index)
    service = SearchService(registry=registry_clean, embeddings=FakeEmbeddings())

    response = await service.search(
        "acme", "client-wordpress-site", "where is the contact form email configured",
        mode="hybrid", limit=5,
    )

    assert response.mode_used == "hybrid"
    assert response.hits
    assert not any("Semantic search is not configured" in note for note in response.notes)
    assert not any("Embeddings request failed" in note for note in response.notes)


async def test_hybrid_search_falls_back_when_embeddings_fail(
    settings, wp_scan, dict_reader, registry_clean
):
    index = await RepositoryIndexer(dict_reader.read, settings).build(wp_scan)
    registry_clean.put(index)
    service = SearchService(registry=registry_clean, embeddings=BrokenEmbeddings())

    response = await service.search(
        "acme", "client-wordpress-site", "where is the contact form email configured",
        mode="hybrid", limit=5,
    )

    assert response.hits
    assert any("Embeddings request failed" in note for note in response.notes)


async def test_semantic_rerank_resolves_match_subranges_to_chunks(
    settings, wp_scan, dict_reader, registry_clean
):
    """Real keyword hits point at matched lines, not at chunk boundaries."""
    from backend.models.analysis import SearchHit

    index = await RepositoryIndexer(dict_reader.read, settings).build(wp_scan)
    registry_clean.put(index)
    chunk = max(index.chunks, key=lambda c: c.end_line - c.start_line)
    assert chunk.end_line - chunk.start_line >= 3
    hit = SearchHit(
        file_path=chunk.file_path,
        score=1.0,
        start_line=chunk.start_line + 2,
        end_line=chunk.end_line,
    )
    service = SearchService(registry=registry_clean, embeddings=FakeEmbeddings())

    reranked, notes = await service._semantic_rerank(index, "header styles", [hit], 5)

    assert len(reranked) == 1
    assert reranked[0].match_type == "semantic"
    assert notes == []


async def test_semantic_rerank_skips_hits_outside_the_index(
    settings, wp_scan, dict_reader, registry_clean
):
    from backend.models.analysis import SearchHit

    index = await RepositoryIndexer(dict_reader.read, settings).build(wp_scan)
    registry_clean.put(index)
    hit = SearchHit(file_path="ghost.php", score=1.0, start_line=1, end_line=5)
    service = SearchService(registry=registry_clean, embeddings=FakeEmbeddings())

    reranked, notes = await service._semantic_rerank(index, "anything", [hit], 5)

    assert reranked == []
    assert notes == []


async def test_search_missing_index_raises(settings):
    service = SearchService()
    with pytest.raises(LookupError):
        await service.search("nobody", "nothing", "query")


async def test_results_are_diverse_per_file(service):
    response = await service.search(
        "acme", "client-wordpress-site", "php", mode="keyword", limit=10
    )
    per_file: dict[str, int] = {}
    for hit in response.hits:
        per_file[hit.file_path] = per_file.get(hit.file_path, 0) + 1
    assert all(count <= 3 for count in per_file.values())


async def test_search_result_includes_index_stats(service):
    response = await service.search("acme", "client-wordpress-site", "header")
    assert response.index is not None
    assert response.index.chunks > 0
