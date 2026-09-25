from __future__ import annotations

import math
from typing import Protocol, Sequence

from backend.utils.logging import get_logger

logger = get_logger(__name__)


class EmbeddingsUnavailable(Exception):
    """Raised when no embeddings provider is configured/usable."""


class EmbeddingsProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:  # pragma: no cover
        ...


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


async def embed_texts(
    provider: EmbeddingsProvider | None,
    texts: Sequence[str],
    *,
    batch_size: int = 32,
) -> list[list[float]] | None:
    """Embed texts, returning None when embeddings are unavailable."""
    if provider is None or not texts:
        return None
    vectors: list[list[float]] = []
    try:
        for index in range(0, len(texts), batch_size):
            batch = list(texts[index : index + batch_size])
            embedded = await provider.embed(batch)
            if not embedded or len(embedded) != len(batch):
                return None
            vectors.extend(embedded)
    except EmbeddingsUnavailable:
        return None
    except Exception as exc:
        logger.warning("Embeddings unavailable, falling back to lexical search: %s", exc)
        return None
    return vectors
