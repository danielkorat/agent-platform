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
│   ├── vector_store.py           # FAISS IndexHNSWFlat / IndexFlatIP (auto-selected by corpus size)
│   ├── lexical_store.py          # BM25 via rank_bm25
│   ├── embeddings.py             # BGE-small-en-v1.5 (384-dim)
│   ├── fusion.py                 # Reciprocal Rank Fusion (k=60)
│   ├── reranker.py               # Cross-encoder reranker: torch + ONNX backends, GPU-optional
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
│   ├── build_demo_index.py       # FAISS + BM25 index builder from mock data
│   └── build_large_scale_index.py # 12K IT Ops corpus generator + index builder
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
│   ├── benchmark.py              # E2E API benchmark (requires running server)
│   └── bench_components.py       # Component-level benchmarks (offline, no server needed)
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

`reranker.py` supports three backends/approaches:
- **Pre-truncation** (`RERANK_MAX_CANDIDATES`, default 20): Only score top-N candidates from RRF, not all 50+. Linear latency reduction.
- **ONNX Runtime** (`RERANK_BACKEND=onnx`): Auto-exports model to `data/onnx_reranker/`, uses ORT with full graph optimization. Outperforms Torch at C≥4.
- **GPU offload** (`RERANK_DEVICE=cuda|xpu`): Optional path for environments with a **dedicated** GPU. **Do NOT use on this deployment** — all 8 Arc Pro B60s are fully committed to vLLM at tp=8. Adding the reranker there risks OOM and LLM latency spikes. ONNX/10 already exceeds retrieval throughput needs (19.3 q/s vs ~2k q/s capacity need).

Benchmarked (Xeon 6, 12K corpus, 10 queries):
- Torch/50 baseline: 1,653ms (C=1) → 1.1 q/s (C=32)
- Torch/20 (default): 563ms (C=1) → 3.1 q/s (C=64), **2.5–2.9× speedup**
- ONNX/10 (fastest CPU): 216ms (C=1) → 19.3 q/s (C=64), **7.7–16.8× speedup**
- Top-1 ranking identical across all configs

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

### 23. Docs HTML file must stay in sync with docs/
`docs/index.html` is a single-file combined view of all docs (architecture.md, marketing.md, roi.md).
**Rule**: Whenever any file under `docs/*.md` is added, removed, or edited, the corresponding section in `docs/index.html` must be updated in the same change. Never let the HTML fall out of sync with the source markdown files.

### 25. docs/index.html: always use visual HTML/CSS/SVG diagrams — no ASCII art
When rendering architecture diagrams, flowcharts, pipeline stages, hardware layouts, financial summaries, or any other visual in `docs/index.html`, always use proper HTML/CSS (styled divs, flex/grid layouts, cards) or inline SVG. **Never use `<pre>` blocks with box-drawing characters (┌ │ └ ─ etc.) or ASCII art for diagrams.** Code blocks (`<pre>`) are only acceptable for actual source code (Python, shell, etc.). Replace any ASCII art discovered during edits with an appropriate visual component.

### 24. FAISS index strategy: HNSW not sharding
Benchmarked on Xeon 6730P (128-core), 623K × 384d vectors:
- `IndexFlatIP`: 72.5 ms p50 (exact, 100% recall)
- `IndexHNSWFlat` M=32, ef=64: 0.25 ms p50 (98% recall@20) → **290× faster**
- `IndexShards`: no improvement — FAISS already uses all threads via OpenMP internally; merging adds overhead

Rules:
- Use `IndexFlatIP` below `hnsw_min_vectors` (default 10K) for exact search on small corpora
- Use a **single** `IndexHNSWFlat` above that threshold — do NOT use `IndexShards`
- M=32, efConstruction=200, efSearch=64 is the production sweet spot (98% recall, sub-ms)
- 98% recall@20 has negligible downstream impact after cross-encoder reranking
- Memory overhead: ~17% vs FlatIP (acceptable)
- Always call `faiss.omp_set_num_threads(n_cpu)` before build/search for FlatIP parallelism

### 25. Large-scale corpus: build_large_scale_index.py
The demo corpus is 12,160 IT Ops documents (160 runbooks, 9,000 incidents, 3,000 how-tos), generated procedurally from template problems × systems. Fully deterministic from `seed=42`. No LLM or external data involved.
To rebuild: `HF_HUB_OFFLINE=1 python3 -m connectors.build_large_scale_index`

### 26. Benchmark harness: evals/bench_components.py
Component-level benchmarks measuring FAISS, BM25, reranker, full retrieval pipeline, router, and simulated E2E at concurrency 1/4/16/32/64.
To run: `HF_HUB_OFFLINE=1 python3 -m evals.bench_components --concurrency 1,4,16,32,64`
Key findings (Xeon 6, 12K corpus):
- FAISS HNSW: 18ms p50 @ C=1, 51ms p50 @ C=64
- BM25: 31ms p50 @ C=1
- Cross-encoder reranker: 563ms p50 torch/20 (was 1,653ms @ 50 cands), 216ms ONNX/10
- Full retrieval pipeline: 2,244ms p50 @ C=1, peaks at 18.8 q/s @ C=16
- Router rules: 0.022ms p50, 100% rule coverage on eval set
- E2E fast tier: 5.4s, deep tier: 23.6–39.4s
- Monthly capacity at GPU C=8: 1.46M queries, $0.00035/query

### 27. ONNX export requires `attn_implementation="eager"`
PyTorch 2.10+ defaults to SDPA attention which traces poorly to ONNX (5× regression).
Always export with `attn_implementation="eager"` and `dynamo=False`.
The exported model lives at `data/onnx_reranker/model.onnx` and is auto-generated on first use.
Dependencies: `onnx`, `onnxruntime` (both already installed).

### 28. Deep Research scenario benchmarks: evals/bench_deep_research.py
Dedicated benchmark measuring retrieval quality + speed per Deep Research tier (fast/medium/deep).
To run: `HF_HUB_OFFLINE=1 python3 -m evals.bench_deep_research`
Key findings (Xeon 6, 12K corpus):
- Fast tier: 556ms retrieval, 4.8s E2E modelled (88% LLM), top-1 score -10.42
- Medium tier: 508ms retrieval, 10.1s E2E modelled (95% LLM), top-1 score -9.55
- Deep tier: 710ms retrieval (initial) + 6.1s sub-agent retrieval (12 calls), 45.0s E2E modelled, top-1 score -7.79
- Cross-tier: top-1 scores identical for same query across tiers; deep tier packs 40% more context chunks
- Sub-agent dedup ratio: 11% mean — supervisor decomposition produces genuinely independent subtopics
- Deep tier retrieval share: 15% of E2E (vs 85% LLM); main optimization path is LLM decode speed
