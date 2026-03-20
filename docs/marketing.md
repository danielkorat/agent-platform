# Marketing Strategy

## Positioning Statement

**"Enterprise AI that works with your infrastructure, not against it."**

The Agent Platform positions Intel Xeon + Arc Pro B60 as the **complete on-premises AI inference stack** — not just model serving, but full enterprise workflow automation with security, observability, and cost control built in.

---

## 1. Target Segments

### Primary: Large Enterprise IT Operations

**Profile**: 500+ employees, 1,000+ IT incidents/month, existing Xeon infrastructure, compliance requirements that discourage cloud AI.

**Pain points**:
- Ticket triage is manual, slow, and inconsistent
- Runbooks exist but aren't used (too many, hard to search)
- MTTR is measured in hours, not minutes
- On-call engineers burn out from repetitive L1 work

**Message**: "Transform your incident response from hours to seconds. Same hardware. Same data center. Full control."

### Secondary: Research & Strategy Teams

**Profile**: Financial services, consulting, legal, intelligence — teams that produce written analysis from multiple sources under time pressure.

**Pain points**:
- Research memos take days when the decision needs to happen today
- Citation tracking is manual and error-prone
- Quality varies by analyst experience and available time
- No systematic coverage assessment

**Message**: "4-8× faster research with full citation. Let your analysts do analysis, not information retrieval."

### Tertiary: Intel Partners & Systems Integrators

**Profile**: OEMs, VARs, and consulting firms selling Intel-based solutions to enterprise clients.

**Pain points**:
- Need concrete use cases to sell Xeon + Arc Pro together
- Need proof points beyond model benchmarks (MMLU, etc.)
- Need demo-ready solutions for customer PoCs

**Message**: "A turnkey enterprise AI demo that sells Intel hardware. 15-minute setup. Real metrics. Customer PoC in a week."

---

## 2. Key Messages

### Message 1: On-Premises and Secure

> "Your data never leaves your data center. No API keys to cloud providers. No per-token bills. No data sovereignty concerns."

This matters because:
- Regulated industries (finance, healthcare, government) cannot send sensitive data to cloud LLM APIs
- Enterprise data often contains PII, trade secrets, or ITAR-controlled information
- Total cost is predictable: fixed hardware cost, no variable API fees

### Message 2: 138:1 ROI

> "For every dollar spent on hardware, the platform saves $138 in engineer time. Monthly."

This matters because:
- CIOs need financial justification, not just technical merit
- The ROI is driven by time savings (easy to verify), not speculative productivity gains
- Break-even at 82 incidents/month means virtually every enterprise qualifies

### Message 3: Observability Built In

> "Every query shows its execution path, retrieved sources, model used, latency breakdown, and cost. No black boxes."

This matters because:
- Enterprises won't trust AI they can't explain
- Auditors and compliance teams need traceable decision chains
- Operations teams need cost accounting per department/use case

### Message 4: Cost-Controlled Execution

> "Simple questions cost simple resources. Three execution tiers route every query to the cheapest sufficient path."

This matters because:
- Without routing, every query pays the cost of the most expensive path
- Most enterprise queries (60-80%) are simple lookups — they don't need multi-agent research
- Token waste from unnecessary context is a real cost driver

### Message 5: Heterogeneous Advantage

> "2.27× more throughput at 31% lower cost per query. Same hardware, smarter scheduling."

This matters because:
- Enterprises already have Xeon servers — the CPU side is free
- The throughput advantage only appears at production scale (c≥8), which is where it matters
- This is a measurable, reproducible hardware advantage — not a model improvement

---

## 3. Competitive Positioning

### vs. Cloud AI APIs (OpenAI, Anthropic, Google)

| Dimension | Cloud AI | Agent Platform |
|---|---|---|
| Data location | Their servers | Your data center |
| Cost model | Per-token variable | Fixed hardware cost |
| Latency | Network RTT + queue | Local, predictable |
| Customization | System prompts only | Full pipeline control |
| Observability | Limited (usage dashboard) | Full node-level tracing |
| Compliance | SOC 2, varies | You control everything |
| Air-gap capable | No | Yes |

**When to use each**: Cloud AI is better for prototyping, small-scale experimentation, and teams without infrastructure expertise. Agent Platform is better for production deployment, regulated industries, high-volume workloads, and organizations that need full data control.

### vs. GPU-Only On-Premises (NVIDIA-centric)

| Dimension | NVIDIA GPU-Only | Agent Platform (Xeon + Arc Pro) |
|---|---|---|
| Hardware cost | H100: $25,000+ per GPU | Arc Pro B60: $900 per GPU |
| Throughput @ c=32 | Higher per GPU | 2.27× with heterogeneous |
| KV-cache behavior | Same saturation issue | CPU staging prevents saturation |
| Existing infra leverage | Requires new GPU servers | Extends existing Xeon servers |
| TCO at scale | Lower per-GPU but 28× upfront | Lower entry, better per-query at scale |

