"""Dense vector store backed by FAISS.

Index type is chosen automatically based on corpus size:
- Small corpus (< hnsw_min_vectors): IndexFlatIP — exact cosine search via inner
  product after L2 normalisation.  FAISS already parallelises this across all CPU
  cores via OpenMP; no manual sharding needed.
- Large corpus (≥ hnsw_min_vectors): IndexHNSWFlat (M=32, ef=64).  Benchmarked at
  623 K vectors: 0.25 ms p50 vs 72 ms for FlatIP at 98% recall@20.  HNSW graph
  traversal is single-index and sub-ms at any practical scale, so IndexShards adds
  overhead without benefit and is intentionally not used.

Supports:
- Build from a list of document chunks
- Search by query embedding
- Tenant-scoped filtering via metadata
- Persistence (index.faiss + metadata.json)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from config import get_settings
from retrieval.embeddings import embed_texts

logger = logging.getLogger(__name__)


class VectorStore:
    """FAISS vector store with automatic flat / sharded-HNSW selection."""

    def __init__(self, index_dir: str | None = None):
        self.index_dir = Path(index_dir or get_settings().vector_index_dir)
        self._index = None
        self._metadata: list[dict[str, Any]] = []

    # ── helpers ──────────────────────────────────────────────────────────────

    def _n_threads(self) -> int:
        n = get_settings().faiss_num_threads
        return n if n > 0 else (os.cpu_count() or 4)

    def _build_index(self, vectors: np.ndarray, dim: int):
        """Return a FAISS index populated with *vectors*.

        Chooses between IndexFlatIP (small) and IndexHNSWFlat (large).
        Vectors must already be L2-normalised before calling this method.
        """
        import faiss

        cfg = get_settings()
        n = vectors.shape[0]
        n_threads = self._n_threads()
        faiss.omp_set_num_threads(n_threads)

        if n < cfg.hnsw_min_vectors:
            logger.info(
                "Corpus size %d < hnsw_min_vectors %d → IndexFlatIP "
                "(exact search, OMP threads=%d)",
                n, cfg.hnsw_min_vectors, n_threads,
            )
            index = faiss.IndexFlatIP(dim)
            index.add(vectors)
            return index

        # ── Large corpus: single IndexHNSWFlat ───────────────────────────
        # Benchmarked: 290× faster than FlatIP at 623K vectors, 98% recall@20.
        # FlatIP already saturates all CPU threads via OpenMP, so IndexShards
        # would only add merge overhead — not used.
        logger.info(
            "Corpus size %d ≥ hnsw_min_vectors %d → IndexHNSWFlat "
            "(M=%d, ef_construction=%d, ef_search=%d, OMP threads=%d)",
            n, cfg.hnsw_min_vectors,
            cfg.hnsw_m, cfg.hnsw_ef_construction, cfg.hnsw_ef_search, n_threads,
        )
        index = faiss.IndexHNSWFlat(dim, cfg.hnsw_m, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = cfg.hnsw_ef_construction
        index.hnsw.efSearch = cfg.hnsw_ef_search
        index.add(vectors)
        return index

    def _configure_loaded_index(self) -> None:
        """After loading from disk, restore runtime settings (OMP threads, ef_search)."""
        import faiss

        cfg = get_settings()
        faiss.omp_set_num_threads(self._n_threads())

        # Restore ef_search so the loaded HNSW index honours the current config
        # value rather than whatever was baked in at build time.
        if hasattr(self._index, "hnsw"):
            self._index.hnsw.efSearch = cfg.hnsw_ef_search

    # ── public API ───────────────────────────────────────────────────────────

    def build(self, chunks: list[dict[str, Any]]) -> None:
        """Build index from chunks. Each chunk needs 'text' and optional metadata."""
        import faiss

        texts = [c["text"] for c in chunks]
        vectors = embed_texts(texts)
        dim = vectors.shape[1]
        # L2-normalize for cosine similarity via inner product
        faiss.normalize_L2(vectors)
        self._index = self._build_index(vectors, dim)
        self._metadata = [
            {k: v for k, v in c.items() if k != "text"} | {"text": c["text"]}
            for c in chunks
        ]
        logger.info("Built vector index: %d vectors, dim=%d", len(chunks), dim)

    def save(self) -> None:
        """Persist index and metadata to disk."""
        import faiss

        self.index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.index_dir / "index.faiss"))
        with open(self.index_dir / "metadata.json", "w") as f:
            json.dump(self._metadata, f)
        logger.info("Saved vector index to %s", self.index_dir)

    def load(self) -> None:
        """Load index and metadata from disk."""
        import faiss

        idx_path = self.index_dir / "index.faiss"
        meta_path = self.index_dir / "metadata.json"
        if not idx_path.exists():
            raise FileNotFoundError(f"No index at {idx_path}")
        self._index = faiss.read_index(str(idx_path))
        with open(meta_path) as f:
            self._metadata = json.load(f)
        self._configure_loaded_index()
        logger.info("Loaded vector index: %d vectors", self._index.ntotal)

    def search(
        self,
        query: str,
        top_k: int = 20,
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for top_k most similar chunks."""
        import faiss

        if self._index is None:
            self.load()
        qvec = embed_texts([query])
        faiss.normalize_L2(qvec)
        distances, indices = self._index.search(qvec, min(top_k * 2, self._index.ntotal))

        results = []
        for score, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            meta = self._metadata[idx]
            if tenant_id and meta.get("tenant_id") and meta["tenant_id"] != tenant_id:
                continue
            results.append({**meta, "score": float(score), "_index": int(idx)})
            if len(results) >= top_k:
                break
        return results

    @property
    def is_loaded(self) -> bool:
        return self._index is not None

    @property
    def size(self) -> int:
        return self._index.ntotal if self._index else 0
