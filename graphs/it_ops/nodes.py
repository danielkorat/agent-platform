"""IT Ops scenario — graph nodes.

Pipeline: extract_entities → expand_context → retrieve_runbooks →
          root_cause_analysis → generate_actions → approval_gate →
          execute_if_approved → generate_closure_note
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from config import get_settings
from graphs.shared.state import AgentState
from graphs.it_ops.prompts import (
    EXTRACT_ENTITIES_SYSTEM, EXTRACT_ENTITIES_USER,
    ROOT_CAUSE_SYSTEM, ROOT_CAUSE_USER,
    REMEDIATION_SYSTEM, REMEDIATION_USER,
    CLOSURE_NOTE_SYSTEM, CLOSURE_NOTE_USER,
)
from llm.client import get_llm
from retrieval.packer import format_context_for_llm
from security.approvals import get_approval_gate

logger = logging.getLogger(__name__)


async def extract_ticket_entities(state: AgentState) -> dict[str, Any]:
    """Extract structured entities from the incident query."""
    t0 = time.time()
    query = state.get("clarified_query", "")
    tracker = state.get("metrics", {}).get("_tracker")

    llm = get_llm(caller="extract_entities", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": EXTRACT_ENTITIES_SYSTEM},
            {"role": "user", "content": EXTRACT_ENTITIES_USER.format(query=query)},
        ],
        caller="extract_ticket_entities",
        temperature=0.0,
        max_tokens=512,
    )

    # Parse JSON response (best-effort)
    try:
        entities = json.loads(response)
    except json.JSONDecodeError:
        entities = {"raw_extraction": response}

    return {
        "ticket_entities": entities,
        "node_trace": state.get("node_trace", []) + [
            {"node": "extract_ticket_entities", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def root_cause_analysis(state: AgentState) -> dict[str, Any]:
    """Generate root cause hypotheses based on context and entities."""
    t0 = time.time()
    query = state.get("clarified_query", "")
    entities = state.get("ticket_entities", {})
    packed = state.get("packed_context", [])
    context = format_context_for_llm(packed)
    tracker = state.get("metrics", {}).get("_tracker")

    llm = get_llm(caller="root_cause_analysis", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": ROOT_CAUSE_SYSTEM},
            {"role": "user", "content": ROOT_CAUSE_USER.format(
                query=query,
                entities=json.dumps(entities, indent=2),
                context=context,
            )},
        ],
        caller="root_cause_analysis",
        temperature=0.1,
        max_tokens=1024,
    )

    # Split into summary and hypotheses
    lines = response.strip().split("\n")
    summary = lines[0] if lines else response
    hypotheses = [l.strip() for l in lines[1:] if l.strip()]

    return {
        "root_cause_hypotheses": hypotheses or [response],
        "draft_output": response,
        "node_trace": state.get("node_trace", []) + [
            {"node": "root_cause_analysis", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def generate_recommended_actions(state: AgentState) -> dict[str, Any]:
    """Generate remediation action recommendations."""
    t0 = time.time()
    hypotheses = state.get("root_cause_hypotheses", [])
    packed = state.get("packed_context", [])
    context = format_context_for_llm(packed)
    summary = state.get("draft_output", "")
    tracker = state.get("metrics", {}).get("_tracker")

    llm = get_llm(caller="generate_actions", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": REMEDIATION_SYSTEM},
            {"role": "user", "content": REMEDIATION_USER.format(
                summary=summary,
                hypotheses="\n".join(f"- {h}" for h in hypotheses),
                context=context,
            )},
        ],
        caller="generate_recommended_actions",
        temperature=0.1,
        max_tokens=1024,
    )

    # Check if any actions are high-risk and need approval
    risk_class = state.get("risk_class", "low")
    needs_approval = risk_class in ("high", "critical")

    actions = [{"description": response, "risk": risk_class}]

    return {
        "recommended_actions": actions,
        "draft_output": response,
        "approval_required": needs_approval,
        "node_trace": state.get("node_trace", []) + [
            {"node": "generate_recommended_actions", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def human_approval_gate(state: AgentState) -> dict[str, Any]:
    """Gate execution on human approval for high-risk actions."""
    t0 = time.time()
    if not state.get("approval_required", False):
        return {
            "approval_status": "not_required",
            "node_trace": state.get("node_trace", []) + [
                {"node": "human_approval_gate", "wall_s": round(time.time() - t0, 3)}
            ],
        }

    gate = get_approval_gate()
    task_id = state.get("request_id", "unknown")
    gate.create_request(
        task_id=task_id,
        action=state.get("draft_output", "")[:200],
        risk_level=state.get("risk_class", "medium"),
        evidence=[c.get("chunk_id", "") for c in state.get("packed_context", [])],
    )

    # For demo: auto-approve after creating the request
    # In production, this would wait_for_decision()
    decision = gate.submit_decision(task_id, approved=True, reviewer_id="auto")

    return {
        "approval_status": decision["status"],
        "node_trace": state.get("node_trace", []) + [
            {"node": "human_approval_gate", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def generate_closure_note(state: AgentState) -> dict[str, Any]:
    """Generate an incident closure note."""
    t0 = time.time()
    query = state.get("clarified_query", "")
    hypotheses = state.get("root_cause_hypotheses", [])
    actions = state.get("recommended_actions", [])
    summary = state.get("draft_output", "")
    tracker = state.get("metrics", {}).get("_tracker")

    llm = get_llm(caller="generate_closure", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": CLOSURE_NOTE_SYSTEM},
            {"role": "user", "content": CLOSURE_NOTE_USER.format(
                query=query,
                summary=summary,
                root_cause="\n".join(hypotheses[:3]),
                actions=json.dumps(actions, indent=2, default=str),
            )},
        ],
        caller="generate_closure_note",
        temperature=0.2,
        max_tokens=512,
    )

    return {
        "closure_note": response,
        "draft_output": response,
        "node_trace": state.get("node_trace", []) + [
            {"node": "generate_closure_note", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def it_ops_fast_path(state: AgentState) -> dict[str, Any]:
    """Fast path: single-pass synthesis for simple IT queries."""
    t0 = time.time()
    query = state.get("clarified_query", "")
    packed = state.get("packed_context", [])
    context = format_context_for_llm(packed)
    tracker = state.get("metrics", {}).get("_tracker")

    from graphs.shared.prompts import FAST_SYNTHESIS_SYSTEM, FAST_SYNTHESIS_USER

    llm = get_llm(caller="it_ops_fast", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": FAST_SYNTHESIS_SYSTEM},
            {"role": "user", "content": FAST_SYNTHESIS_USER.format(
                context=context, query=query,
            )},
        ],
        caller="it_ops_fast_path",
        max_tokens=1024,
    )

    return {
        "draft_output": response,
        "node_trace": state.get("node_trace", []) + [
            {"node": "it_ops_fast_path", "wall_s": round(time.time() - t0, 3)}
        ],
    }
