"""Hybrid retrieval service — orchestrates vector + lexical + fusion + reranking.

This is the main entry point for retrieval in the platform.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from retrieval.vector_store import VectorStore
from retrieval.lexical_store import LexicalStore
from retrieval.fusion import reciprocal_rank_fusion
from retrieval.reranker import rerank
from retrieval.packer import pack_context
from token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class RetrievalService:
    """Hybrid retrieval: dense + lexical + RRF fusion + reranking + packing."""

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        lexical_store: LexicalStore | None = None,
    ):
        self.vector_store = vector_store or VectorStore()
        self.lexical_store = lexical_store or LexicalStore()
        self._loaded = False

    def ensure_loaded(self) -> None:
        """Load indexes if not already loaded. Silently skip if files don't exist."""
        if self._loaded:
            return
        try:
            if not self.vector_store.is_loaded:
                self.vector_store.load()
        except FileNotFoundError:
            logger.warning("Vector index not found — vector search disabled")
        try:
            if not self.lexical_store.is_loaded:
                self.lexical_store.load()
        except FileNotFoundError:
            logger.warning("Lexical index not found — BM25 search disabled")
        self._loaded = True

    def retrieve(
        self,
        query: str,
        *,
        top_n_raw: int = 50,
        rerank_top_k: int = 10,
        max_packed: int = 8,
        tenant_id: str | None = None,
        tracker: TokenTracker | None = None,
    ) -> dict[str, Any]:
        """Full hybrid retrieval pipeline.

        Returns:
            Dict with 'candidates', 'reranked', 'packed', and timing metadata.
        """
        self.ensure_loaded()
        t0 = time.time()

        # 1. Dense vector retrieval
        vector_results = []
        if self.vector_store.is_loaded:
            vector_results = self.vector_store.search(query, top_k=top_n_raw, tenant_id=tenant_id)
        t_vector = time.time() - t0

        # 2. Lexical BM25 retrieval
        t1 = time.time()
        lexical_results = []
        if self.lexical_store.is_loaded:
            lexical_results = self.lexical_store.search(query, top_k=top_n_raw, tenant_id=tenant_id)
        t_lexical = time.time() - t1

        # 3. Reciprocal Rank Fusion
        t2 = time.time()
        if vector_results and lexical_results:
            fused = reciprocal_rank_fusion(vector_results, lexical_results)
        elif vector_results:
            fused = vector_results
        else:
            fused = lexical_results
        t_fusion = time.time() - t2

        # 4. Cross-encoder reranking
        t3 = time.time()
        reranked = rerank(query, fused, top_k=rerank_top_k) if fused else []
        t_rerank = time.time() - t3

        # 5. Context packing
        t4 = time.time()
        packed = pack_context(reranked, max_chunks=max_packed)
        t_pack = time.time() - t4

        total_time = time.time() - t0

        if tracker:
            tracker.track_tool("retrieval", total_time)

        # Compute tokens saved estimate
        total_raw_tokens = sum(len(d.get("text", "")) // 4 for d in fused)
        packed_tokens = sum(len(d.get("text", "")) // 4 for d in packed)
        tokens_saved = max(0, total_raw_tokens - packed_tokens)

        return {
            "candidates": fused[:top_n_raw],
            "reranked": reranked,
            "packed": packed,
            "tokens_saved_by_reranking": tokens_saved,
            "timing": {
                "vector_s": round(t_vector, 3),
                "lexical_s": round(t_lexical, 3),
                "fusion_s": round(t_fusion, 3),
                "rerank_s": round(t_rerank, 3),
                "pack_s": round(t_pack, 3),
                "total_s": round(total_time, 3),
            },
            "counts": {
                "vector_hits": len(vector_results),
                "lexical_hits": len(lexical_results),
                "fused": len(fused),
                "reranked": len(reranked),
                "packed": len(packed),
            },
        }
