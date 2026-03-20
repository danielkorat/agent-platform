"""Shared graph nodes — reusable across both scenarios.

Node ordering:
1. ingest_request
2. authenticate_and_authorize
3. classify_scenario
4. classify_complexity
5. build_retrieval_plan
6. retrieve_candidates
7. rerank_candidates
8. pack_context
9. route_execution_path
10. policy_check_output
11. format_response
12. persist_audit_record
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from config import get_settings
from graphs.shared.state import AgentState
from graphs.shared.router import classify_query
from models import ProgressEvent, TaskStatus
from retrieval.packer import format_context_for_llm
from retrieval.service import RetrievalService
from security.auth import authenticate
from security.rbac import require_permission, require_tenant_access
from security.pii import redact_pii, contains_pii
from security.prompt_injection import sanitize_retrieved_content
from token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# Module-level retrieval service (lazy init)
_retrieval_service: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service


# ── Shared Nodes ─────────────────────────────────────────────

async def ingest_request(state: AgentState) -> dict[str, Any]:
    """Validate and normalize the incoming request."""
    t0 = time.time()
    query = state.get("user_query", "").strip()
    if not query:
        return {"errors": ["Empty query"]}

    # PII check on input (log warning, don't block)
    s = get_settings()
    pii_found = contains_pii(query) if s.pii_redaction_enabled else []
    if pii_found:
        logger.warning("PII detected in query: %s", pii_found)

    return {
        "clarified_query": query,
        "node_trace": state.get("node_trace", []) + [
            {"node": "ingest_request", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def authenticate_and_authorize(state: AgentState) -> dict[str, Any]:
    """Authenticate user and verify tenant access."""
    t0 = time.time()
    auth_ctx = state.get("auth_context", {})

    if not auth_ctx:
        # Default dev-mode auth
        auth_ctx = authenticate(None)

    require_permission(auth_ctx, "read")
    require_tenant_access(auth_ctx, state.get("tenant_id", "default"))

    return {
        "auth_context": auth_ctx,
        "node_trace": state.get("node_trace", []) + [
            {"node": "authenticate_and_authorize", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def classify_scenario_and_complexity(state: AgentState) -> dict[str, Any]:
    """Classify scenario, complexity, and risk level."""
    t0 = time.time()
    query = state.get("clarified_query", state.get("user_query", ""))

    # Allow scenario override from request
    scenario_hint = state.get("scenario")
    tracker = _get_tracker(state)

    result = await classify_query(query, scenario_override=scenario_hint, tracker=tracker)

    return {
        "scenario": result.scenario.value,
        "complexity_class": result.complexity.value,
        "risk_class": result.risk.value,
        "node_trace": state.get("node_trace", []) + [
            {"node": "classify", "wall_s": round(time.time() - t0, 3),
             "result": result.model_dump()}
        ],
    }


async def build_retrieval_plan(state: AgentState) -> dict[str, Any]:
    """Generate a retrieval strategy based on query and classification."""
    t0 = time.time()
    query = state.get("clarified_query", "")
    complexity = state.get("complexity_class", "fast")

    # Adjust retrieval depth based on complexity
    depth_config = {
        "fast": {"top_n_raw": 20, "rerank_top_k": 5, "max_packed": 5},
        "medium": {"top_n_raw": 40, "rerank_top_k": 10, "max_packed": 8},
        "deep": {"top_n_raw": 80, "rerank_top_k": 20, "max_packed": 12},
    }
    config = depth_config.get(complexity, depth_config["medium"])

    plan = {
        "queries": [query],
        "sources": ["vector", "lexical"],
        "filters": {"tenant_id": state.get("tenant_id", "default")},
        **config,
    }

    return {
        "retrieval_plan": plan,
        "node_trace": state.get("node_trace", []) + [
            {"node": "build_retrieval_plan", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def retrieve_candidates(state: AgentState) -> dict[str, Any]:
    """Execute retrieval plan — hybrid dense + lexical search."""
    t0 = time.time()
    plan = state.get("retrieval_plan", {})
    tracker = _get_tracker(state)

    svc = get_retrieval_service()
    query = plan.get("queries", [state.get("clarified_query", "")])[0]

    result = svc.retrieve(
        query,
        top_n_raw=plan.get("top_n_raw", 50),
        rerank_top_k=plan.get("rerank_top_k", 10),
        max_packed=plan.get("max_packed", 8),
        tenant_id=plan.get("filters", {}).get("tenant_id"),
        tracker=tracker,
    )

    # Sanitize for prompt injection
    sanitized = sanitize_retrieved_content(result["packed"])

    return {
        "candidate_docs": result["candidates"],
        "reranked_docs": result["reranked"],
        "packed_context": sanitized,
        "metrics": {
            **(state.get("metrics", {})),
            "retrieval": result["timing"],
            "retrieval_counts": result["counts"],
            "tokens_saved_by_reranking": result["tokens_saved_by_reranking"],
        },
        "node_trace": state.get("node_trace", []) + [
            {"node": "retrieve_candidates", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def route_execution_path(state: AgentState) -> dict[str, Any]:
    """Determine which execution path to take based on classification."""
    complexity = state.get("complexity_class", "fast")
    scenario = state.get("scenario", "it_ops")

    path_map = {
        ("it_ops", "fast"): "it_ops_fast",
        ("it_ops", "medium"): "it_ops_single_agent",
        ("it_ops", "deep"): "it_ops_single_agent",  # cap IT ops at single-agent
        ("deep_research", "fast"): "research_fast",
        ("deep_research", "medium"): "research_single_agent",
        ("deep_research", "deep"): "research_supervisor",
    }
    path = path_map.get((scenario, complexity), f"{scenario}_fast")

    return {"execution_path": path}


async def policy_check_output(state: AgentState) -> dict[str, Any]:
    """Safety check on generated output — PII redaction, content policy."""
    t0 = time.time()
    output = state.get("draft_output", "")
    s = get_settings()

    if s.pii_redaction_enabled:
        output = redact_pii(output)

    safety_flags = []
    if not output.strip():
        safety_flags.append("empty_output")

    return {
        "final_output": output,
        "metrics": {
            **(state.get("metrics", {})),
            "safety_flags": safety_flags,
        },
        "node_trace": state.get("node_trace", []) + [
            {"node": "policy_check_output", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def format_response(state: AgentState) -> dict[str, Any]:
    """Format the final response with citations and metadata."""
    t0 = time.time()
    citations = state.get("citations", [])

    # Build citation references from packed context
    if not citations and state.get("packed_context"):
        citations = [
            {
                "source_id": c.get("chunk_id", f"s{i}"),
                "source": c.get("source", ""),
                "title": c.get("title", ""),
                "score": c.get("score", 0.0),
            }
            for i, c in enumerate(state.get("packed_context", []), 1)
        ]

    return {
        "citations": citations,
        "node_trace": state.get("node_trace", []) + [
            {"node": "format_response", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def persist_audit_record(state: AgentState) -> dict[str, Any]:
    """Persist an immutable audit record for this task execution."""
    t0 = time.time()
    s = get_settings()

    if not s.audit_enabled:
        return {}

    output_hash = hashlib.sha256(
        state.get("final_output", "").encode()
    ).hexdigest()[:16]

    audit = {
        "task_id": state.get("request_id", ""),
        "tenant_id": state.get("tenant_id", "default"),
        "user_id": state.get("user_id", "anonymous"),
        "scenario": state.get("scenario", ""),
        "execution_path": state.get("execution_path", ""),
        "model_endpoints_used": list(
            state.get("metrics", {}).get("hw_summary", {}).keys()
        ),
        "retrieved_source_ids": [
            c.get("chunk_id", "") for c in state.get("packed_context", [])
        ],
        "approval_required": state.get("approval_required", False),
        "approval_status": state.get("approval_status", "not_required"),
        "output_hash": output_hash,
        "latency_breakdown": state.get("metrics", {}).get("retrieval", {}),
    }

    logger.info("Audit record: %s", json.dumps(audit, default=str))

    return {
        "node_trace": state.get("node_trace", []) + [
            {"node": "persist_audit_record", "wall_s": round(time.time() - t0, 3)}
        ],
    }


# ── Helpers ──────────────────────────────────────────────────

def _get_tracker(state: AgentState) -> TokenTracker | None:
    """Extract or create a token tracker from state metrics."""
    metrics = state.get("metrics", {})
    task_id = state.get("request_id", "unknown")
    if "_tracker" in metrics:
        return metrics["_tracker"]
    return None
