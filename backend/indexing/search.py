from __future__ import annotations

import math
import re
import time

from backend.config import Settings, get_settings
from backend.models.analysis import SearchHit, SearchMode, SearchResponse
from backend.utils.logging import get_logger

from .chunker import Chunk, snippet_for
from .embeddings import EmbeddingsProvider, cosine_similarity, embed_texts
from .indexer import IndexRegistry, RepositoryIndex, registry as default_registry

logger = get_logger(__name__)

STOPWORDS = frozenset(
    """
    a an the and or but if then else when while for to of in on at by with from
    as is are was were be been being do does did doing have has had having
    i me my we our you your he she it its they them their this that these those
    what which who whom whose where why how not no nor so too very can could
    should would will shall may might must about above after again against all
    am any because before below between both during each few further into just
    more most other some such than through under until up down out off over
    own same s t don now please find show tell explain give get make know
    think look like also there here than per via using use used use case
    """.split()
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        parts = _CAMEL_RE.findall(raw) or [raw]
        for part in parts:
            lowered = part.lower()
            if lowered and lowered not in STOPWORDS:
                tokens.append(lowered)
            elif raw.isdigit():
                tokens.append(lowered)
    return tokens


def query_terms(query: str) -> list[str]:
    terms = tokenize(query)
    if not terms:
        terms = [t for t in _TOKEN_RE.findall(query.lower()) if t]
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


class LexicalIndex:
    """BM25 (k1=1.5, b=0.75) over repository chunks."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.tfs: list[dict[str, int]] = []
        self.lengths: list[int] = []
        self.df: dict[str, int] = {}
        for chunk in chunks:
            tf: dict[str, int] = {}
            tokens = tokenize(chunk.content)
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            for token in tf:
                self.df[token] = self.df.get(token, 0) + 1
            self.tfs.append(tf)
            self.lengths.append(len(tokens))
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        self.n = len(chunks)

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def search(
        self, terms: list[str], *, top_n: int = 60
    ) -> list[tuple[int, float, list[str]]]:
        results: list[tuple[int, float, list[str]]] = []
        if not terms or not self.chunks:
            return results
        k1, b = 1.5, 0.75
        for index, tf in enumerate(self.tfs):
            score = 0.0
            matched: list[str] = []
            length = self.lengths[index] or 1
            for term in terms:
                freq = tf.get(term)
                if not freq:
                    continue
                matched.append(term)
                idf = self.idf(term)
                denom = freq + k1 * (1 - b + b * length / (self.avg_len or 1.0))
                score += idf * (freq * (k1 + 1)) / denom
            if score <= 0:
                continue
            path = self.chunks[index].file_path.lower()
            path_hits = sum(1 for term in terms if term in path)
            if path_hits:
                score += 0.6 * path_hits
                basename = self.chunks[index].file_path.rsplit("/", 1)[-1].lower()
                if all(term in basename for term in terms):
                    score += 1.0
            results.append((index, score, matched))
        results.sort(key=lambda item: -item[1])
        return results[:top_n]


class SearchService:
    """Repository-aware keyword / exact / file / semantic search."""

    def __init__(
        self,
        registry: IndexRegistry | None = None,
        embeddings: EmbeddingsProvider | None = None,
        settings: Settings | None = None,
    ):
        self.registry = registry or default_registry
        self.embeddings = embeddings
        self.settings = settings or get_settings()

    def _lexical(self, index: RepositoryIndex) -> LexicalIndex:
        if index.lexical is None:
            index.lexical = LexicalIndex(index.chunks)
        return index.lexical  # type: ignore[return-value]

    def get_index(self, owner: str, repo: str) -> RepositoryIndex | None:
        return self.registry.get_or_load(owner, repo)

    async def search(
        self,
        owner: str,
        repo: str,
        query: str,
        *,
        mode: str | SearchMode = SearchMode.hybrid,
        limit: int = 10,
    ) -> SearchResponse:
        index = self.registry.get_or_load(owner, repo)
        if index is None:
            raise LookupError("repository_index_missing")
        started = time.perf_counter()
        mode_value = mode.value if isinstance(mode, SearchMode) else str(mode)
        response = await self.search_index(index, query, mode=mode_value, limit=limit)
        response.took_ms = int((time.perf_counter() - started) * 1000)
        response.index = index.stats
        return response

    async def search_index(
        self,
        index: RepositoryIndex,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 10,
    ) -> SearchResponse:
        started = time.perf_counter()
        mode_requested = mode
        notes: list[str] = []
        hits: list[SearchHit] = []

        if mode == SearchMode.exact.value or mode == "exact":
            hits, notes = self._exact(index, query, limit)
            mode_used = "exact"
        elif mode == SearchMode.file.value or mode == "file":
            hits = self._file(index, query, limit)
            mode_used = "file"
        else:
            keyword_hits, keyword_notes = self._keyword(index, query, limit=max(limit * 4, 40))
            notes.extend(keyword_notes)
            hits = keyword_hits
            mode_used = "keyword"

            if mode in (SearchMode.semantic.value, SearchMode.hybrid.value, "semantic", "hybrid"):
                reranked, sem_notes = await self._semantic_rerank(index, query, keyword_hits, limit)
                notes.extend(sem_notes)
                if reranked:
                    if mode in (SearchMode.semantic.value, "semantic"):
                        hits = reranked
                        mode_used = "semantic" if self.embeddings else "keyword"
                    else:
                        hits = self._blend(keyword_hits, reranked, limit)

            if mode in (SearchMode.keyword.value, "keyword"):
                mode_used = "keyword"

        hits = self._dedupe(hits, limit)
        for position, hit in enumerate(hits):
            hit.score = round(hit.score, 4)

        elapsed = int((time.perf_counter() - started) * 1000)
        return SearchResponse(
            query=query,
            mode_requested=mode_requested,
            mode_used=mode_used,
            hits=hits,
            total=len(hits),
            took_ms=elapsed,
            notes=_unique(notes),
        )

    # -- modes -------------------------------------------------------------
    def _exact(
        self, index: RepositoryIndex, query: str, limit: int
    ) -> tuple[list[SearchHit], list[str]]:
        notes: list[str] = []
        needle = query.strip()
        if len(needle) < 2:
            return [], ["Exact search needs at least 2 characters."]

        hits: list[SearchHit] = []
        for chunk in index.chunks:
            if needle in chunk.file_path:
                hits.append(
                    SearchHit(
                        file_path=chunk.file_path,
                        score=2.0,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        snippet=_head(chunk),
                        match_type="path",
                        language=chunk.language,
                        matched_terms=[needle],
                    )
                )
            position = chunk.content.find(needle)
            if position == -1:
                continue
            line_offset = chunk.content.count("\n", 0, position)
            line = chunk.start_line + line_offset
            text, start, end = snippet_for(chunk.content, needle=needle, context_lines=4)
            hits.append(
                SearchHit(
                    file_path=chunk.file_path,
                    score=3.0,
                    start_line=chunk.start_line + start - 1,
                    end_line=chunk.start_line + end - 1,
                    snippet=text,
                    match_type="exact",
                    language=chunk.language,
                    matched_terms=[needle],
                )
            )
            if len(hits) >= limit * 3:
                break

        if not hits:
            lowered = needle.lower()
            for chunk in index.chunks:
                if lowered in chunk.content.lower():
                    text, start, end = snippet_for(chunk.content, needle=lowered, context_lines=4)
                    hits.append(
                        SearchHit(
                            file_path=chunk.file_path,
                            score=2.5,
                            start_line=chunk.start_line + start - 1,
                            end_line=chunk.start_line + end - 1,
                            snippet=text,
                            match_type="exact_ci",
                            language=chunk.language,
                            matched_terms=[needle],
                        )
                    )
                    if len(hits) >= limit * 3:
                        break
            if hits:
                notes.append("No case-sensitive match; showing case-insensitive results.")
        return hits, notes

    def _file(self, index: RepositoryIndex, query: str, limit: int) -> list[SearchHit]:
        needle = query.strip().lower()
        tokens = query_terms(query)
        # Generic extensions are not discriminating in file-name search.
        generic = {
            "php", "js", "jsx", "ts", "tsx", "css", "scss", "less", "html",
            "json", "yml", "yaml", "xml", "md", "txt", "twig", "vue",
        }
        specific = [t for t in tokens if t not in generic]
        tokens = specific or tokens or [needle]
        scored: list[tuple[str, float]] = []
        for path in index.files:
            lowered = path.lower()
            basename = lowered.rsplit("/", 1)[-1]
            score = 0.0
            if needle and basename == needle:
                score += 4.0
            elif needle and (basename == needle or needle in basename):
                score += 2.0
            for token in tokens:
                if token == basename or token + "." in basename:
                    score += 2.0
                elif token in lowered:
                    score += 1.0
            if score > 0:
                scored.append((path, score))
        scored.sort(key=lambda item: -item[1])

        hits: list[SearchHit] = []
        for path, score in scored[:limit]:
            file_chunks = [c for c in index.chunks if c.file_path == path]
            if not file_chunks:
                continue
            first = file_chunks[0]
            text, start, end = snippet_for(first.content, context_lines=8, max_chars=700)
            hits.append(
                SearchHit(
                    file_path=path,
                    score=score,
                    start_line=first.start_line,
                    end_line=first.start_line + (end - start),
                    snippet=text,
                    match_type="file",
                    language=first.language,
                    matched_terms=tokens,
                )
            )
        return hits

    def _keyword(
        self, index: RepositoryIndex, query: str, *, limit: int = 40
    ) -> tuple[list[SearchHit], list[str]]:
        notes: list[str] = []
        terms = query_terms(query)
        if not terms:
            return [], ["The query did not contain any searchable terms."]
        lexical = self._lexical(index)
        ranked = lexical.search(terms, top_n=limit)
        if not ranked:
            return [], ["No lexical matches found in the index."]

        max_score = ranked[0][1] or 1.0
        hits: list[SearchHit] = []
        for chunk_index, score, matched in ranked:
            chunk = index.chunks[chunk_index]
            needle = matched[0] if matched else None
            text, start, end = snippet_for(chunk.content, needle=needle, context_lines=5)
            hits.append(
                SearchHit(
                    file_path=chunk.file_path,
                    score=score / max_score,
                    start_line=chunk.start_line + start - 1,
                    end_line=chunk.start_line + end - 1,
                    snippet=text,
                    match_type="keyword",
                    language=chunk.language,
                    matched_terms=matched,
                )
            )
        return hits, notes

    async def _semantic_rerank(
        self,
        index: RepositoryIndex,
        query: str,
        keyword_hits: list[SearchHit],
        limit: int,
    ) -> tuple[list[SearchHit], list[str]]:
        if self.embeddings is None:
            return [], [
                "Semantic search is not configured (no embeddings provider); "
                "results are ranked lexically."
            ]
        candidates = keyword_hits[: max(limit * 6, 60)]
        if not candidates:
            return [], []
        chunks_by_key = {(c.file_path, c.start_line, c.end_line): c for c in index.chunks}
        candidate_chunks: list[Chunk] = []
        for hit in candidates:
            chunk = chunks_by_key.get((hit.file_path, hit.start_line, hit.end_line))
            if chunk is not None:
                candidate_chunks.append(chunk)
        if not candidate_chunks:
            return [], []

        vectors = await embed_texts(
            self.embeddings, [query] + [c.content[:2000] for c in candidate_chunks]
        )
        if not vectors:
            return [], ["Embeddings request failed; using lexical ranking."]

        query_vector = vectors[0]
        chunk_vectors = vectors[1:]
        scored: list[tuple[SearchHit, float]] = []
        for hit, vector in zip(candidates, chunk_vectors):
            similarity = max(0.0, cosine_similarity(query_vector, vector))
            scored.append((hit, similarity))
        scored.sort(key=lambda item: -item[1])

        reranked: list[SearchHit] = []
        for hit, similarity in scored:
            updated = hit.model_copy(deep=True)
            updated.score = similarity
            updated.match_type = "semantic"
            reranked.append(updated)
        return reranked[: limit * 3], []

    def _blend(
        self, keyword_hits: list[SearchHit], semantic_hits: list[SearchHit], limit: int
    ) -> list[SearchHit]:
        keyword_max = max((h.score for h in keyword_hits), default=1.0) or 1.0
        combined: dict[tuple, SearchHit] = {}
        position_bonus: dict[tuple, float] = {}

        for rank, hit in enumerate(keyword_hits):
            key = (hit.file_path, hit.start_line, hit.end_line)
            normalized = hit.score / keyword_max
            combined[key] = hit.model_copy(deep=True)
            combined[key].score = 0.55 * normalized
            position_bonus[key] = 0.55 * normalized

        for rank, hit in enumerate(semantic_hits):
            key = (hit.file_path, hit.start_line, hit.end_line)
            semantic_score = 0.45 * max(0.0, hit.score)
            if key in combined:
                combined[key].score += semantic_score
                combined[key].match_type = "hybrid"
            else:
                new_hit = hit.model_copy(deep=True)
                new_hit.score = semantic_score
                new_hit.match_type = "hybrid"
                combined[key] = new_hit

        merged = sorted(combined.values(), key=lambda h: -h.score)
        return merged[: max(limit * 3, limit)]

    @staticmethod
    def _dedupe(hits: list[SearchHit], limit: int) -> list[SearchHit]:
        selected: list[SearchHit] = []
        per_file: dict[str, int] = {}
        for hit in hits:
            count = per_file.get(hit.file_path, 0)
            if count >= 3:
                continue
            per_file[hit.file_path] = count + 1
            selected.append(hit)
            if len(selected) >= limit:
                break
        return selected


def _head(chunk: Chunk, lines: int = 8) -> str:
    content_lines = chunk.content.splitlines()[:lines]
    return "\n".join(content_lines)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
