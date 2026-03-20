# Agent Platform — Copilot Instructions

## Purpose

Enterprise Agent Platform: LangGraph orchestration + vLLM inference on Intel Xeon 6 + Arc Pro B60.
Two scenarios (IT Ops, Deep Research) sharing a common prefix/suffix graph with scenario-specific middle sections.
Three execution tiers (Fast, Medium, Deep) routed by a rules-first, LLM-second complexity classifier.

## Repository Structure

```
agent_platform/
├── api.py                        # FastAPI gateway + SSE streaming (port 8081)
├── main.py                       # Entry point (uvicorn)
├── config.py                     # Pydantic Settings (env_file, runtime config)
├── models.py                     # All Pydantic models: API, events, structured outputs
├── token_tracker.py              # Per-task metrics: latency, tokens, HW utilization
│
├── llm/
│   ├── client.py                 # LLMClient: streaming chat() + structured chat_structured()
│   └── agent_llm.py              # LangChain ChatOpenAI wrappers for graph nodes
│
├── graphs/
│   ├── shared/
│   │   ├── state.py              # AgentState TypedDict (shared across all graphs)
│   │   ├── router.py             # Rules + LLM complexity classifier → fast/medium/deep
│   │   ├── nodes.py              # 9 shared nodes (ingest, auth, classify, retrieve, route, policy, format, audit)
│   │   ├── policies.py           # Output safety: blocked patterns, PII, risk gating
│   │   └── prompts.py            # Shared prompt templates
│   ├── it_ops/
│   │   ├── graph.py              # IT Ops LangGraph builder
│   │   ├── nodes.py              # Entity extract, root cause, actions, approval, closure
│   │   └── prompts.py            # IT Ops prompt templates
│   └── deep_research/
│       ├── graph.py              # Deep Research LangGraph builder
│       ├── nodes.py              # Brief, supervisor decompose, sub-agents, reflect, synthesis
│       └── prompts.py            # Research prompt templates
│
├── retrieval/
│   ├── vector_store.py           # FAISS IndexFlatIP (cosine sim after L2 norm)
│   ├── lexical_store.py          # BM25 via rank_bm25
│   ├── embeddings.py             # BGE-small-en-v1.5 (384-dim)
│   ├── fusion.py                 # Reciprocal Rank Fusion (k=60)
│   ├── reranker.py               # Cross-encoder ms-marco-MiniLM-L-6-v2
│   ├── packer.py                 # Context packing: dedup, diversity, token budget
│   └── service.py                # RetrievalService: vector → lexical → RRF → rerank → pack
│
├── security/
│   ├── auth.py                   # JWT (HMAC-SHA256) + API key auth
│   ├── rbac.py                   # 4 roles: admin, analyst, operator, viewer
│   ├── pii.py                    # Regex PII/secret redaction
│   ├── prompt_injection.py       # Heuristic injection detection
│   └── approvals.py              # Human approval gate (async event-based)
│
├── connectors/
│   ├── base.py                   # BaseConnector ABC
│   ├── tickets.py                # Mock ticket system (5 incidents)
│   ├── kb.py                     # Mock KB (7 articles: 4 runbooks, 3 research)
│   ├── tool_proxy.py             # Secure tool proxy with allowlist + RBAC
│   └── build_demo_index.py       # FAISS + BM25 index builder from mock data
│
├── db/
│   ├── models.py                 # SQLAlchemy ORM: TaskRecord, AuditLog
│   └── session.py                # Async engine, session factory, init_db()
│
├── frontend/                     # Static web UI (served by FastAPI)
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── tests/                        # pytest tests
├── evals/                        # Benchmark harness
├── deploy/                       # Docker Compose + Dockerfile
├── docs/                         # Architecture, ROI, marketing docs
├── scripts/                      # Entry scripts
└── data/                         # FAISS index + BM25 data (gitignored)
```

## LLM Server Configuration

### Primary (GPU — reasoning and synthesis)
```
URL:    http://localhost:8000/v1
Model:  meta-llama/Llama-3.1-8B-Instruct
TP:     8 (tensor-parallelism across 8× Arc Pro B60)
Mode:   enforce-eager (eager=false → OOM on XPU)
Cache:  prefix-caching enabled
Max:    131072 context window
```

### Secondary (CPU — classification and entity extraction)
```
URL:    http://localhost:8001/v1
Model:  Qwen/Qwen2.5-3B-Instruct
TP:     1 (single Xeon socket)
```

### Routing Rule
A module runs on CPU/SLM if its name appears in `SECONDARY_LLM_MODULES` env var (CSV).
Default: `classify,extract_entities,analyze_gaps`.
Everything else runs on the primary GPU endpoint.
Implementation: `llm.client.get_llm(caller=)` checks `config.secondary_modules_set`.

## Environment Configuration

All config via `.env` file (pydantic-settings `env_file=".env"`):
```
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=meta-llama/Llama-3.1-8B-Instruct
LLM_HARDWARE=XPU
SECONDARY_LLM_BASE_URL=http://localhost:8001/v1
SECONDARY_LLM_MODEL=Qwen/Qwen2.5-3B-Instruct
SECONDARY_LLM_HARDWARE=Xeon
SECONDARY_LLM_MODULES=classify,extract_entities,analyze_gaps
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
API_PORT=8081
```

## Common Commands

