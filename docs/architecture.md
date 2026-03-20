# Architecture

## System Overview

The Agent Platform is a **stateful graph-based orchestration system** that routes enterprise queries through the cheapest sufficient execution path. It combines Intel Xeon CPU and Arc Pro B60 GPU to maximize throughput and minimize cost per query.

## Design Principles

1. **Classification-first**: Every query is classified before execution. Simple queries never pay the cost of deep execution.
2. **Retrieval-augmented**: No query executes without grounding in retrieved context. Hallucination is bounded by design.
3. **Observable by default**: Every node, tool call, and LLM invocation emits timing and token metrics.
4. **Secure by default**: Read-only by default. Write actions require explicit approval. All outputs are PII-scrubbed.
5. **Cost-aware**: The router, packer, and reranker all minimize unnecessary token consumption.

---

## Execution Flow

```
Request → API Gateway → Ingest → Authenticate → Classify → Route
                                                            │
                    ┌───────────────────────────────────────┤
                    │                 │                      │
                   Fast            Medium                  Deep
                    │                 │                      │
              1-pass synth    Entity Extract          Write Brief
                    │          Root Cause               Decompose
                    │          Actions                 Sub-Agents
                    │          Approval?                Reflect
                    │          Closure                  Iterate?
                    │                │                  Synthesize
                    │                │                      │
                    └────────────────┴──────────────────────┘
                                     │
                              Policy Check → Format → Audit → Response
```

### Phase 1: Ingestion + Authentication (CPU)

Every request enters through the FastAPI gateway and passes through:

1. **Ingest**: Normalize the request, assign task ID, initialize state
2. **Authenticate**: Verify JWT or API key. In dev mode, a default analyst identity is injected
3. **Authorize**: Check RBAC permissions for the requested scenario and action type

### Phase 2: Classification + Routing (CPU / SLM)

The router determines two things: **scenario** (it_ops or deep_research) and **complexity** (fast / medium / deep).

**Rule-based classification** runs first:
- Deep signals: "compare", "analyze", "multi-factor", long queries (>200 chars), many entities
- Medium signals: "investigate", "root cause", "incident", action verbs
- Fast signals: short queries (<50 chars), "what is", "how to"

If rule confidence ≥ 0.7, the LLM is skipped entirely. Otherwise, the SLM (Qwen 3B on CPU) classifies with a structured JSON response in ~0.2s.

This dual-gate approach means:
- **70-80% of queries** are classified by rules alone (zero LLM cost)
- **20-30% of edge cases** use the SLM (0.2s, no GPU contention)

### Phase 3: Retrieval (CPU)

Retrieval runs on the Xeon CPU through a multi-stage pipeline:

1. **Query expansion**: Build retrieval variants from the original query + classification context
2. **Dense search (FAISS)**: BGE-small-en-v1.5 embeddings → cosine similarity → top-N candidates
3. **Lexical search (BM25)**: BM25Okapi keyword match → top-N candidates
4. **Reciprocal Rank Fusion**: Merge and deduplicate across both result sets (k=60)
5. **Cross-encoder reranking**: ms-marco-MiniLM-L-6-v2 scores each candidate against the query
6. **Context packing**: Deduplicate (90% overlap threshold), enforce source diversity (max 3 per source), trim to token budget

The retrieval pipeline typically returns 5-10 high-quality passages in <0.5s.

### Phase 4: Scenario Execution (GPU + CPU)

#### IT Ops Path

**Fast**: Single-pass synthesis using top-ranked context and system prompt. No entity extraction, no multi-turn reasoning.

**Medium** (full pipeline):
1. **Extract entities** (SLM/CPU): Parse ticket details, identify affected systems, severity, timestamps
2. **Root cause analysis** (LLM/GPU): Analyze entities + context to hypothesize root cause with confidence score
3. **Recommended actions** (LLM/GPU): Generate risk-aware remediation steps, flag high-risk actions for approval
4. **Human approval gate**: If risk > medium, pause and wait for explicit approval (auto-approved in demo mode)
5. **Closure note** (LLM/GPU): Generate structured incident summary

#### Deep Research Path

**Fast**: Single-pass synthesis (same as IT Ops fast path but with research-tuned prompts).

**Medium**: Research brief → direct final report (no decomposition).

