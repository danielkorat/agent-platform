"""Cross-encoder reranker for top-k refinement.

Uses cross-encoder/ms-marco-MiniLM-L-6-v2 (22M params, CPU-fast).
Runs on Xeon — no GPU needed.
"""

from __future__ import annotations

import logging
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        model_name = get_settings().rerank_model
        logger.info("Loading reranker model: %s", model_name)
        _reranker = CrossEncoder(model_name)
    return _reranker


def rerank(
    query: str,
    passages: list[dict[str, Any]],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Rerank passages by cross-encoder relevance score.

    Args:
        query: The user query.
        passages: List of candidate passages (must have 'text' field).
        top_k: Number of top results to return (default from config).

    Returns:
        Top-k passages sorted by reranker score, with 'rerank_score' added.
    """
    if not passages:
        return []

    top_k = top_k or get_settings().rerank_top_k
    model = _get_reranker()

    pairs = [(query, p["text"]) for p in passages]
    scores = model.predict(pairs)

    for p, score in zip(passages, scores):
        p["rerank_score"] = float(score)

    passages.sort(key=lambda x: x["rerank_score"], reverse=True)
    return passages[:top_k]