```bash
# Install
pip install -e .

# Build demo indexes
python -m connectors.build_demo_index

# Run server
python main.py

# Run tests
pytest tests/ -v

# Run benchmarks
python -m evals.benchmark --quick

# Docker Compose (full stack)
cd deploy && docker compose up -d
```

## Key Rules

### 1. Proxy bypass for localhost LLM calls
This host has corporate proxy env vars. `httpx` picks them up and routes localhost requests through the proxy (which fails). Always use `trust_env=False`:
```python
http_client = httpx.AsyncClient(trust_env=False)
AsyncOpenAI(base_url=..., http_client=http_client)
```
Do NOT rely on `no_proxy` env var — httpx doesn't consistently respect it.

### 2. AgentState is TypedDict with total=False
All fields except `messages` are optional. Never assume a field exists — always use `.get()` with defaults.
`messages` uses `Annotated[list[BaseMessage], add_messages]` for LangGraph's message accumulation reducer.

### 3. Graph nodes are async functions returning partial state dicts
Every node signature: `async def node_name(state: AgentState) -> dict:`. Return only the fields that changed. LangGraph merges them into the state.

### 4. Router: rules first, LLM second
`classify_by_rules()` uses keyword patterns and query structure. If confidence ≥ 0.7, skip LLM. This saves 70-80% of classification latency. Only ambiguous queries hit the SLM.

### 5. Retrieval pipeline order matters
Vector → Lexical → RRF Fusion → Cross-encoder Rerank → Context Pack. Do not reorder. The cross-encoder expects fused candidates (not raw FAISS output).

### 6. Cross-encoder and embedding models are lazy-loaded singletons
`reranker.py` and `embeddings.py` load models on first call. This avoids startup cost if retrieval isn't needed. Do not pre-load in imports.

### 7. Context packer enforces three constraints
1. Deduplication: 90% text overlap → skip
2. Source diversity: max 3 chunks per source_id
3. Token budget: max `max_context_tokens` (default 8192)
All three must pass for a chunk to be included.

### 8. Security: read-only by default
All connectors are read-only unless explicitly marked. Write actions require both RBAC check AND approval gate. The tool_proxy enforces this.

### 9. PII redaction runs on output, not input
The model sees real data for accurate reasoning. PII is scrubbed from the response before it reaches the user. Patterns: email, phone, SSN, credit card, IP address, API key, bearer token, password.

### 10. Approval gate is async event-based
`ApprovalGate.wait_for_decision()` sets an asyncio.Event and blocks. The API endpoint `/api/approval/{task_id}` sets the decision and unblocks the event. In demo mode, auto-approve is enabled.

### 11. SSE streaming format
API sends `ProgressEvent` objects as SSE `data:` lines. Frontend processes them by type:
- `component` + `step_start`: show step name in progress UI
- `thinking_chunk`: append to thinking panel
- `step_done`: finalize step with token counts
- `status=complete`: show result
- `status=failed`: show error

### 12. Token tracker records per-call metrics
Every LLM call records: caller, latency, TTFT, ITL, input/output tokens, TPS. Access via `tracker.to_metrics_dict()`. Hardware stats aggregated by `tracker.get_hw_summary()`.

### 13. Bounded execution — always enforce limits
- Agent node loops: max 15 iterations
- Supervisor rounds: max 5 reflection cycles
- Sub-agents per task: max 4
- Context tokens per retrieval: max 8192
Never remove these limits without explicit approval.

### 14. Model name must match exactly
Use the full HuggingFace model ID: `meta-llama/Llama-3.1-8B-Instruct`, `Qwen/Qwen2.5-3B-Instruct`. These must match what vLLM was started with.

### 15. vLLM on XPU requires tp=8 and enforce-eager
- `tp=1` → only ~4.5 GiB KV-cache → OOM at 131K context
- `eager=false` → `UR_RESULT_ERROR_OUT_OF_DEVICE_MEMORY`
- Always use `tp=8 --enforce-eager --enable-prefix-caching`

### 16. Structured output via instructor
`chat_structured()` uses the `instructor` library with `mode=instructor.Mode.JSON`. This produces structured JSON matching Pydantic models. Do not use `tool_calling` mode — it's unreliable with vLLM.

### 17. Never commit secrets
`.env` is gitignored. API keys, tokens, passwords go ONLY in `.env`. If referencing in docs, use placeholders: `API_KEY=<your-key>`.

### 18. Graph construction: shared prefix + scenario middle + shared suffix
Both IT Ops and Deep Research graphs share:
- Prefix: ingest → authenticate → classify → retrieve → route
- Suffix: policy_check → format_response → persist_audit
The scenario-specific middle is composed via conditional edges from the route node.

### 19. Adding a new scenario
1. Create `graphs/new_scenario/{graph,nodes,prompts}.py`
2. Add to `models.Scenario` enum
3. Register in route conditional edges (in the graph that adds them)
4. Add mock connectors if needed for demo

### 20. Adding a new connector
1. Subclass `connectors.base.BaseConnector`
2. Implement `search()`, `get()`, optionally `execute_action()`
3. Register in `tool_proxy.CONNECTOR_REGISTRY`
4. Set `is_read_only = True` unless write is needed

### 21. Test naming convention
`tests/test_{module}.py` → test functions `test_{behavior}_{condition}`. Use `pytest-asyncio` for async tests.

### 22. After any correction, update this file
Add a numbered rule documenting what went wrong and the correct approach. This file is the single source of truth for future sessions.