**Deep** (full pipeline):
1. **Research brief** (LLM/GPU): Synthesize initial findings from retrieval, identify key themes
2. **Supervisor decomposition** (LLM/GPU): Break the query into 2-4 independent subtopics
3. **Sub-agent execution** (sequential, each: retrieve → synthesize): Each subtask gets its own retrieval + synthesis pass
4. **Supervisor reflection** (LLM/GPU): Assess coverage, identify gaps, decide: iterate or finalize
5. **Final report synthesis** (LLM/GPU): Merge all sub-findings into a structured, cited decision memo

The deep path has a circuit breaker: max 2 reflection iterations before forced finalization.

### Phase 5: Output + Audit (CPU)

1. **Policy check**: Scan output for PII, blocked patterns, prompt injection residue. Redact as needed
2. **Format response**: Build citation list, attach metrics, structure output
3. **Audit persistence**: Log full execution trace to SQLite (task, path, timing, tokens, approval decision)

---

## Hardware Mapping

```
┌─────────────────────────────────────────────────────────────────┐
│                 Intel Xeon 6 (CPU)                              │
│                                                                  │
│  Control Plane:  API, routing, auth, RBAC, audit               │
│  Classification: Qwen 3B SLM via vLLM (port 8001)             │
│  Retrieval:      BGE-small embeddings, FAISS search, BM25      │
│  Reranking:      Cross-encoder (22M params)                    │
│  Post-process:   PII redaction, context packing, formatting    │
│                                                                  │
│  Why CPU: I/O-bound, small models, deterministic processing    │
│  Typical load: 1-5% of pipeline time for simple queries        │
│               60%+ for complex queries with entity extraction   │
├─────────────────────────────────────────────────────────────────┤
│                 Intel Arc Pro B60 × 8 (GPU)                     │
│                                                                  │
│  Reasoning:      Root cause analysis (Llama-3.1-8B-Instruct)  │
│  Synthesis:      Report generation, closure notes              │
│  Multi-hop:      Sub-agent research, supervisor reflection     │
│                                                                  │
│  Serving:        vLLM with tp=8, prefix caching, eager mode   │
│  Performance:    ~41 tok/s output, 131K max context            │
│                                                                  │
│  Why GPU: Autoregressive generation is memory-bandwidth bound  │
│           8 GPUs provide enough KV-cache for large contexts    │
└─────────────────────────────────────────────────────────────────┘
```

### Pipeline Staging Effect at Scale

At concurrency > 8, the CPU classification stage creates a **natural rate-limiting buffer**:

```
Requests:  R1  R2  R3  R4  R5  R6  R7  R8  R9  R10 ...

GPU-only:  All 10 hit GPU simultaneously
           → KV-cache saturated
           → Throughput drops (measured: -25% at c=32)

Heterogeneous:
           CPU classifies R1-R10 in staggered 0.2s slots
           GPU receives requests in waves of 2-3
           → KV-cache stays in optimal batching regime
           → Throughput keeps scaling (measured: +81% from c=16 to c=32)
```

This is not speculation. It is measured and reproducible.

---

## LangGraph Design

### State Schema

```python
class AgentState(TypedDict, total=False):
    # Identity
    task_id: str
    scenario: str
    tenant_id: str
    
    # Auth
    user_id: str
    user_role: str
    
    # Classification
    query: str
    complexity: str              # fast | medium | deep
    risk_level: str              # low | medium | high | critical
    execution_path: str          # e.g., "it_ops_single_agent"
    
    # Retrieval
    retrieval_plan: dict
    retrieved_chunks: list[dict]
    packed_context: str
    
    # LLM message accumulation
    messages: Annotated[list[BaseMessage], add_messages]
    
    # Scenario-specific fields...
    # Observability fields...
```

### Graph Construction Pattern

Both scenarios share a common prefix (ingest → auth → classify → retrieve → route) and suffix (policy → format → audit). The scenario-specific middle section is composed as a subgraph:

```python
# Shared prefix
graph.add_node("ingest", ingest_request)
graph.add_node("authenticate", authenticate_and_authorize)
graph.add_node("classify", classify_scenario_and_complexity)
graph.add_node("retrieve", retrieve_candidates)
graph.add_node("route", route_execution_path)

# Scenario-specific (conditional based on route output)
graph.add_conditional_edges("route", scenario_router, {
    "it_ops_fast": "it_fast_synth",
    "it_ops_single_agent": "it_extract",
    "research_fast": "research_fast_synth",
    "research_medium": "research_brief",
    "research_deep": "research_brief",
})
```

### Bounded Execution

Every loop and agent has explicit limits:
- **Agent node loops**: max 15 iterations
- **Supervisor rounds**: max 5 reflection cycles
- **Sub-agents per task**: max 4 (configurable)
- **Context tokens per retrieval**: max 8,192 tokens

