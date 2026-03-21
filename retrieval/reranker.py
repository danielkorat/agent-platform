"""Cross-encoder reranker for top-k refinement.

Uses cross-encoder/ms-marco-MiniLM-L-6-v2 (22M params, CPU-fast).
Supports torch (default) and ONNX Runtime backends.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from config import get_settings

logger = logging.getLogger(__name__)

_reranker = None          # torch CrossEncoder (lazy)
_onnx_session = None      # ONNX InferenceSession (lazy)
_onnx_tokenizer = None    # HF tokenizer for ONNX path (lazy)

ONNX_EXPORT_DIR = Path("data/onnx_reranker")


# ── Torch backend ────────────────────────────────────────────

def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        cfg = get_settings()
        logger.info("Loading reranker model (torch/%s): %s", cfg.rerank_device, cfg.rerank_model)
        _reranker = CrossEncoder(cfg.rerank_model, device=cfg.rerank_device)
    return _reranker


# ── ONNX backend ─────────────────────────────────────────────

def _export_onnx(model_name: str, export_path: Path) -> Path:
    """Export cross-encoder to ONNX format (one-time operation)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    logger.info("Exporting %s to ONNX → %s", model_name, export_path)
    export_path.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    # Force eager attention — SDPA doesn't trace cleanly to ONNX operators
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, attn_implementation="eager"
    )
    model.eval()

    dummy = tokenizer("query", "passage", return_tensors="pt", padding="max_length", max_length=128)
    onnx_file = export_path / "model.onnx"

    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy["input_ids"], dummy["attention_mask"], dummy["token_type_ids"]),
            str(onnx_file),
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq"},
                "attention_mask": {0: "batch", 1: "seq"},
                "token_type_ids": {0: "batch", 1: "seq"},
                "logits": {0: "batch"},
            },
            opset_version=14,
            dynamo=False,  # use legacy TorchScript exporter (no onnxscript dep)
        )

    tokenizer.save_pretrained(str(export_path))
    logger.info("ONNX export complete: %s (%.1f MB)", onnx_file, onnx_file.stat().st_size / 1e6)
    return onnx_file


def _get_onnx_session():
    """Lazy-load ONNX session, exporting model if needed."""
    global _onnx_session, _onnx_tokenizer
    if _onnx_session is not None:
        return _onnx_session, _onnx_tokenizer

    import onnxruntime as ort
    from transformers import AutoTokenizer

    cfg = get_settings()
    onnx_file = ONNX_EXPORT_DIR / "model.onnx"

    if not onnx_file.exists():
        _export_onnx(cfg.rerank_model, ONNX_EXPORT_DIR)

    # Use all CPU cores + full graph optimization
    opts = ort.SessionOptions()
    opts.inter_op_num_threads = os.cpu_count() or 4
    opts.intra_op_num_threads = os.cpu_count() or 4
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    # Select execution provider based on configured device
    device = cfg.rerank_device
    if device == "cuda":
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    elif device == "xpu":
        providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
    else:
        providers = ["CPUExecutionProvider"]

    logger.info("Loading ONNX reranker session from %s (providers=%s)", onnx_file, providers)
    _onnx_session = ort.InferenceSession(str(onnx_file), opts, providers=providers)
    _onnx_tokenizer = AutoTokenizer.from_pretrained(str(ONNX_EXPORT_DIR))
    return _onnx_session, _onnx_tokenizer


def _predict_onnx(pairs: list[tuple[str, str]]) -> np.ndarray:
    """Score (query, passage) pairs via ONNX Runtime."""
    session, tokenizer = _get_onnx_session()
    encoded = tokenizer(
        [p[0] for p in pairs],
        [p[1] for p in pairs],
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="np",
    )
    feeds = {
        "input_ids": encoded["input_ids"],
        "attention_mask": encoded["attention_mask"],
        "token_type_ids": encoded["token_type_ids"],
    }
    logits = session.run(["logits"], feeds)[0]
    return logits[:, 0] if logits.ndim == 2 else logits


def rerank(
    query: str,
    passages: list[dict[str, Any]],
    top_k: int | None = None,
    max_candidates: int | None = None,
) -> list[dict[str, Any]]:
    """Rerank passages by cross-encoder relevance score.

    Args:
        query: The user query.
        passages: List of candidate passages (must have 'text' field).
        top_k: Number of top results to return (default from config).
        max_candidates: Max passages to score (pre-truncate). Reduces latency
            linearly. Passages beyond this cutoff are assumed lower quality
            by the upstream RRF ranking and are dropped before scoring.

    Returns:
        Top-k passages sorted by reranker score, with 'rerank_score' added.
    """
    if not passages:
        return []

    cfg = get_settings()
    top_k = top_k or cfg.rerank_top_k
    max_candidates = max_candidates or cfg.rerank_max_candidates

    # Pre-truncate: only score the top candidates from upstream ranking
    scored_passages = passages[:max_candidates]
    pairs = [(query, p["text"]) for p in scored_passages]

    # Dispatch to backend
    if cfg.rerank_backend == "onnx":
        scores = _predict_onnx(pairs)
    else:
        model = _get_reranker()
        scores = model.predict(pairs)

    for p, score in zip(scored_passages, scores):
        p["rerank_score"] = float(score)

    scored_passages.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored_passages[:top_k]
