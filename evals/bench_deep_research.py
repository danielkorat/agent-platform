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
# 32 fast + 20 medium + 12 deep = 64 total — enough to saturate C=32 and C=64.

QUERIES = {
    "fast": [
        # --- original 3 ---
        "What is RAG?",
        "How does BM25 scoring work?",
        "What is cross-encoder reranking?",
        # --- added for C=32/64 coverage ---
        "What is vector similarity search?",
        "What is a knowledge graph?",
        "How does the attention mechanism work in transformers?",
        "What is semantic search?",
        "What is HNSW indexing?",
        "How does TF-IDF differ from BM25?",
        "What are sentence embeddings?",
        "What is reciprocal rank fusion?",
        "What is a LangGraph node?",
        "What is the difference between FAISS FlatIP and HNSW?",
        "What is prefix caching in LLMs?",
        "What is tensor parallelism in vLLM?",
        "What is the difference between a cross-encoder and a bi-encoder?",
        "What is role-based access control?",
        "What is PII redaction?",
        "What are server-sent events (SSE)?",
        "What is a LangGraph state machine?",
        "What is LLM token throughput?",
        "What is prompt injection?",
        "What is chunking in RAG?",
        "What is the context window of an LLM?",
        "What is an embedding model?",
        "What is ONNX Runtime?",
        "What is a retrieval pipeline?",
        "What is a supervisor agent?",
        "What is a sub-agent?",
        "What is document reranking?",
        "What is asymmetric semantic search?",
        "What is a dense retrieval model?",
    ],
    "medium": [
        # --- original 2 ---
        "How does hybrid retrieval improve over dense-only retrieval in enterprise systems?",
        "Explain the tradeoffs between single-agent and supervisor/sub-agent orchestration patterns",
        # --- added for C=16/32 coverage ---
        "What factors determine when to use HNSW vs a flat index for vector search?",
        "How should retrieval results be ranked when combining dense and sparse signals?",
        "What are the key design decisions when building a multi-tenant AI agent platform?",
        "How does tensor parallelism affect LLM inference throughput and GPU memory usage?",
        "Compare ONNX Runtime vs PyTorch inference for production NLP workloads.",
        "What are the security implications of allowing agents to execute arbitrary tool calls?",
        "How should context packing be optimised for long-context LLM inference?",
        "What is the role of a complexity classifier in a tiered agent architecture?",
        "How does reciprocal rank fusion compare to learned score fusion for retrieval?",
        "What are the tradeoffs of prefix caching vs KV-cache eviction in vLLM?",
        "How should audit logs be structured for enterprise AI regulatory compliance?",
        "When does cross-encoder reranking provide diminishing returns relative to its cost?",
        "How should a multi-agent system handle partial failures in sub-tasks?",
        "What are the latency tradeoffs of streaming vs batch LLM inference in agent pipelines?",
        "How does BM25 complement dense retrieval for out-of-vocabulary queries?",
        "What is the optimal chunk size for RAG with long-context LLMs?",
        "How should token budgets be allocated across retrieval, context, and generation stages?",
        "What are the latency implications of adding a reranker to a production retrieval pipeline?",
    ],
    "deep": [
        # --- original 2 ---
        "Compare dense retrieval vs sparse retrieval vs hybrid retrieval for enterprise knowledge systems. Analyse precision, recall, latency, and infrastructure cost tradeoffs at 100K, 500K, and 1M document scale.",
        "Research the intersection of retrieval-augmented generation and agent orchestration. How should retrieval be integrated into multi-agent systems — per-agent retrieval, shared retrieval, or supervised retrieval allocation?",
        # --- added for C=8/16 coverage ---
        "Analyse the full memory hierarchy for enterprise AI agents: in-context working memory, short-term episodic storage, and long-term knowledge bases. How should agents decide what to store, retrieve, and evict at each tier, and what are the latency and fidelity tradeoffs?",
        "Evaluate architectures for multi-tenant AI agent platforms serving 1,000+ enterprise customers. Address data isolation, shared vs dedicated LLM inference, cost allocation, compliance requirements, and per-tenant performance guarantees.",
        "Conduct a comprehensive analysis of LLM inference optimisation techniques: KV-cache management, continuous batching, speculative decoding, tensor parallelism, and quantisation. At what deployment scale does each technique deliver measurable ROI?",
        "Research the security threat model for enterprise agentic AI systems. Analyse prompt injection, tool-call abuse, data exfiltration via LLM outputs, and supply chain risks in agent frameworks. Propose defence-in-depth countermeasures for each attack vector.",
        "Compare orchestration frameworks for production agentic AI: LangGraph, AutoGen, CrewAI, and custom FSMs. Evaluate observability, fault tolerance, human-in-the-loop support, horizontal scalability, and vendor lock-in risk.",
        "Research how RAG quality degrades at scale: analyse the impact of index staleness, embedding model drift, chunk quality degradation, and retrieval-generation misalignment. Propose monitoring and automated remediation strategies.",
        "Analyse the cost structure of enterprise LLM deployments at 1M, 10M, and 100M queries per month across on-premise GPU, cloud API, and hybrid topologies. Include hardware amortisation, energy, staffing, and per-query cost modelling.",
        "Research the state of the art in agentic planning under uncertainty: compare ReAct, chain-of-thought, Tree-of-Thought, and supervisor/reflector patterns. Analyse failure modes, recovery strategies, and computational overhead at enterprise scale.",
        "Evaluate retrieval quality metrics for enterprise RAG: MRR, NDCG, precision@k, and answer faithfulness. How should offline eval sets be constructed, maintained, and used to gate model and index updates in production?",
        "Research how to build an observable, debuggable multi-agent AI system: distributed tracing, token accounting, latency attribution, anomaly detection, and cost alerting. Propose a reference monitoring stack for production deployment on bare-metal GPU infrastructure.",
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

async def run_tier_concurrent(
    queries: list[str],
    tier: str,
    concurrency: int,
) -> tuple[list[E2EResult], float, float]:
    """Run all queries for a tier with bounded concurrency.
    Returns (results, wall_total_s, throughput_qps).
    """
    sem = asyncio.Semaphore(concurrency)

    async def bounded(query: str) -> E2EResult:
        async with sem:
            return await run_graph_e2e(query, tier)

    t0 = time.perf_counter()
    results = await asyncio.gather(*[bounded(q) for q in queries])
    wall_total = time.perf_counter() - t0
    throughput = len(queries) / wall_total
    return list(results), round(wall_total, 2), round(throughput, 3)


async def async_main(tiers: list[str], concurrency_levels: list[int]):
    output_dir = Path("evals/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    # all_results[tier][concurrency] = list[E2EResult]
    all_results: dict[str, dict[int, list[E2EResult]]] = {}

    print("=" * 70)
    print("DEEP RESEARCH — FULL E2E GRAPH BENCHMARK")
    print("=" * 70)
    print(f"Tiers: {', '.join(tiers)}")
    print(f"Concurrency levels: {concurrency_levels}")
    print(f"LLM: meta-llama/Llama-3.1-8B-Instruct (GPU) + Qwen2.5-3B (CPU)")
    print()

    for tier in tiers:
        queries = QUERIES.get(tier, [])
        if not queries:
            continue

        all_results[tier] = {}

        for c in concurrency_levels:
            # Cap in-flight to the number of available queries
            effective_c = min(c, len(queries))

            print(f"\n{'─'*60}")
            print(f"  TIER: {tier.upper()}  C={c}  "
                  f"({len(queries)} queries, effective_c={effective_c})")
            print(f"{'─'*60}")

            tier_results, wall_total, throughput = await run_tier_concurrent(
                queries, tier, effective_c
            )

            for i, result in enumerate(tier_results):
                q_short = queries[i][:70]
                if result.error:
                    print(f"  [{i+1:02d}] ✗ ERROR: {result.error[:80]}")
                else:
                    print(f"  [{i+1:02d}] {result.wall_s:.1f}s  "
                          f"LLM={result.llm_calls}/{result.output_tokens}tok  "
                          f"ret={result.retrieval_total_s:.1f}s  "
                          f"packed={result.n_packed}  "
                          f"Q: {q_short}")
                    if result.n_sub_findings:
                        print(f"       sub-findings={result.n_sub_findings}  "
                              f"supervisor_rounds={result.supervisor_rounds}")

                    if c == concurrency_levels[0]:  # print node trace only at C=1
                        for nt in result.node_trace:
                            name = nt.get("node", "")
                            wall = nt.get("wall_s", 0.0)
                            extra = ""
                            if nt.get("subtask_count"):
                                extra = f" ({nt['subtask_count']} subtasks)"
                            if nt.get("coverage"):
                                extra = f" (coverage={nt['coverage']:.2f})"
                            print(f"       {name:30s}  {wall:7.2f}s{extra}")

            ok = [r for r in tier_results if not r.error]
            if ok:
                walls = [r.wall_s for r in ok]
                walls_sorted = sorted(walls)
                p50 = walls_sorted[int(len(walls_sorted) * 0.50)]
                p99 = walls_sorted[min(int(len(walls_sorted) * 0.99), len(walls_sorted) - 1)]
                print(f"\n  → C={c}: wall_total={wall_total:.1f}s  "
                      f"throughput={throughput:.3f} q/s  "
                      f"p50={p50:.1f}s  p99={p99:.1f}s  "
                      f"errors={len(tier_results)-len(ok)}")

            all_results[tier][c] = tier_results

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    output = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scenario": "deep_research",
            "tiers": tiers,
            "concurrency_levels": concurrency_levels,
            "type": "full_e2e_graph",
        },
        "results": {},
        "summary": {},
    }

    for tier in tiers:
        tier_conc_results = all_results.get(tier, {})
        if not tier_conc_results:
            continue

        output["results"][tier] = {}
        output["summary"][tier] = {}

        print(f"\n  {tier.upper()}:")
        print(f"  {'C':>4}  {'q/s':>7}  {'p50':>6}  {'p99':>6}  "
              f"{'mean_wall':>9}  {'errors':>6}")
        print(f"  {'─'*50}")

        for c, results in sorted(tier_conc_results.items()):
            ok = [r for r in results if not r.error]
            if not ok:
                print(f"  {c:>4}  {'—':>7}  {'—':>6}  {'—':>6}  {'—':>9}  "
                      f"{len(results):>6}  ALL FAILED")
                output["results"][tier][str(c)] = [asdict(r) for r in results]
                continue

            walls = [r.wall_s for r in ok]
            walls_sorted = sorted(walls)
            p50 = walls_sorted[int(len(walls_sorted) * 0.50)]
            p99 = walls_sorted[min(int(len(walls_sorted) * 0.99), len(walls_sorted) - 1)]
            mean_wall = statistics.mean(walls)

            llm_calls = [r.llm_calls for r in ok]
            out_tok = [r.output_tokens for r in ok]
            ret_s = [r.retrieval_total_s for r in ok]
            llm_s = [r.llm_total_s for r in ok]
            packed = [r.n_packed for r in ok]
            costs = [r.cost_per_query_usd for r in ok]
            output_lens = [r.output_length for r in ok]

            mean_ret = statistics.mean(ret_s)
            mean_llm = statistics.mean(llm_s)
            # Approx throughput: n_queries / (n_queries * mean_wall / effective_c)
            # Actual throughput is stored in wall_total computed during run, but
            # we don't carry it here; use mean_wall as a proxy.
            effective_c = min(c, len(results))
            throughput = effective_c / mean_wall if mean_wall > 0 else 0

            summary = {
                "concurrency": c,
                "effective_concurrency": effective_c,
                "n_queries": len(ok),
                "n_errors": len(results) - len(ok),
                "throughput_qps": round(throughput, 3),
                "wall_s": {"mean": round(mean_wall, 1),
                           "p50": round(p50, 1),
                           "p99": round(p99, 1),
                           "min": round(min(walls), 1),
                           "max": round(max(walls), 1)},
                "llm_calls": {"mean": round(statistics.mean(llm_calls), 1),
                              "total": sum(r.llm_calls for r in ok)},
                "output_tokens": {"mean": round(statistics.mean(out_tok)),
                                  "total": sum(r.output_tokens for r in ok)},
                "retrieval_s": {
                    "mean": round(mean_ret, 2),
                    "share_pct": round(mean_ret / mean_wall * 100, 1) if mean_wall > 0 else 0,
                },
                "llm_s": {
                    "mean": round(mean_llm, 2),
                    "share_pct": round(mean_llm / mean_wall * 100, 1) if mean_wall > 0 else 0,
                },
                "packed_chunks": {"mean": round(statistics.mean(packed), 1)},
                "cost_per_query_usd": round(statistics.mean(costs), 6),
                "output_length": {"mean": round(statistics.mean(output_lens))},
            }

            if tier == "deep":
                sub_findings = [r.n_sub_findings for r in ok if r.n_sub_findings]
                sup_rounds = [r.supervisor_rounds for r in ok if r.supervisor_rounds]
                if sub_findings:
                    summary["sub_findings_mean"] = round(statistics.mean(sub_findings), 1)
                if sup_rounds:
                    summary["supervisor_rounds_mean"] = round(statistics.mean(sup_rounds), 1)

            output["summary"][tier][str(c)] = summary
            output["results"][tier][str(c)] = [asdict(r) for r in results]

            print(f"  {c:>4}  {throughput:>7.3f}  {p50:>6.1f}s  {p99:>6.1f}s  "
                  f"{mean_wall:>9.1f}s  {len(results)-len(ok):>6}")

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
    parser.add_argument("--concurrency", default="1",
                        help="Comma-separated concurrency levels, e.g. 1,4,16,32,64")
    args = parser.parse_args()

    tiers = [t.strip() for t in args.tiers.split(",")]
    concurrency_levels = [int(c.strip()) for c in args.concurrency.split(",")]
    asyncio.run(async_main(tiers, concurrency_levels))


if __name__ == "__main__":
    main()
