"""IT Ops scenario — LangGraph graph builder.

Execution paths:
- Fast: ingest → auth → classify → retrieve → pack → fast_synthesis → policy → format → audit
- Medium: ingest → auth → classify → retrieve → pack → extract_entities → root_cause →
          actions → approval → closure → policy → format → audit
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from graphs.shared.state import AgentState
from graphs.shared.nodes import (
    ingest_request,
    authenticate_and_authorize,
    classify_scenario_and_complexity,
    build_retrieval_plan,
    retrieve_candidates,
    route_execution_path,
    policy_check_output,
    format_response,
    persist_audit_record,
)
from graphs.it_ops.nodes import (
    extract_ticket_entities,
    root_cause_analysis,
    generate_recommended_actions,
    human_approval_gate,
    generate_closure_note,
    it_ops_fast_path,
)


def _it_ops_router(state: AgentState) -> str:
    """Route to fast or medium path based on complexity."""
    path = state.get("execution_path", "it_ops_fast")
    if path == "it_ops_fast":
        return "fast"
    return "medium"


def build_it_ops_graph() -> StateGraph:
    """Build the IT Ops scenario LangGraph pipeline."""
    graph = StateGraph(AgentState)

    # ── Shared prefix ────────────────────────────────────────
    graph.add_node("ingest", ingest_request)
    graph.add_node("auth", authenticate_and_authorize)
    graph.add_node("classify", classify_scenario_and_complexity)
    graph.add_node("retrieval_plan", build_retrieval_plan)
    graph.add_node("retrieve", retrieve_candidates)
    graph.add_node("route", route_execution_path)

    # ── Fast path ────────────────────────────────────────────
    graph.add_node("fast_synthesis", it_ops_fast_path)

    # ── Medium path (single-agent bounded) ───────────────────
    graph.add_node("extract_entities", extract_ticket_entities)
    graph.add_node("root_cause", root_cause_analysis)
    graph.add_node("actions", generate_recommended_actions)
    graph.add_node("approval", human_approval_gate)
    graph.add_node("closure", generate_closure_note)

    # ── Shared suffix ────────────────────────────────────────
    graph.add_node("policy_check", policy_check_output)
    graph.add_node("format", format_response)
    graph.add_node("audit", persist_audit_record)

    # ── Edges ────────────────────────────────────────────────
    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "auth")
    graph.add_edge("auth", "classify")
    graph.add_edge("classify", "retrieval_plan")
    graph.add_edge("retrieval_plan", "retrieve")
    graph.add_edge("retrieve", "route")

    # Conditional routing
    graph.add_conditional_edges("route", _it_ops_router, {
        "fast": "fast_synthesis",
        "medium": "extract_entities",
    })

    # Fast path → suffix
    graph.add_edge("fast_synthesis", "policy_check")

    # Medium path
    graph.add_edge("extract_entities", "root_cause")
    graph.add_edge("root_cause", "actions")
    graph.add_edge("actions", "approval")
    graph.add_edge("approval", "closure")
    graph.add_edge("closure", "policy_check")

    # Shared suffix
    graph.add_edge("policy_check", "format")
    graph.add_edge("format", "audit")
    graph.add_edge("audit", END)

    return graph


def get_it_ops_graph():
    """Compile and return the IT Ops graph."""
    return build_it_ops_graph().compile()
