"""Build demo indexes from mock KB data.

Run: python -m connectors.build_demo_index
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectors.kb import _MOCK_KB
from retrieval.vector_store import VectorStore
from retrieval.lexical_store import LexicalStore


def build_demo_indexes():
    """Build FAISS + BM25 indexes from mock KB articles."""
    chunks = []
    for i, article in enumerate(_MOCK_KB):
        chunks.append({
            "chunk_id": article["id"],
            "doc_id": article["id"],
            "text": article["text"],
            "title": article["title"],
            "source": article["source"],
            "tenant_id": article.get("tenant_id", "default"),
            "tags": article.get("tags", []),
        })

    print(f"Building indexes from {len(chunks)} KB articles...")

    # Vector index
    vs = VectorStore("data/index")
    vs.build(chunks)
    vs.save()
    print(f"  Vector index: {vs.size} vectors saved to data/index/")

    # Lexical index
    ls = LexicalStore("data/lexical")
    ls.build(chunks)
    ls.save()
    print(f"  Lexical index: {len(chunks)} documents saved to data/lexical/")

    print("Done!")


if __name__ == "__main__":
    build_demo_indexes()
