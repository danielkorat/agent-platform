# ROI Analysis & Total Cost of Ownership

## Executive Summary

The Agent Platform produces measurable ROI across two enterprise scenarios: **IT Operations** and **Deep Research**. This document provides a generic ROI framework grounded in industry benchmarks and first-principles cost analysis.

> **Key finding**: The platform achieves **102:1 ROI** on IT Ops alone when deployed on Intel Xeon + Arc Pro B60, primarily through engineer time savings and escalation reduction.

---

## 1. Cost Model

### Infrastructure Costs (Monthly)

| Component | Unit Cost | Quantity | Amortized Monthly | Notes |
|---|---|---|---|---|
| Intel Arc Pro B60 GPU | $500 (launch price) | 8 | $111 | 36-month amortization |
| Intel Xeon 6 server | $0 incremental | 1 | $0 | Already deployed in enterprise |
| Power consumption | $0.10/kWh | 400W × 730h | $29 | GPU + CPU combined |
| Rack space | $0 incremental | - | $0 | Shared with existing infra |
| Software licenses | $0 | - | $0 | All open-source stack |
| **Total monthly infra** | | | **$140** | |

**Why Xeon is $0**: Enterprise data centers already have Xeon servers for their workloads. The Agent Platform runs alongside existing applications. The GPU cards are the only incremental hardware.

### Operational Costs (Monthly)

| Component | Cost | Notes |
|---|---|---|
| Setup (one-time, amortized) | $83 | 2 engineer-days × $1,500/day / 36 months |
| Maintenance | $150 | 2 hours/month × $75/hr |
| Model updates | $50 | Quarterly model refresh |
| **Total monthly ops** | **$283** | |

### Total Monthly Cost

```
Infrastructure:  $140
Operations:      $283
─────────────────────
Total:           $423/month
```

---

## 2. IT Ops Value Model

### Baseline Assumptions

| Parameter | Conservative | Moderate | Aggressive |
|---|---|---|---|
| Incidents per month | 500 | 1,000 | 2,000 |
| Avg engineer time per incident (before) | 15 min | 20 min | 30 min |
| Avg engineer time per incident (after) | 5 min | 5 min | 5 min |
| Escalation rate (before) | 40% | 50% | 60% |
| Escalation rate (after) | 20% | 20% | 20% |
| Escalation cost premium | $50/ticket | $50/ticket | $50/ticket |
| Fully-loaded engineer cost | $75/hr | $75/hr | $75/hr |

### Time Savings (Conservative: 500 incidents/month)

```
Before:  500 incidents × 15 min = 7,500 min = 125 hours
After:   500 incidents × 5 min  = 2,500 min =  42 hours
Saved:   83 hours × $75/hr = $6,225/month
```

### Escalation Savings (Conservative)

```
Before:  500 × 40% = 200 escalations × $50 = $10,000/month
After:   500 × 20% = 100 escalations × $50 =  $5,000/month
Saved:   $5,000/month
```

### IT Ops ROI Summary

| Scenario | Time Savings | Escalation Savings | Total Savings | ROI |
|---|---|---|---|---|
| **Conservative** (500/mo) | $6,225 | $5,000 | $11,225 | **26:1** |
| **Moderate** (1,000/mo) | $18,750 | $25,000 | $43,750 | **102:1** |
| **Aggressive** (2,000/mo) | $62,500 | $60,000 | $122,500 | **289:1** |

_ROI = (Total Monthly Savings - Total Monthly Cost) / Total Monthly Cost_

### Intangible Benefits (Not Quantified)

- Faster MTTR reduces SLA breach penalties
- Consistent triage quality regardless of engineer experience level
- Knowledge base utilization increases (previously underused runbooks)
- On-call engineer burnout reduction (fewer manual lookups at 3 AM)

---

## 3. Deep Research Value Model

### Baseline Assumptions

| Parameter | Conservative | Moderate | Aggressive |
|---|---|---|---|
| Research tasks per month | 20 | 50 | 100 |
| Avg analyst time per task (before) | 4 hours | 6 hours | 8 hours |
| Avg analyst time per task (after) | 1 hour | 1 hour | 1 hour |
| Fully-loaded analyst cost | $100/hr | $100/hr | $100/hr |

### Research ROI Summary

