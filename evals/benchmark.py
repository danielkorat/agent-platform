"""Evaluation / benchmark harness.

Usage:
    python -m evals.benchmark --quick
    python -m evals.benchmark --queries 10 --concurrency 1,4,8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Eval queries ─────────────────────────────────────────────

EVAL_QUERIES = [
    # IT Ops — simple
    {"query": "What is the status of incident INC-001?", "scenario": "it_ops", "expected_complexity": "fast"},
    {"query": "How do I troubleshoot PostgreSQL connection pool exhaustion?", "scenario": "it_ops", "expected_complexity": "medium"},
    {"query": "Kubernetes pods are in CrashLoopBackOff with OOMKilled", "scenario": "it_ops", "expected_complexity": "medium"},
    {"query": "SSL certificate expiring in 7 days, cert-manager renewal failed", "scenario": "it_ops", "expected_complexity": "medium"},
    {"query": "API latency spike on payment gateway, Envoy sidecar at 95% CPU", "scenario": "it_ops", "expected_complexity": "medium"},

    # Deep Research — simple
    {"query": "What is RAG?", "scenario": "deep_research", "expected_complexity": "fast"},
    {"query": "How does cross-encoder reranking work?", "scenario": "deep_research", "expected_complexity": "fast"},

    # Deep Research — complex
    {"query": "Compare dense retrieval vs hybrid retrieval for enterprise knowledge systems. What are the tradeoffs?", "scenario": "deep_research", "expected_complexity": "deep"},
    {"query": "Analyze heterogeneous computing for AI inference. Compare GPU-only vs CPU+GPU configurations.", "scenario": "deep_research", "expected_complexity": "deep"},
    {"query": "Investigate LangGraph agent orchestration patterns. How does supervisor/sub-agent decomposition compare to single-agent approaches?", "scenario": "deep_research", "expected_complexity": "deep"},
]


@dataclass
class QueryResult:
    query: str
    scenario: str
    expected_complexity: str
    actual_complexity: str = ""
    execution_path: str = ""
    elapsed_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    status: str = ""
    error: str = ""


async def run_single_query(query_def: dict, api_base: str = "http://localhost:8081") -> QueryResult:
    """Run a single query through the API and collect metrics."""
    import httpx

    result = QueryResult(
        query=query_def["query"],
        scenario=query_def["scenario"],
        expected_complexity=query_def["expected_complexity"],
    )

    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
        t0 = time.time()
        try:
            # Submit task
            resp = await client.post(f"{api_base}/api/task", json={
                "query": query_def["query"],
                "scenario": query_def["scenario"],
            })
            resp.raise_for_status()
            task_id = resp.json()["task_id"]

            # Poll for completion
            while True:
                await asyncio.sleep(1.0)
                status_resp = await client.get(f"{api_base}/api/task/{task_id}")
                if status_resp.status_code != 200:
                    continue
                data = status_resp.json()
                if data["status"] in ("complete", "failed"):
                    result.status = data["status"]
                    result.execution_path = data.get("execution_path", "")
                    if data.get("metrics"):
                        m = data["metrics"]
                        result.input_tokens = m.get("input_tokens", 0)
                        result.output_tokens = m.get("output_tokens", 0)
                        result.llm_calls = m.get("llm_calls", 0)
                        result.actual_complexity = m.get("execution_path", "").split("_")[-1] if m.get("execution_path") else ""
                    if data.get("errors"):
                        result.error = str(data["errors"])
                    break
                if time.time() - t0 > 120:
                    result.status = "timeout"
                    break

        except Exception as e:
            result.status = "error"
            result.error = str(e)

        result.elapsed_s = time.time() - t0

    return result


async def run_benchmark(queries: list[dict], concurrency: int = 1, api_base: str = "http://localhost:8081") -> list[QueryResult]:
    """Run benchmark at given concurrency."""
    if concurrency == 1:
        results = []
        for q in queries:
            r = await run_single_query(q, api_base)
            print(f"  {r.status:8s} {r.elapsed_s:6.1f}s  {r.query[:60]}")
            results.append(r)
        return results

    sem = asyncio.Semaphore(concurrency)

    async def bounded(q):
        async with sem:
            return await run_single_query(q, api_base)

    results = await asyncio.gather(*[bounded(q) for q in queries])
    for r in results:
        print(f"  {r.status:8s} {r.elapsed_s:6.1f}s  {r.query[:60]}")
    return list(results)


def main():
    parser = argparse.ArgumentParser(description="Agent Platform Benchmark")
    parser.add_argument("--quick", action="store_true", help="Run only 3 queries")
    parser.add_argument("--queries", type=int, default=len(EVAL_QUERIES))
    parser.add_argument("--concurrency", type=str, default="1")
    parser.add_argument("--api", type=str, default="http://localhost:8081")
    parser.add_argument("--output", type=str, default="evals/results")
    args = parser.parse_args()

    queries = EVAL_QUERIES[:3] if args.quick else EVAL_QUERIES[:args.queries]
    concurrency_levels = [int(c) for c in args.concurrency.split(",")]

    Path(args.output).mkdir(parents=True, exist_ok=True)
    all_results: dict[int, list[QueryResult]] = {}

    for c in concurrency_levels:
        print(f"\n=== Concurrency={c}, Queries={len(queries)} ===")
        results = asyncio.run(run_benchmark(queries, c, args.api))
        all_results[c] = results

        # Summary
        completed = [r for r in results if r.status == "complete"]
        avg_latency = sum(r.elapsed_s for r in completed) / len(completed) if completed else 0
        throughput = len(completed) / sum(r.elapsed_s for r in completed) * 60 if completed else 0
        print(f"  Completed: {len(completed)}/{len(results)}")
        print(f"  Avg latency: {avg_latency:.1f}s")
        print(f"  Throughput: {throughput:.1f} q/min")

    # Save results
    out_path = Path(args.output) / f"benchmark_{int(time.time())}.json"
    output = {
        str(c): [
            {
                "query": r.query, "scenario": r.scenario,
                "expected": r.expected_complexity, "actual": r.actual_complexity,
                "path": r.execution_path, "elapsed_s": round(r.elapsed_s, 2),
                "in_tok": r.input_tokens, "out_tok": r.output_tokens,
                "calls": r.llm_calls, "status": r.status, "error": r.error,
            }
            for r in results
        ]
        for c, results in all_results.items()
    }
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