These prevent runaway cost and latency.

---

## Security Architecture

```
Request
  │
  ▼
┌──────────────────────┐
│  JWT / API Key Auth   │ ← Reject unauthenticated
├──────────────────────┤
│  RBAC Check           │ ← Reject unauthorized
├──────────────────────┤
│  Input Sanitization   │ ← Log prompt injection attempts
├──────────────────────┤
│  Execution (graph)    │
├──────────────────────┤
│  PII Redaction        │ ← Scrub before output
├──────────────────────┤
│  Output Policy Check  │ ← Block dangerous patterns
├──────────────────────┤
│  Audit Log            │ ← Full trace persisted
└──────────────────────┘
```

Key design decisions:
- **All connectors are read-only by default**. Write actions require both RBAC and approval.
- **PII redaction runs on output, not input** — the model sees real data for better reasoning, but the user never sees PII in the response.
- **Prompt injection detection is heuristic** — it flags but does not block retrieved content, since false positives would degrade retrieval quality.
- **Approval gate is async** — the graph pauses and waits for an explicit decision via the API. In demo mode, it auto-approves.

---

## Retrieval Architecture

### Hybrid Search Design

| Stage | Purpose | Typical Latency |
|---|---|---|
| Embedding | Convert query to 384-dim vector | 5-10ms |
| FAISS search | Dense similarity, top-50 | 1-5ms |
| BM25 search | Keyword matching, top-50 | 5-10ms |
| RRF fusion | Merge + deduplicate | <1ms |
| Cross-encoder | Score top-50 against query | 50-200ms |
| Context packing | Dedup, diversity, budget | <1ms |

**Why hybrid?** Dense search excels at semantic similarity but misses exact keyword matches. BM25 catches exact terms but fails on paraphrase. RRF fusion gives the best of both.

**Why reranking?** FAISS top-50 typically has 60-80% irrelevant results. The cross-encoder prunes these, reducing token waste in downstream LLM calls by 60-80%.

### Indexing

- **Chunking**: 512-token chunks with 64-token overlap (configurable)
- **Embeddings**: BGE-small-en-v1.5 (384-dim, 33M params, runs on CPU in <50ms/chunk)
- **Index**: FAISS IndexFlatIP (exact cosine similarity after L2 normalization)
- **Metadata**: Every chunk carries `chunk_id`, `source_id`, `title`, `text`, `tenant_id`

---

## Deployment Architecture

### Single-Node (Development / Demo)

```
┌─────────────────────────────────────────┐
│            Single Server                 │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  Agent Platform (port 8081)      │   │
│  │  Python process                   │   │
│  └──────────┬──────────┬────────────┘   │
│             │          │                 │
│  ┌──────────┴─┐  ┌────┴──────────┐     │
│  │ vLLM GPU   │  │ vLLM CPU      │     │
│  │ (port 8000)│  │ (port 8001)   │     │
│  │ Llama 8B   │  │ Qwen 3B       │     │
│  │ tp=8       │  │ tp=1          │     │
│  └────────────┘  └───────────────┘     │
│                                          │
│  SQLite DB │ FAISS Index │ BM25 Index   │
└─────────────────────────────────────────┘
```

### Docker Compose (Production-Ready)

```yaml
services:
  vllm-gpu:       # Llama 8B on Arc Pro B60 × 8
  vllm-cpu:       # Qwen 3B on Xeon
  agent-platform: # API + Frontend + Retrieval
```

All services use `network_mode: host` for simplicity on single-node Intel deployments. For multi-node, replace with Docker overlay networks.

---

## Extending the Platform

### Adding a New Scenario

1. Create `graphs/new_scenario/graph.py` — define the LangGraph graph
2. Create `graphs/new_scenario/nodes.py` — define scenario-specific nodes
3. Add `new_scenario` to `models.Scenario` enum
4. Register the graph in the route conditional edges
5. Add connectors as needed

### Adding a New Connector

1. Subclass `connectors.base.BaseConnector`
2. Implement `search()`, `get()`, optionally `execute_action()`
3. Register in `connectors.tool_proxy.CONNECTOR_REGISTRY`
4. Add mock data for demo purposes

### Swapping the LLM

Change the model in `.env`:
```bash
LLM_MODEL=meta-llama/Llama-3.3-70B-Instruct
SECONDARY_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

The platform is model-agnostic — any vLLM-compatible model works. Adjust `tp` in the vLLM server config to match the model's size.