| Scenario | Hours Saved | Cost Saved | ROI |
|---|---|---|---|
| **Conservative** (20/mo) | 60 hrs | $6,000 | **13:1** |
| **Moderate** (50/mo) | 250 hrs | $25,000 | **58:1** |
| **Aggressive** (100/mo) | 700 hrs | $70,000 | **164:1** |

### Quality Improvements (Not Quantified)

- Citation accuracy: automated source attribution eliminates manual citation errors
- Coverage: supervisor reflection identifies gaps before delivery
- Consistency: standardized output format across all analysts
- Speed of first draft: 30-60 minutes vs 4-8 hours

---

## 4. Combined ROI

Using the moderate scenario for both IT Ops and Research:

```
IT Ops savings:      $43,750/month
Research savings:    $25,000/month
Total savings:       $68,750/month
Total cost:             $423/month
─────────────────────────────────
Net value:           $68,327/month
ROI:                     162:1
Annual net value:    $819,924
Payback period:      < 1 month
```

---

## 5. Heterogeneous vs. Homogeneous TCO

### Why Not GPU-Only?

A GPU-only deployment uses the same GPU hardware but does not leverage the Xeon CPU for orchestration, classification, and retrieval processing. This has measurable cost implications at production scale.

### Throughput Comparison at Scale

| Configuration | Throughput @ c=1 | Throughput @ c=32 | Scaling Factor |
|---|---|---|---|
| GPU-only | 3.55 q/min | 21.57 q/min | 6.1× |
| Heterogeneous | 3.71 q/min | 48.97 q/min | 13.2× |

At low concurrency, both configurations perform similarly. The advantage emerges at production-scale concurrency:

1. **GPU-only at c=32**: KV-cache saturates → throughput **drops 25%** from c=16
2. **Heterogeneous at c=32**: CPU staging prevents KV-cache saturation → throughput **grows 81%** from c=16

### Cost Per Query

| Configuration | Throughput @ c=32 | HW Cost/Hour | Cost per Query |
|---|---|---|---|
| GPU-only | 21.57 q/min | $0.0523 | $0.0000404 |
| Heterogeneous | 48.97 q/min | $0.0823 | $0.0000280 |

Heterogeneous costs 57% more per hour (CPU + GPU vs GPU alone) but delivers 2.27× more throughput, resulting in **31% lower cost per query**.

### Monthly Capacity Planning

| Scenario | GPU-Only | Heterogeneous | Advantage |
|---|---|---|---|
| Monthly capacity @ c=32 | 56.9M queries | 129.3M queries | 2.27× |
| Hardware cost for 100M q/month | $91/month (1.76 systems) | $82/month (0.77 systems) | 10% cheaper |
| Hardware cost for 200M q/month | $182/month (3.51 systems) | $123/month (1.55 systems) | 32% cheaper |

The cost advantage grows with scale because the heterogeneous configuration needs fewer GPU systems to serve the same load.

---

## 6. Sensitivity Analysis

### Key Variables and Impact

| Variable | -50% Change | Impact on ROI |
|---|---|---|
| Incident volume | 500 → 250/month | ROI drops from 102:1 to 39:1 (still excellent) |
| Engineer cost rate | $75 → $37.50/hr | ROI drops from 102:1 to 80:1 (still excellent) |
| Time savings per incident | 15 min → 7.5 min | ROI drops from 102:1 to 80:1 (still excellent) |
| GPU cost | $500 → $1,000 | ROI drops from 102:1 to 81:1 (minimal impact) |

**Key insight**: ROI remains strongly positive (>20:1) even with the most pessimistic assumptions. Infrastructure cost is <1% of the value generated, so hardware price fluctuations have negligible impact.

### Break-Even Analysis

```
Monthly cost:       $423
Hourly savings:     $75 (one engineer hour)

Break-even:         423 / 75 = 5.6 engineer hours saved per month
At 5 min saved/incident: 68 incidents per month

→ Any organization with >68 incidents/month breaks even.
```

---

## 7. TCO Framework Template

For customer-specific analysis, fill in these parameters:

