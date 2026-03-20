"""Reciprocal Rank Fusion for merging dense + lexical results."""

from __future__ import annotations

from typing import Any


def reciprocal_rank_fusion(
    *result_lists: list[dict[str, Any]],
    k: int = 60,
    id_field: str = "chunk_id",
) -> list[dict[str, Any]]:
    """Merge multiple ranked result lists using RRF.

    RRF score for document d = sum(1 / (k + rank_i(d))) across all lists.
    Higher is better.

    Args:
        result_lists: Multiple ranked result lists to fuse.
        k: RRF constant (default 60, standard value).
        id_field: Field to use for deduplication.

    Returns:
        Merged results sorted by RRF score, deduplicated.
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, dict[str, Any]] = {}

    for results in result_lists:
        for rank, doc in enumerate(results, 1):
            doc_id = doc.get(id_field) or doc.get("text", "")[:100]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in doc_map:
                doc_map[doc_id] = doc

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{**doc_map[doc_id], "rrf_score": score} for doc_id, score in ranked]
