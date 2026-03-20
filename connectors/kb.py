"""Mock knowledge base connector — simulates Confluence/SharePoint/wiki."""

from __future__ import annotations

from typing import Any

from connectors.base import BaseConnector

# ── Sample KB articles ───────────────────────────────────────

_MOCK_KB = [
    {
        "id": "KB-001",
        "title": "Runbook: PostgreSQL Connection Pool Exhaustion",
        "source": "runbook",
        "text": (
            "## Symptoms\n"
            "- Application returning 503/504 errors\n"
            "- PostgreSQL logs showing 'too many connections'\n"
            "- Connection pool metrics exceeding configured maximum\n\n"
            "## Root Causes\n"
            "1. Connection leak in application code (most common)\n"
            "2. Long-running transactions holding connections\n"
            "3. Pool size misconfiguration for current load\n"
            "4. Sudden traffic spike exceeding pool capacity\n\n"
            "## Resolution Steps\n"
            "1. **Immediate**: Identify and kill idle connections: "
            "`SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '5 minutes';`\n"
            "2. **Short-term**: Increase pool size to 150 in `pgbouncer.ini` and restart pgbouncer\n"
            "3. **Long-term**: Review application connection management, implement connection timeouts, "
            "add `idle_in_transaction_session_timeout = 30000` to PostgreSQL config\n\n"
            "## Escalation\n"
            "If pool exhaustion recurs within 24 hours, escalate to DBA team."
        ),
        "tags": ["postgresql", "connection-pool", "database", "runbook"],
        "tenant_id": "default",
    },
    {
        "id": "KB-002",
        "title": "Runbook: Kubernetes OOMKilled Troubleshooting",
        "source": "runbook",
        "text": (
            "## Symptoms\n"
            "- Pods in CrashLoopBackOff with OOMKilled reason\n"
            "- Container memory exceeding resource limits\n\n"
            "## Diagnosis\n"
            "1. Check events: `kubectl describe pod <pod> -n <namespace>`\n"
            "2. Check memory usage: `kubectl top pod <pod> -n <namespace>`\n"
            "3. Review recent deployments: `kubectl rollout history deployment/<name>`\n\n"
            "## Resolution\n"
            "1. **Quick fix**: Increase memory limit: `kubectl set resources deployment/<name> --limits=memory=1Gi`\n"
            "2. **If leak suspected**: Enable heap profiling, capture dump before OOM\n"
            "3. **Rollback if recent deploy**: `kubectl rollout undo deployment/<name>`\n"
            "4. **Long-term**: Add memory profiling to CI pipeline, set up VPA (Vertical Pod Autoscaler)"
        ),
        "tags": ["kubernetes", "oomkilled", "memory", "crashloopbackoff", "runbook"],
        "tenant_id": "default",
    },
    {
        "id": "KB-003",
        "title": "Runbook: SSL Certificate Renewal Failure",
        "source": "runbook",
        "text": (
            "## Symptoms\n"
            "- cert-manager Certificate resource showing False ready condition\n"
            "- ACME challenge failing with timeout or DNS errors\n\n"
            "## Diagnosis\n"
            "1. Check certificate status: `kubectl get certificate -A`\n"
            "2. Check challenges: `kubectl get challenges -A`\n"
            "3. Check cert-manager logs: `kubectl logs -n cert-manager deploy/cert-manager`\n\n"
            "## Resolution\n"
            "1. For DNS challenge timeout: verify DNS provider API credentials in secret\n"
            "2. For HTTP challenge: ensure `.well-known/acme-challenge` is accessible\n"
            "3. Manual fallback: generate cert with certbot, create secret manually\n"
            "4. Emergency: use self-signed cert temporarily (with client notification)"
        ),
        "tags": ["ssl", "certificate", "cert-manager", "acme", "tls", "runbook"],
        "tenant_id": "default",
    },
    {
        "id": "KB-004",
        "title": "Guide: Envoy Proxy Performance Tuning",
        "source": "knowledge_base",
        "text": (
            "## Overview\n"
            "Envoy proxy (used as Istio sidecar) can become a bottleneck under high load.\n\n"
            "## Common Issues\n"
            "1. **High CPU**: Circuit breaker thresholds too high, allowing too many concurrent requests\n"
            "2. **High latency**: Connection pool exhaustion to upstream clusters\n"
            "3. **Memory growth**: Access log buffering with high traffic\n\n"
            "## Tuning Parameters\n"
            "- `max_connections`: default 1024, increase for high-throughput services\n"
            "- `max_pending_requests`: default 1024, tune based on upstream capacity\n"
            "- `max_requests`: concurrent request limit per connection\n"
            "- `cpu_limit`: ensure sidecar has adequate CPU allocation (at least 500m for high-traffic)\n\n"
            "## Quick Diagnosis\n"
            "`kubectl exec <pod> -c istio-proxy -- pilot-agent request GET stats | grep upstream_cx`"
        ),
        "tags": ["envoy", "proxy", "istio", "performance", "latency"],
        "tenant_id": "default",
    },
    {
        "id": "KB-005",
        "title": "Research: RAG Pipeline Architecture Patterns",
        "source": "research_doc",
        "text": (
            "## Retrieval-Augmented Generation (RAG)\n"
            "RAG combines retrieval from a knowledge base with LLM generation to produce "
            "grounded, cited responses.\n\n"
            "## Key Components\n"
            "1. **Embedding model**: Converts text to dense vectors (e.g., BGE, E5, GTE)\n"
            "2. **Vector store**: FAISS, Milvus, Pinecone for similarity search\n"
            "3. **Reranker**: Cross-encoder model for precision refinement\n"
            "4. **Generator**: LLM that produces answers from retrieved context\n\n"
            "## Best Practices\n"
            "- Hybrid retrieval (dense + lexical) outperforms either alone\n"
            "- Reranking reduces context noise and token cost\n"
            "- Chunk size 256-512 tokens balances precision and recall\n"
            "- Citation tracking improves trustworthiness\n\n"
            "## Advanced Patterns\n"
            "- Multi-hop retrieval for complex queries\n"
            "- Supervisor + sub-agent decomposition for research tasks\n"
            "- Complexity routing to match cost with query difficulty"
        ),
        "tags": ["rag", "retrieval", "llm", "architecture", "research"],
        "tenant_id": "default",
    },
    {
        "id": "KB-006",
        "title": "Research: Heterogeneous Computing for AI Inference",
        "source": "research_doc",
        "text": (
            "## Heterogeneous Computing\n"
            "Mixing CPU and GPU hardware for AI workloads can improve cost efficiency.\n\n"
            "## Key Findings\n"
            "- CPU (Xeon) handles orchestration, preprocessing, reranking efficiently\n"
            "- GPU (Arc Pro B60) provides high-throughput LLM inference\n"
            "- Routing cheap classification to CPU creates pipeline staging buffer\n"
            "- At high concurrency (32+), heterogeneous configs prevent GPU KV-cache saturation\n\n"
            "## Benchmarked Results\n"
            "- 2.27× throughput advantage at c=32 vs GPU-only\n"
            "- 31% lower cost-per-query at production concurrency\n"
            "- Quality parity across configurations (3.9-4.1/5)\n"
            "- GPU saturation causes 25% throughput regression at c=32\n\n"
            "## Recommendation\n"
            "Deploy with Xeon for orchestration + GPU for reasoning/synthesis. "
            "Only offload steps with <5% of GPU pipeline runtime to CPU."
        ),
        "tags": ["heterogeneous", "xeon", "gpu", "benchmark", "tco", "research"],
        "tenant_id": "default",
    },
    {
        "id": "KB-007",
        "title": "Research: LangGraph Agent Orchestration",
        "source": "research_doc",
        "text": (
            "## LangGraph for Agentic AI\n"
            "LangGraph provides stateful, graph-based orchestration for AI agents.\n\n"
            "## Architecture Patterns\n"
            "1. **ReAct loop**: Agent reasons, acts (tool call), observes, repeats\n"
            "2. **Supervisor/sub-agent**: Supervisor decomposes, sub-agents research independently\n"
            "3. **Conditional routing**: Route by complexity/risk to appropriate execution path\n\n"
            "## Open Deep Research Pattern\n"
            "- Scope → Research → Write (not parallel writing)\n"
            "- Sub-agents return CLEANED findings (not raw tool dumps)\n"
            "- Supervisor reflects on coverage before synthesis\n"
            "- Single-pass final writing to avoid coordination issues\n\n"
            "## Best Practices\n"
            "- Use TypedDict shared state for strong typing\n"
            "- Bounded iterations with circuit breakers\n"
            "- Context isolation between sub-agents\n"
            "- Observable node-level metrics"
        ),
        "tags": ["langgraph", "agent", "orchestration", "research", "supervisor"],
        "tenant_id": "default",
    },
]


class KBConnector(BaseConnector):
    """Mock knowledge base connector."""

    @property
    def name(self) -> str:
        return "knowledge_base"

    async def search(self, query: str, **kwargs) -> list[dict[str, Any]]:
        """Search KB articles by keyword match."""
        query_lower = query.lower()
        results = []
        for article in _MOCK_KB:
            searchable = f"{article['title']} {article['text']} {' '.join(article['tags'])}".lower()
            if any(word in searchable for word in query_lower.split()):
                results.append(article)
        return results

    async def get(self, item_id: str) -> dict[str, Any] | None:
        for article in _MOCK_KB:
            if article["id"] == item_id:
                return article
        return None