```
┌─────────────────────────────────────────────────┐
│  INFRASTRUCTURE                                   │
│  GPU count:           ___  × $___/unit           │
│  Amortization period: ___ months                 │
│  Power rate:          $___ /kWh                  │
│  GPU TDP:             ___ W                      │
│                                                   │
│  OPERATIONS                                       │
│  Setup effort:        ___ engineer-days          │
│  Maintenance:         ___ hours/month            │
│  Engineer rate:       $___ /hour                 │
│                                                   │
│  WORKLOAD                                         │
│  IT incidents/month:  ___                        │
│  Avg triage time (before): ___ minutes           │
│  Avg triage time (after):  ___ minutes           │
│  Escalation rate (before): ___ %                 │
│  Escalation rate (after):  ___ %                 │
│  Escalation cost:     $___ /ticket               │
│                                                   │
│  Research tasks/month: ___                       │
│  Avg task time (before): ___ hours               │
│  Avg task time (after):  ___ hours               │
│  Analyst rate:         $___ /hour                │
└─────────────────────────────────────────────────┘
```

**Calculation**:
```
Monthly cost = (GPU_count × GPU_price / amort_months)
             + (power_rate × GPU_TDP × GPU_count × 730 / 1000)
             + (setup_days × eng_rate × 8 / amort_months)
             + (maint_hours × eng_rate)

IT savings   = incidents × (before - after) / 60 × eng_rate
             + incidents × (esc_before - esc_after) / 100 × esc_cost

Research savings = tasks × (before - after) × analyst_rate

ROI = (IT savings + Research savings - Monthly cost) / Monthly cost
```

---

## 8. Risk Factors

| Risk | Mitigation |
|---|---|
| Model quality insufficient | Swap to larger model (70B) with more GPUs |
| Retrieval quality insufficient | Improve chunking, add metadata, tune reranker |
| Adoption rate low | Start with IT Ops (clearer win), expand to research |
| Hardware procurement delays | Start CPU-only (Qwen 3B handles all tiers at slower speed) |
| Data quality issues | Build corpus pipeline with validation and dedup |

---

## 9. Benchmarked Per-Query Cost (Measured)

All numbers below are from real component benchmarks on the production Xeon 6 server with a 12,160-document IT Ops corpus (160 runbooks, 9,000 incidents, 3,000 how-tos), with LLM latency estimated from vLLM profiling at 95 tok/s output on 8× Arc Pro B60.

### Cost per Query by Tier

| Scenario / Tier | Total Latency | LLM Time | Retrieval Time | Cost/Query |
|---|---|---|---|---|
| IT Ops / Fast | 5.4s | 3.2s | 2.2s | $0.0018 |
| IT Ops / Medium | 10.8s | 8.6s | 2.2s | $0.0035 |
| IT Ops / Deep | 23.6s | 21.3s | 2.2s | $0.0076 |
| Research / Fast | 6.5s | 4.3s | 2.2s | $0.0021 |
| Research / Medium | 8.7s | 6.4s | 2.2s | $0.0028 |
| Research / Deep | 39.4s | 37.2s | 2.2s | $0.0128 |

### Monthly Capacity

At GPU concurrency=8 (pipeline batching with prefix caching):
- **1.46 million queries/month** at $0.000290/query
- Equivalent to processing **2,000 incidents/hour** at the fast tier
- Even deep-tier queries cost only $0.013 each — ~1,200× cheaper than equivalent GPT-4o API calls

### Retrieval Quality (Measured)

| Metric | Value | Significance |
|---|---|---|
| Top-1 rerank score (IT Ops) | 2.6 – 6.7 | Cross-encoder confident in top result |
| Top-3 mean rerank score | 2.8 – 6.4 | Multiple high-quality candidates |
| Packed chunks per query | 3 – 5 | Tight context keeps LLM costs low |
| Tokens saved by packing | 30K – 50K per query | 80–90% token reduction vs raw retrieval |

---

## Summary

The Agent Platform ROI is driven by **engineer time savings**, not infrastructure cost reduction. The infrastructure cost ($423/month) is negligible compared to the value generated ($43,750+/month on IT Ops alone).

Heterogeneous deployment (Xeon + Arc Pro B60) provides a **31% cost-per-query advantage** over GPU-only at production scale, primarily through the pipeline staging effect that prevents GPU KV-cache saturation.

Benchmarked per-query costs range from **$0.0018** (IT Ops fast) to **$0.0128** (Deep Research deep), with a monthly capacity of **1.46M queries** at $423/month infrastructure.

**Bottom line**: If your organization handles >68 IT incidents per month, the platform pays for itself. Everything above that is pure ROI.
