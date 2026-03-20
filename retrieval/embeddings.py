"""Embedding generation using sentence-transformers.

Lazy-loads the model on first call. Thread-safe via module-level singleton.
"""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np

from config import get_settings

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        model_name = get_settings().embedding_model
        logger.info("Loading embedding model: %s", model_name)
        _model = SentenceTransformer(model_name)
    return _model


def embed_texts(texts: Sequence[str], batch_size: int = 256) -> np.ndarray:
    """Embed a batch of texts, returning (N, dim) float32 array."""
    model = _get_model()
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=False,
        convert_to_numpy=True,
    )
    return vectors.astype(np.float32)
