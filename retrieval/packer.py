"""Context packing — select, deduplicate, and format chunks for LLM consumption.

Packing strategy:
1. Prioritize high-score, high-trust chunks
2. Collapse near-duplicates (>90% text overlap)
3. Enforce source diversity (max N chunks per source)
4. Truncate to max context token budget
5. Format with source provenance for citation
"""

from __future__ import annotations

from typing import Any

from config import get_settings


def _text_overlap(a: str, b: str) -> float:
    """Approximate text overlap ratio using set intersection of words."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))


def pack_context(
    chunks: list[dict[str, Any]],
    *,
    max_chunks: int = 10,
    max_tokens: int | None = None,
    max_per_source: int = 3,
    dedup_threshold: float = 0.90,
) -> list[dict[str, Any]]:
    """Select and deduplicate chunks for LLM context.

    Returns packed chunks with provenance metadata.
    """
    max_tokens = max_tokens or get_settings().max_context_tokens

    packed: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    token_budget = max_tokens

    for chunk in chunks:
        text = chunk.get("text", "")
        source = chunk.get("source", chunk.get("doc_id", "unknown"))

        # Source diversity cap
        if source_counts.get(source, 0) >= max_per_source:
            continue

        # Near-duplicate check
        is_dup = any(_text_overlap(text, p["text"]) > dedup_threshold for p in packed)
        if is_dup:
            continue

        # Token budget check (approximate: 1 token ≈ 4 chars)
        chunk_tokens = len(text) // 4
        if chunk_tokens > token_budget:
            continue

        packed.append({
            "chunk_id": chunk.get("chunk_id", f"c{len(packed)}"),
            "text": text,
            "source": source,
            "title": chunk.get("title", ""),
            "score": chunk.get("rerank_score", chunk.get("rrf_score", chunk.get("score", 0.0))),
            "metadata": {k: v for k, v in chunk.items()
                         if k not in ("text", "chunk_id", "source", "title", "score",
                                      "rerank_score", "rrf_score", "bm25_score", "_index")},
        })
        source_counts[source] = source_counts.get(source, 0) + 1
        token_budget -= chunk_tokens

        if len(packed) >= max_chunks:
            break

    return packed


def format_context_for_llm(packed: list[dict[str, Any]]) -> str:
    """Format packed chunks into a numbered context string for LLM prompts."""
    parts = []
    for i, chunk in enumerate(packed, 1):
        source = chunk.get("source", "unknown")
        title = chunk.get("title", "")
        header = f"[Source {i}] {title} ({source})" if title else f"[Source {i}] ({source})"
        parts.append(f"{header}\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)