**When to use each**: NVIDIA is better for large-scale training, multi-model serving, and organizations already invested in CUDA ecosystem. Agent Platform on Intel is better for inference-focused workloads, cost-sensitive deployments, and organizations leveraging existing Xeon infrastructure.

### vs. Open-Source RAG Frameworks (LlamaIndex, Haystack)

| Dimension | RAG Frameworks | Agent Platform |
|---|---|---|
| Scope | Retrieval pipeline | Full enterprise platform |
| Security | DIY | Built-in auth, RBAC, PII, approvals |
| Routing | Manual | Automatic 3-tier classification |
| Observability | Callbacks (DIY) | Full metrics dashboard |
| Deployment | Framework, not product | Docker Compose ready |

**When to use each**: RAG frameworks are better for custom pipeline construction and research projects. Agent Platform is better for production deployment with enterprise requirements (auth, audit, RBAC).

---

## 4. Demo Strategy

### 15-Minute Customer Demo

**Setup**: Docker Compose deployment with pre-built demo indexes. Works on any machine with vLLM endpoint access.

**Script**:

1. **Architecture overview** (2 min)
   - Show the platform diagram
   - Key message: "One platform, two scenarios, three execution tiers"
   - Highlight security and observability

2. **IT Ops demo** (5 min)
   - Submit: "Production DB connection pool exhausted on db-prod-01"
   - Walk through: classification → runbook retrieval → root cause → actions → approval gate
   - Highlight: execution path label, cited sources, approval gate pause

3. **Deep Research demo** (5 min)
   - Submit: "Compare dense retrieval, lexical search, and hybrid approaches for enterprise RAG"
   - Walk through: supervisor decomposition → sub-agent research → reflection → synthesis
   - Highlight: sub-topic breakdown, source diversity, cited conclusions

4. **Metrics walkthrough** (2 min)
   - Show per-query metrics: latency breakdown, token cost, hardware utilization
   - Key message: "Every query is observable and cost-accounted"

5. **TCO and next steps** (1 min)
   - Present ROI numbers for customer's incident volume
   - Offer PoC with customer's data and connectors

### PoC Playbook (Post-Demo)

1. **Week 1**: Install platform on customer hardware. Ingest 100-500 KB articles
2. **Week 2**: Connect to customer's ticket system (read-only connector)
3. **Week 3**: Run 50-100 historical incidents through the platform. Measure time savings
4. **Week 4**: Present results with customer-specific ROI numbers

---

## 5. Content Strategy

### Technical Blog Series (for engineering audiences)

1. "Building an Enterprise Agent Platform with LangGraph and vLLM"
2. "Why Hybrid Retrieval Outperforms Dense-Only for Enterprise RAG"
3. "The Pipeline Staging Effect: How CPU Classification Scales GPU Throughput 2.27×"
4. "Security Patterns for Production LLM Applications"
5. "Three Execution Tiers: Stop Overspending on Simple Queries"

### Business Case Materials (for decision-makers)

1. Two-page executive brief with ROI headline
2. Customer-fillable TCO calculator spreadsheet
3. Competitive comparison one-pager
4. Compliance and security whitepaper

### Demo Materials (for sales engineers)

1. Live demo environment (Docker Compose)
2. Pre-recorded demo video (5 min)
3. Architecture diagram (presentation-ready)
4. FAQ document for common objections

---

## 6. Pricing Guidance (for Intel Sales)

The Agent Platform is open-source (Apache 2.0). Revenue comes from hardware sales:

| Configuration | Hardware | Estimated Street Price | Target Workload |
|---|---|---|---|
| Starter | 1× Xeon + 4× Arc Pro B60 | ~$8,000 | 500 incidents/month |
| Standard | 1× Xeon + 8× Arc Pro B60 | ~$12,000 | 2,000 incidents/month |
| Enterprise | 2× Xeon + 16× Arc Pro B60 | ~$22,000 | 10,000 incidents/month |

**Attach rate target**: Ship the Agent Platform as a reference design with every Arc Pro B60 server sale. "Buy the hardware, get the software. Here's the ROI proof."

---

## 7. Objection Handling

| Objection | Response |
|---|---|
| "We'll just use OpenAI / Claude" | "For prototyping, sure. For production with PII, compliance, and cost control? You need on-prem." |
| "Arc Pro B60 is too small for real work" | "8B-param models at 41 tok/s. 8 GPUs with 192GB total HBM. Benchmarked on 640 production queries." |
| "Our team doesn't have AI expertise" | "Docker Compose deployment, pre-built demos, documented architecture. Two engineer-days to production." |
| "What about model quality?" | "Llama 3.1 8B scored 4.1/5 on Claude-judged quality. Swap to 70B if you need more." |
| "We already have NVIDIA GPUs" | "This is about the Xeon you already have. The CPU staging effect works with any GPU — it's a software architecture win." |
| "Open source means no support" | "Intel provides reference design support. The platform is documented and tested. Your team owns it." |
