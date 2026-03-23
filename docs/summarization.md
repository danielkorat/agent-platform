

# Summarization Sub-Agent on Xeon: Where It Hurts vs. Helps

## Won't Reduce Latency: Serial LLM Pipelines

When summarization is **in the critical path** (output must complete before the next LLM call starts), the Xeon decode overhead exceeds GPU input-token savings.

| Scenario | Current E2E | Summarization Cost (Xeon) | GPU Savings (fewer input tokens) | Net |
|----------|-------------|--------------------------|----------------------------------|-----|
| Deep Research — compress 4 sub-findings before `supervisor_reflect` | 45s | +5–8s (4×400 tokens @ 50–120 t/s) | −0.3–0.5s (5K fewer prefill tokens) | **+4.5–7.5s worse** |
| Deep Research — compress before `generate_final_report` | 45s | +3–5s (1 summary, ~600 tokens) | −0.2s | **+3–5s worse** |
| Medium tier — compress retrieval context before synthesis | 7–10s | +3–5s | −0.1s | **+3–5s worse** |

**Root cause**: GPU prefill is fast (~5K tokens in <100ms). The bottleneck is autoregressive decode. Summarization doesn't reduce output tokens — it only trims the next node's input.

## Will Reduce Latency: Parallel / Async Pipelines

When summarization runs **off the critical path** or reduces tokens that hit a hard budget ceiling, it pays off.

| Scenario | Mechanism | Token Savings | Latency Impact |
|----------|-----------|---------------|----------------|
| **Multi-turn agent loops** (IT Ops, 5–15 iterations) | Compress conversation history between iterations; GPU sees shorter context each round | ~2K/iteration → 10–30K over full loop | **−2–8s** (shorter prefill × N iterations) |
| **Cross-session memory** | Summarize prior session findings before injecting as context | 8K→1K per session reference | **−0.5–1s** per injected session |
| **Context budget overflow** | When retrieval packs > 8192 tokens, summarize to fit budget instead of truncating | Avoids losing 30–50% of retrieved evidence | **Quality gain**, not latency — prevents blind truncation |
| **Streaming UX** | Summarize sub-findings as they arrive, display progressive summaries to user while GPU works | Zero critical-path cost (parallel) | **Perceived latency −10–20s** on deep tier |

The multi-turn agent loop case is the strongest: IT Ops `execute_actions` can run 5–15 iterations, each re-reading the full message history. At iteration 10, that's ~20K accumulated tokens. Compressing prior rounds to ~500 tokens each saves ~15K input tokens → ~1.5s prefill savings per iteration × remaining iterations.

## Alternative LLMs for CPU Summarization

| Model | Params | Xeon Decode (est. t/s) | 400-token Summary Latency | Quality | Instruction Following | Verdict |
|-------|--------|----------------------|--------------------------|---------|----------------------|---------|
| **Qwen2.5-3B-Instruct** | 3B | 50–120 | 3.3–8.0s | Good | Yes | Baseline; too slow for serial use |
| **Qwen2.5-1.5B-Instruct** | 1.5B | 100–250 | 1.6–4.0s | Decent | Yes | **Best balance** — 2× faster, retains structure |
| **Qwen2.5-0.5B-Instruct** | 0.5B | 200–500 | 0.8–2.0s | Weak | Partial | Drops key facts; unreliable compression |
| **Phi-3.5-mini-instruct** | 3.8B | 40–90 | 4.4–10.0s | Good | Yes | Slower than Qwen-3B; no advantage |
| **BART-large-cnn** | 400M | 400–800 | 0.5–1.0s | Good extractive | No | Fastest, but can't follow structured prompts |
| **Llama-3.2-1B-Instruct** | 1.2B | 120–280 | 1.4–3.3s | Decent | Yes | Competitive with Qwen-1.5B |
| **SmolLM2-1.7B-Instruct** | 1.7B | 90–220 | 1.8–4.4s | Decent | Yes | Newer; needs quality eval |

**Optimal pick**: **Qwen2.5-1.5B-Instruct** — fast enough for async summarization (1.6–4.0s), retains structured output capability, and is already in the Qwen family matching the existing secondary endpoint.

## Recommendation

- **Don't** add summarization in the Deep Research serial pipeline (supervisor reflect / final report). Net latency increase.
- **Do** consider it for multi-turn IT Ops agent loops (history compression) and context budget overflow (quality gain).
- **Do** consider it for streaming UX (parallel, off critical path).
- **Model**: Qwen2.5-1.5B-Instruct on the existing Xeon vLLM secondary endpoint. Deploy as a third model or replace the 3B for all secondary tasks (classification + extraction + summarization).

## Industry Context: Where Cloud Agents Use Summarization

Cloud agents (OpenAI, Anthropic, Google, LangChain, AutoGen, Perplexity) use summarization primarily to **fit more information into bounded context windows**, not to reduce latency. Latency reduction is a secondary benefit that only materializes when compressed content is read **repeatedly**.

| Pattern | Who | Why |
|---------|-----|-----|
| **Conversation history compression** | ChatGPT, Claude, Gemini | Multi-turn chats hit 50K+ tokens; summarize old turns into ~1K running summary to avoid truncation |
| **Tool output compression** | LangChain agents, AutoGPT, Assistants API | Tool calls return 5–50K tokens (web pages, SQL results); compress to ~500 tokens before next reasoning step |
| **Multi-agent handoff** | AutoGen, CrewAI, LangGraph | Agent A's 2K output → 300-token summary for Agent B; only helps if B re-reads it across multiple calls |
| **RAG context compression** | LlamaIndex (`TreeSummarize`), Cohere, Perplexity | Process more source documents than fit in one context window via hierarchical summarization |
| **Long-running agent memory** | MemGPT/Letta, AutoGen | Persist 50K+ investigation as 2K session summary for cross-session continuity |
| **Agentic web search** | Perplexity, Google/OpenAI Deep Research | Each fetched page (5–20K tokens) summarized to ~500 tokens; 10–30 pages would otherwise exceed any context window |

**Key takeaway**: Summarization is universally justified when raw content **exceeds the context window** or is **re-read across N iterations/calls**. For single-pass pipelines where content fits in context (our Deep Research serial path), it adds cost without benefit.