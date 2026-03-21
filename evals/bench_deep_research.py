"""Deep Research scenario benchmarks — full end-to-end graph execution.

Runs the actual Deep Research LangGraph graph with live LLM inference.
Measures per-query: wall time, node trace, LLM calls/tokens, retrieval
timing, quality metrics (packed chunks, scores), and cost.

Requires: vLLM servers running on localhost:8000 (GPU) and :8001 (CPU).

Output: evals/results/deep_research_bench.json

Usage:
    python3 -m evals.bench_deep_research
    python3 -m evals.bench_deep_research --tiers fast,medium,deep
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


# ── Monthly cost for per-query cost calculation ─────────────────────────────
_MONTHLY_COST_USD = 512.0
_SECONDS_PER_MONTH = 30.44 * 24 * 3600


# ── Queries per tier ────────────────────────────────────────────────────────

QUERIES = {
    "fast": [
        "What is RAG?",
        "How does BM25 scoring work?",
        "What is cross-encoder reranking?",
    ],
    "medium": [
        "How does hybrid retrieval improve over dense-only retrieval in enterprise systems?",
        "Explain the tradeoffs between single-agent and supervisor/sub-agent orchestration patterns",
    ],
    "deep": [
        "Compare dense retrieval vs sparse retrieval vs hybrid retrieval for enterprise knowledge systems. Analyse precision, recall, latency, and infrastructure cost tradeoffs at 100K, 500K, and 1M document scale.",
        "Research the intersection of retrieval-augmented generation and agent orchestration. How should retrieval be integrated into multi-agent systems — per-agent retrieval, shared retrieval, or supervised retrieval allocation?",
    ],
}


# ── Complexity overrides (force the router to pick the right tier) ──────────
_TIER_TO_PATH = {
    "fast": "research_fast",
    "medium": "research_single_agent",
    "deep": "research_supervisor",
}


# ── Result types ────────────────────────────────────────────────────────────

@dataclass
class E2EResult:
    query: str
    tier: str
    wall_s: float = 0.0
    execution_path: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retrieval_nodes: int = 0
    retrieval_total_s: float = 0.0
    llm_total_s: float = 0.0
    node_count: int = 0
    node_trace: list = field(default_factory=list)
    n_packed: int = 0
    n_sub_findings: int = 0
    supervisor_rounds: int = 0
    output_length: int = 0
    cost_per_query_usd: float = 0.0
    error: str = ""


# ── Graph runner ────────────────────────────────────────────────────────────

async def run_graph_e2e(query: str, tier: str) -> E2EResult:
    """Run the full Deep Research graph for one query and collect metrics."""
    from graphs.deep_research.graph import get_deep_research_graph
    from graphs.shared.state import AgentState
    from token_tracker import TokenTracker

    tracker = TokenTracker(task_id=f"bench_{tier}_{int(time.time()*1000)}")
    result = E2EResult(query=query, tier=tier)

    initial_state: AgentState = {
        "request_id": f"bench_{tier}_{int(time.time()*1000)}",
        "tenant_id": "default",
        "user_id": "benchmark",
        "scenario": "deep_research",
        "user_query": query,
        "metrics": {"_tracker": tracker},
        "errors": [],
        "node_trace": [],
        # Force the execution path for this tier
        "complexity_class": tier,
        "execution_path": _TIER_TO_PATH[tier],
    }

    graph = get_deep_research_graph()

    t0 = time.perf_counter()
    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as e:
        result.wall_s = round(time.perf_counter() - t0, 3)
        result.error = str(e)
        return result

    result.wall_s = round(time.perf_counter() - t0, 3)
    result.execution_path = final_state.get("execution_path", "")
    result.node_trace = final_state.get("node_trace", [])
    result.node_count = len(result.node_trace)

    # Token tracker metrics
    result.llm_calls = tracker.total_calls
    result.input_tokens = tracker.total_input_tokens
    result.output_tokens = tracker.total_output_tokens

    # Parse node trace for retrieval vs LLM breakdown
    for nt in result.node_trace:
        name = nt.get("node", "")
        wall = nt.get("wall_s", 0.0)
        if "retriev" in name.lower():
            result.retrieval_nodes += 1
            result.retrieval_total_s += wall
        elif any(kw in name.lower() for kw in ("fast_path", "brief", "plan", "sub_agent",
                                                 "reflect", "report", "synth")):
            result.llm_total_s += wall

    # Quality: packed context
    packed = final_state.get("packed_context", [])
    result.n_packed = len(packed)

    # Deep-specific metrics
    result.n_sub_findings = len(final_state.get("sub_findings", []))
    result.supervisor_rounds = final_state.get("supervisor_round", 0)

    # Output
    output = final_state.get("final_output", "") or final_state.get("draft_output", "")
    result.output_length = len(output)

    # Cost model: amortised infra
    cost_per_s = _MONTHLY_COST_USD / _SECONDS_PER_MONTH
    result.cost_per_query_usd = round(cost_per_s * result.wall_s, 6)

    return result


# ── Main ────────────────────────────────────────────────────────────────────

async def async_main(tiers: list[str]):
    output_dir = Path("evals/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, list[E2EResult]] = {}

    print("=" * 70)
    print("DEEP RESEARCH — FULL E2E GRAPH BENCHMARK")
    print("=" * 70)
    print(f"Tiers: {', '.join(tiers)}")
    print(f"LLM: meta-llama/Llama-3.1-8B-Instruct (GPU) + Qwen2.5-3B (CPU)")
    print()

    for tier in tiers:
        queries = QUERIES.get(tier, [])
        if not queries:
            continue

        print(f"\n{'─'*60}")
        print(f"  TIER: {tier.upper()} ({len(queries)} queries)")
        print(f"{'─'*60}")

        tier_results = []
        for i, q in enumerate(queries):
            print(f"\n  [{i+1}/{len(queries)}] {q[:70]}...")
            result = await run_graph_e2e(q, tier)
            tier_results.append(result)

            if result.error:
                print(f"    ✗ ERROR: {result.error[:100]}")
            else:
                print(f"    ✓ {result.wall_s:.1f}s  "
                      f"LLM={result.llm_calls} calls/{result.output_tokens} tok  "
                      f"retrieval={result.retrieval_total_s:.1f}s  "
                      f"packed={result.n_packed}  "
                      f"output={result.output_length} chars")
                if result.n_sub_findings:
                    print(f"      sub-findings={result.n_sub_findings}  "
                          f"supervisor_rounds={result.supervisor_rounds}")

                # Per-node trace
                for nt in result.node_trace:
                    name = nt.get("node", "")
                    wall = nt.get("wall_s", 0.0)
                    extra = ""
                    if nt.get("subtask_count"):
                        extra = f" ({nt['subtask_count']} subtasks)"
                    if nt.get("coverage"):
                        extra = f" (coverage={nt['coverage']:.2f})"
                    print(f"      {name:30s}  {wall:7.2f}s{extra}")

        all_results[tier] = tier_results

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    output = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scenario": "deep_research",
            "tiers": tiers,
            "type": "full_e2e_graph",
        },
        "results": {},
        "summary": {},
    }

    for tier in tiers:
        results = all_results.get(tier, [])
        ok = [r for r in results if not r.error]
        if not ok:
            print(f"\n  {tier.upper()}: all failed")
            output["results"][tier] = [asdict(r) for r in results]
            continue

        walls = [r.wall_s for r in ok]
        llm_calls = [r.llm_calls for r in ok]
        out_tok = [r.output_tokens for r in ok]
        ret_s = [r.retrieval_total_s for r in ok]
        llm_s = [r.llm_total_s for r in ok]
        packed = [r.n_packed for r in ok]
        costs = [r.cost_per_query_usd for r in ok]
        output_lens = [r.output_length for r in ok]

        mean_wall = statistics.mean(walls)
        mean_ret = statistics.mean(ret_s)
        mean_llm = statistics.mean(llm_s)

        summary = {
            "n_queries": len(ok),
            "n_errors": len(results) - len(ok),
            "wall_s": {"mean": round(statistics.mean(walls), 1),
                       "min": round(min(walls), 1),
                       "max": round(max(walls), 1)},
            "llm_calls": {"mean": round(statistics.mean(llm_calls), 1),
                          "total": sum(r.llm_calls for r in ok)},
            "output_tokens": {"mean": round(statistics.mean(out_tok)),
                              "total": sum(r.output_tokens for r in ok)},
            "retrieval_s": {"mean": round(mean_ret, 2),
                            "share_pct": round(mean_ret / mean_wall * 100, 1) if mean_wall > 0 else 0},
            "llm_s": {"mean": round(mean_llm, 2),
                      "share_pct": round(mean_llm / mean_wall * 100, 1) if mean_wall > 0 else 0},
            "packed_chunks": {"mean": round(statistics.mean(packed), 1)},
            "cost_per_query_usd": round(statistics.mean(costs), 6),
            "output_length": {"mean": round(statistics.mean(output_lens))},
        }

        # Deep-tier extras
        if tier == "deep":
            sub_findings = [r.n_sub_findings for r in ok if r.n_sub_findings]
            sup_rounds = [r.supervisor_rounds for r in ok if r.supervisor_rounds]
            if sub_findings:
                summary["sub_findings_mean"] = round(statistics.mean(sub_findings), 1)
            if sup_rounds:
                summary["supervisor_rounds_mean"] = round(statistics.mean(sup_rounds), 1)

        output["summary"][tier] = summary
        output["results"][tier] = [asdict(r) for r in results]

        ret_pct = summary["retrieval_s"]["share_pct"]
        llm_pct = summary["llm_s"]["share_pct"]

        print(f"\n  {tier.upper()}:")
        print(f"    Wall time:    {summary['wall_s']['mean']:.1f}s  "
              f"(range: {summary['wall_s']['min']:.1f}–{summary['wall_s']['max']:.1f}s)")
        print(f"    LLM calls:    {summary['llm_calls']['mean']:.1f} mean  "
              f"({summary['output_tokens']['mean']:.0f} output tok/query)")
        print(f"    Retrieval:    {summary['retrieval_s']['mean']:.1f}s ({ret_pct:.0f}%)")
        print(f"    LLM time:     {summary['llm_s']['mean']:.1f}s ({llm_pct:.0f}%)")
        print(f"    Packed:       {summary['packed_chunks']['mean']:.1f} chunks")
        print(f"    Output:       {summary['output_length']['mean']:.0f} chars")
        print(f"    Cost:         ${summary['cost_per_query_usd']:.4f}/query")

    # Save
    out_path = output_dir / "deep_research_bench.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Deep Research E2E benchmark")
    parser.add_argument("--tiers", default="fast,medium,deep",
                        help="Comma-separated tiers to benchmark")
    args = parser.parse_args()

    tiers = [t.strip() for t in args.tiers.split(",")]
    asyncio.run(async_main(tiers))


if __name__ == "__main__":
    main()
