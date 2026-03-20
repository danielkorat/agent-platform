"""Dense vector store backed by FAISS IndexFlatIP.

Supports:
- Build from a list of document chunks
- Search by query embedding
- Tenant-scoped filtering via metadata
- Persistence (index.faiss + metadata.json)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from config import get_settings
from retrieval.embeddings import embed_texts

logger = logging.getLogger(__name__)


class VectorStore:
    """FAISS flat inner-product vector store."""

    def __init__(self, index_dir: str | None = None):
        self.index_dir = Path(index_dir or get_settings().vector_index_dir)
        self._index = None
        self._metadata: list[dict[str, Any]] = []

    def build(self, chunks: list[dict[str, Any]]) -> None:
        """Build index from chunks. Each chunk needs 'text' and optional metadata."""
        import faiss

        texts = [c["text"] for c in chunks]
        vectors = embed_texts(texts)
        dim = vectors.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        # L2-normalize for cosine similarity via inner product
        faiss.normalize_L2(vectors)
        self._index.add(vectors)
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
