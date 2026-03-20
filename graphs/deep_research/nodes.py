"""Deep Research scenario — graph nodes.

Paths:
- Fast: single-pass synthesis
- Medium: brief → retrieve → synthesize
- Deep (supervisor): brief → decompose → spawn sub-agents → reflect → synthesize
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from config import get_settings
from graphs.shared.state import AgentState
from graphs.deep_research.prompts import (
    RESEARCH_BRIEF_SYSTEM, RESEARCH_BRIEF_USER,
    SUPERVISOR_DECOMPOSE_SYSTEM, SUPERVISOR_DECOMPOSE_USER,
    SUBAGENT_RESEARCH_SYSTEM, SUBAGENT_RESEARCH_USER,
    SUPERVISOR_REFLECT_SYSTEM, SUPERVISOR_REFLECT_USER,
    FINAL_REPORT_SYSTEM, FINAL_REPORT_USER,
    RESEARCH_FAST_SYSTEM, RESEARCH_FAST_USER,
)
from llm.client import get_llm
from retrieval.packer import format_context_for_llm
from retrieval.service import RetrievalService

logger = logging.getLogger(__name__)


async def research_fast_path(state: AgentState) -> dict[str, Any]:
    """Fast path: single-pass research synthesis."""
    t0 = time.time()
    query = state.get("clarified_query", "")
    packed = state.get("packed_context", [])
    context = format_context_for_llm(packed)
    tracker = state.get("metrics", {}).get("_tracker")

    llm = get_llm(caller="research_fast", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": RESEARCH_FAST_SYSTEM},
            {"role": "user", "content": RESEARCH_FAST_USER.format(
                context=context, query=query,
            )},
        ],
        caller="research_fast_path",
        max_tokens=2048,
    )

    return {
        "draft_output": response,
        "node_trace": state.get("node_trace", []) + [
            {"node": "research_fast_path", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def write_research_brief(state: AgentState) -> dict[str, Any]:
    """Generate a scoped research brief."""
    t0 = time.time()
    query = state.get("clarified_query", "")
    packed = state.get("packed_context", [])
    context = format_context_for_llm(packed)
    tracker = state.get("metrics", {}).get("_tracker")

    llm = get_llm(caller="write_brief", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": RESEARCH_BRIEF_SYSTEM},
            {"role": "user", "content": RESEARCH_BRIEF_USER.format(
                query=query, context=context,
            )},
        ],
        caller="write_research_brief",
        max_tokens=1024,
    )

    return {
        "research_brief": response,
        "node_trace": state.get("node_trace", []) + [
            {"node": "write_research_brief", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def supervisor_plan_subtopics(state: AgentState) -> dict[str, Any]:
    """Supervisor decomposes research into independent subtasks."""
    t0 = time.time()
    brief = state.get("research_brief", "")
    tracker = state.get("metrics", {}).get("_tracker")
    s = get_settings()

    llm = get_llm(caller="supervisor_plan", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": SUPERVISOR_DECOMPOSE_SYSTEM},
            {"role": "user", "content": SUPERVISOR_DECOMPOSE_USER.format(
                brief=brief,
                questions="(see brief above)",
                max_subtasks=s.max_sub_agents,
            )},
        ],
        caller="supervisor_plan_subtopics",
        temperature=0.1,
        max_tokens=1024,
    )

    # Parse subtasks from response
    try:
        # Look for JSON array in response
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            sub_tasks = json.loads(response[start:end])
        else:
            sub_tasks = [{"topic": brief, "queries": [state.get("clarified_query", "")],
                          "instructions": "Investigate the full topic."}]
    except json.JSONDecodeError:
        sub_tasks = [{"topic": brief[:200], "queries": [state.get("clarified_query", "")],
                      "instructions": "Investigate the full topic."}]

    # Cap at max sub-agents
    sub_tasks = sub_tasks[:s.max_sub_agents]

    # Add IDs
    for i, st in enumerate(sub_tasks):
        st["id"] = f"sub_{i+1}"

    return {
        "sub_tasks": sub_tasks,
        "supervisor_round": state.get("supervisor_round", 0) + 1,
        "node_trace": state.get("node_trace", []) + [
            {"node": "supervisor_plan_subtopics", "wall_s": round(time.time() - t0, 3)}
        ],
    }


async def execute_sub_agents(state: AgentState) -> dict[str, Any]:
    """Execute research sub-agents sequentially (with isolated contexts).

    Each sub-agent:
    1. Retrieves context for its subtopic queries
    2. Synthesizes findings from that context
    3. Returns cleaned findings (not raw data)
    """
    t0 = time.time()
    sub_tasks = state.get("sub_tasks", [])
    tracker = state.get("metrics", {}).get("_tracker")

    from graphs.shared.nodes import get_retrieval_service

    svc = get_retrieval_service()
    findings = []

    for task in sub_tasks:
        st_t0 = time.time()
        topic = task.get("topic", "")
        queries = task.get("queries", [topic])
        instructions = task.get("instructions", "")

        # Retrieve context for this subtask
        all_chunks = []
        for q in queries[:3]:  # max 3 queries per subtask
            result = svc.retrieve(
                q,
                top_n_raw=30,
                rerank_top_k=5,
                max_packed=5,
                tenant_id=state.get("tenant_id"),
                tracker=tracker,
            )
            all_chunks.extend(result["packed"])

        # Deduplicate
        seen = set()
        unique_chunks = []
        for c in all_chunks:
            cid = c.get("chunk_id", c.get("text", "")[:50])
            if cid not in seen:
                seen.add(cid)
                unique_chunks.append(c)

        context = format_context_for_llm(unique_chunks[:8])

        # Sub-agent synthesis
        llm = get_llm(caller="subagent_research", tracker=tracker)
        response = await llm.chat(
            messages=[
                {"role": "system", "content": SUBAGENT_RESEARCH_SYSTEM},
                {"role": "user", "content": SUBAGENT_RESEARCH_USER.format(
                    topic=topic,
                    instructions=instructions,
                    context=context,
                )},
            ],
            caller=f"subagent_{task.get('id', 'unknown')}",
            max_tokens=1500,
        )

        findings.append({
            "sub_task_id": task.get("id", ""),
            "topic": topic,
            "summary": response,
            "evidence_ids": [c.get("chunk_id", "") for c in unique_chunks[:8]],
            "elapsed_s": round(time.time() - st_t0, 3),
        })

    return {
        "sub_findings": state.get("sub_findings", []) + findings,
        "node_trace": state.get("node_trace", []) + [
            {"node": "execute_sub_agents", "wall_s": round(time.time() - t0, 3),
             "subtask_count": len(sub_tasks)}
        ],
    }


async def supervisor_reflect(state: AgentState) -> dict[str, Any]:
    """Supervisor evaluates coverage and decides whether to iterate."""
    t0 = time.time()
    brief = state.get("research_brief", "")
    findings = state.get("sub_findings", [])
    tracker = state.get("metrics", {}).get("_tracker")
    s = get_settings()

    findings_text = "\n\n".join(
        f"### {f.get('topic', 'Unknown')}\n{f.get('summary', '')}"
        for f in findings
    )

    llm = get_llm(caller="supervisor_reflect", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": SUPERVISOR_REFLECT_SYSTEM},
            {"role": "user", "content": SUPERVISOR_REFLECT_USER.format(
                brief=brief,
                questions="(see brief)",
                findings=findings_text,
            )},
        ],
        caller="supervisor_reflect",
        temperature=0.1,
        max_tokens=512,
    )

    # Parse reflection
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            reflection = json.loads(response[start:end])
        else:
            reflection = {"coverage_score": 0.8, "iterate": False, "gaps": []}
    except json.JSONDecodeError:
        reflection = {"coverage_score": 0.8, "iterate": False, "gaps": []}

    supervisor_notes = state.get("supervisor_notes", [])
    supervisor_notes.append(json.dumps(reflection))

    # Cap iterations
    current_round = state.get("supervisor_round", 1)
    should_iterate = reflection.get("iterate", False) and current_round < s.supervisor_max_rounds

    return {
        "supervisor_notes": supervisor_notes,
        "_should_iterate": should_iterate,
        "node_trace": state.get("node_trace", []) + [
            {"node": "supervisor_reflect", "wall_s": round(time.time() - t0, 3),
             "coverage": reflection.get("coverage_score", 0), "iterate": should_iterate}
        ],
    }


async def generate_final_report(state: AgentState) -> dict[str, Any]:
    """Synthesize all findings into a final decision memo."""
    t0 = time.time()
    brief = state.get("research_brief", "")
    findings = state.get("sub_findings", [])
    supervisor_notes = state.get("supervisor_notes", [])
    tracker = state.get("metrics", {}).get("_tracker")

    findings_text = "\n\n".join(
        f"### {f.get('topic', 'Unknown')}\n{f.get('summary', '')}"
        for f in findings
    )
    notes_text = "\n".join(supervisor_notes) if supervisor_notes else "No special notes."

    llm = get_llm(caller="generate_report", tracker=tracker)
    response = await llm.chat(
        messages=[
            {"role": "system", "content": FINAL_REPORT_SYSTEM},
            {"role": "user", "content": FINAL_REPORT_USER.format(
                brief=brief,
                findings=findings_text,
                supervisor_notes=notes_text,
            )},
        ],
        caller="generate_final_report",
        max_tokens=4096,
    )

    return {
        "draft_output": response,
        "node_trace": state.get("node_trace", []) + [
            {"node": "generate_final_report", "wall_s": round(time.time() - t0, 3)}
        ],
    }
