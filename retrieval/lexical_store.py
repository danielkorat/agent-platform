"""BM25-based lexical retrieval store.

Uses rank_bm25 for keyword-based search. Complements vector search
in hybrid retrieval.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer."""
    return re.findall(r"\w+", text.lower())


class LexicalStore:
    """BM25-based lexical retrieval."""

    def __init__(self, index_dir: str | None = None):
        self.index_dir = Path(index_dir or get_settings().lexical_index_dir)
        self._bm25 = None
        self._docs: list[dict[str, Any]] = []

    def build(self, chunks: list[dict[str, Any]]) -> None:
        """Build BM25 index from chunks."""
        from rank_bm25 import BM25Okapi

        self._docs = chunks
        corpus = [_tokenize(c["text"]) for c in chunks]
        self._bm25 = BM25Okapi(corpus)
        logger.info("Built BM25 index: %d documents", len(chunks))

    def save(self) -> None:
        """Save documents to disk (BM25 is rebuilt on load)."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_dir / "documents.json", "w") as f:
            json.dump(self._docs, f)

    def load(self) -> None:
        """Load and rebuild BM25 index from disk."""
        doc_path = self.index_dir / "documents.json"
        if not doc_path.exists():
            raise FileNotFoundError(f"No lexical index at {doc_path}")
        with open(doc_path) as f:
            self._docs = json.load(f)
        self.build(self._docs)

    def search(
        self,
        query: str,
        top_k: int = 20,
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for top_k most relevant chunks via BM25."""
        if self._bm25 is None:
            self.load()
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)

        scored = list(enumerate(scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scored:
            if score <= 0:
                break
            doc = self._docs[idx]
            if tenant_id and doc.get("tenant_id") and doc["tenant_id"] != tenant_id:
                continue
            results.append({**doc, "bm25_score": float(score), "_index": idx})
            if len(results) >= top_k:
                break
        return results

    @property
    def is_loaded(self) -> bool:
        return self._bm25 is not None
