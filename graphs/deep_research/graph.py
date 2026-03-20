"""Deep Research scenario — LangGraph graph builder.

Execution paths:
- Fast: ingest → auth → classify → retrieve → fast_synthesis → policy → format → audit
- Medium: ingest → auth → classify → retrieve → brief → retrieve_deep → synthesis → policy → format → audit
- Deep (supervisor): ingest → auth → classify → retrieve → brief → decompose →
                     sub-agents → reflect → [iterate?] → final_report → policy → format → audit
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
from graphs.deep_research.nodes import (
    research_fast_path,
    write_research_brief,
    supervisor_plan_subtopics,
    execute_sub_agents,
    supervisor_reflect,
    generate_final_report,
)


def _research_router(state: AgentState) -> str:
    """Route to fast, medium, or deep research path."""
    path = state.get("execution_path", "research_fast")
    if path == "research_fast":
        return "fast"
    elif path == "research_single_agent":
        return "medium"
    return "deep"


def _reflection_router(state: AgentState) -> str:
    """Route after supervisor reflection: iterate or finalize."""
    if state.get("_should_iterate", False):
        return "iterate"
    return "finalize"


def build_deep_research_graph() -> StateGraph:
    """Build the Deep Research scenario LangGraph pipeline."""
    graph = StateGraph(AgentState)

    # ── Shared prefix ────────────────────────────────────────
    graph.add_node("ingest", ingest_request)
    graph.add_node("auth", authenticate_and_authorize)
    graph.add_node("classify", classify_scenario_and_complexity)
    graph.add_node("retrieval_plan", build_retrieval_plan)
    graph.add_node("retrieve", retrieve_candidates)
    graph.add_node("route", route_execution_path)

    # ── Fast path ────────────────────────────────────────────
    graph.add_node("fast_synthesis", research_fast_path)

    # ── Medium + Deep paths ──────────────────────────────────
    graph.add_node("brief", write_research_brief)

    # ── Deep path (supervisor) ───────────────────────────────
    graph.add_node("decompose", supervisor_plan_subtopics)
    graph.add_node("sub_agents", execute_sub_agents)
    graph.add_node("reflect", supervisor_reflect)
    graph.add_node("final_report", generate_final_report)

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

    # Three-way routing
    graph.add_conditional_edges("route", _research_router, {
        "fast": "fast_synthesis",
        "medium": "brief",
        "deep": "brief",
    })

    # Fast → suffix
    graph.add_edge("fast_synthesis", "policy_check")

    # Medium path: brief → final_report (skip supervisor)
    # Deep path: brief → decompose → sub-agents → reflect
    # Both go through brief, but routing after brief depends on path
    def _post_brief_router(state: AgentState) -> str:
        if state.get("execution_path") == "research_single_agent":
            return "direct_report"
        return "decompose"

    graph.add_conditional_edges("brief", _post_brief_router, {
        "direct_report": "final_report",
        "decompose": "decompose",
    })

    # Deep supervisor loop
    graph.add_edge("decompose", "sub_agents")
    graph.add_edge("sub_agents", "reflect")

    graph.add_conditional_edges("reflect", _reflection_router, {
        "iterate": "decompose",
        "finalize": "final_report",
    })

    graph.add_edge("final_report", "policy_check")

    # Shared suffix
    graph.add_edge("policy_check", "format")
    graph.add_edge("format", "audit")
    graph.add_edge("audit", END)

    return graph


def get_deep_research_graph():
    """Compile and return the Deep Research graph."""
    return build_deep_research_graph().compile()
