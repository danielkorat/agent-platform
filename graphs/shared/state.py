"""Shared LangGraph state schema for the Agent Platform.

All graph nodes read/write fields from this single TypedDict.
Scenario-specific fields are optional (total=False).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """Strongly typed shared state used across all graph nodes."""

    # ── Request identity ─────────────────────────────────────
    request_id: str
    tenant_id: str
    user_id: str
    scenario: Literal["it_ops", "deep_research"]
    user_query: str
    clarified_query: str

    # ── Auth / policy ────────────────────────────────────────
    auth_context: dict[str, Any]

    # ── Classification ───────────────────────────────────────
    risk_class: Literal["low", "medium", "high", "critical"]
    complexity_class: Literal["fast", "medium", "deep"]
    execution_path: str

    # ── Retrieval ────────────────────────────────────────────
    retrieval_plan: dict[str, Any]
    candidate_docs: list[dict[str, Any]]
    reranked_docs: list[dict[str, Any]]
    packed_context: list[dict[str, Any]]

    # ── Research (deep research scenario) ────────────────────
    research_brief: str
    sub_tasks: list[dict[str, Any]]
    sub_findings: list[dict[str, Any]]
    supervisor_notes: list[str]
    supervisor_round: int

    # ── IT Ops (it_ops scenario) ─────────────────────────────
    ticket_entities: dict[str, Any]
    incident_context: list[dict[str, Any]]
    runbooks: list[dict[str, Any]]
    root_cause_hypotheses: list[str]
    recommended_actions: list[dict[str, Any]]
    closure_note: str

    # ── Tool execution ───────────────────────────────────────
    tool_calls: list[dict[str, Any]]
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Output ───────────────────────────────────────────────
    citations: list[dict[str, Any]]
    draft_output: str
    final_output: str

    # ── Approval ─────────────────────────────────────────────
    approval_required: bool
    approval_status: Literal["pending", "approved", "rejected", "timeout", "not_required"]

    # ── Observability ────────────────────────────────────────
    metrics: dict[str, Any]
    errors: list[str]
    node_trace: list[dict[str, Any]]
