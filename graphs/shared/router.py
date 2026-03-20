"""Complexity and scenario router.

Three-level complexity routing:
- Fast: retrieval + 1-pass generation
- Medium: single-agent bounded tool loop
- Deep: supervisor + parallel sub-agents

Routing uses rules first, LLM classification second.
"""

from __future__ import annotations

import re
from typing import Any

from models import ClassificationResult, ComplexityLevel, RiskLevel, Scenario
from llm.client import get_llm
from token_tracker import TokenTracker


# ── Rule-based heuristics ────────────────────────────────────

_DEEP_PATTERNS = [
    re.compile(r"\b(compare|contrast|versus|vs\.?)\b", re.IGNORECASE),
    re.compile(r"\b(investigate|analyze|evaluate|assess)\b", re.IGNORECASE),
    re.compile(r"\b(comprehensive|thorough|detailed|in-depth)\b", re.IGNORECASE),
    re.compile(r"\b(multi-|cross-|inter-)\w+", re.IGNORECASE),
    re.compile(r"\b(pros?\s+and\s+cons?|tradeoffs?|trade-offs?)\b", re.IGNORECASE),
    re.compile(r"\b(research|memo|report|brief|whitepaper)\b", re.IGNORECASE),
]

_MEDIUM_PATTERNS = [
    re.compile(r"\b(how\s+to|troubleshoot|diagnose|fix|resolve|debug)\b", re.IGNORECASE),
    re.compile(r"\b(incident|ticket|alert|outage|error)\b", re.IGNORECASE),
    re.compile(r"\b(runbook|playbook|procedure|workflow)\b", re.IGNORECASE),
    re.compile(r"\b(root\s*cause|remediat|mitigat)\b", re.IGNORECASE),
]

_ACTION_PATTERNS = [
    re.compile(r"\b(restart|reboot|deploy|execute|run|apply|patch)\b", re.IGNORECASE),
    re.compile(r"\b(create|update|delete|modify|change)\b", re.IGNORECASE),
    re.compile(r"\b(escalate|approve|rollback|revert)\b", re.IGNORECASE),
]


def _count_entities(query: str) -> int:
    """Rough estimate of distinct entities in the query."""
    # Count capitalized words (excluding sentence starts) as entity proxies
    words = query.split()
    entities = sum(1 for i, w in enumerate(words) if i > 0 and w[0].isupper())
    return max(entities, 1)


def classify_by_rules(query: str) -> dict[str, Any]:
    """Rule-based classification heuristics.

    Returns partial classification with confidence.
    """
    query_len = len(query.split())
    entity_count = _count_entities(query)
    deep_signals = sum(1 for p in _DEEP_PATTERNS if p.search(query))
    medium_signals = sum(1 for p in _MEDIUM_PATTERNS if p.search(query))
    action_signals = sum(1 for p in _ACTION_PATTERNS if p.search(query))

    # Complexity estimation
    if deep_signals >= 2 or (query_len > 30 and entity_count > 3):
        complexity = "deep"
    elif medium_signals >= 1 or action_signals >= 1 or query_len > 15:
        complexity = "medium"
    else:
        complexity = "fast"

    # Scenario estimation
    if medium_signals >= 1 or action_signals >= 1:
        scenario = "it_ops"
    elif deep_signals >= 1:
        scenario = "deep_research"
    else:
        scenario = "it_ops"  # default

    # Risk estimation
    if action_signals >= 2:
        risk = "high"
    elif action_signals >= 1:
        risk = "medium"
    else:
        risk = "low"

    confidence = min(1.0, (deep_signals + medium_signals + action_signals) * 0.2 + 0.3)

    return {
        "complexity": complexity,
        "scenario": scenario,
        "risk": risk,
        "confidence": confidence,
        "signals": {
            "deep": deep_signals,
            "medium": medium_signals,
            "action": action_signals,
            "query_len": query_len,
            "entities": entity_count,
        },
    }


# ── LLM-assisted classification ─────────────────────────────

_CLASSIFY_PROMPT = """\
You are an enterprise task router. Classify the following user request.

Determine:
1. **scenario**: "it_ops" (service desk, incident, troubleshooting, infrastructure) or "deep_research" (analysis, comparison, investigation, memo generation)
2. **complexity**: "fast" (simple lookup/FAQ), "medium" (bounded investigation, few steps), or "deep" (multi-source research, comparison, long-form output)
3. **risk**: "low" (read-only), "medium" (may need data access), "high" (requires write/execute actions), "critical" (production-affecting actions)

User request: {query}

Respond in JSON format with fields: scenario, complexity, risk, reasoning.
"""


async def classify_with_llm(
    query: str,
    tracker: TokenTracker | None = None,
) -> ClassificationResult:
    """Use the SLM to classify a query."""
    llm = get_llm(caller="classify", secondary=True, tracker=tracker)
    result = await llm.chat_structured(
        response_model=ClassificationResult,
        messages=[
            {"role": "system", "content": "You are an enterprise task classifier."},
            {"role": "user", "content": _CLASSIFY_PROMPT.format(query=query)},
        ],
        caller="classify",
        temperature=0.0,
        max_tokens=256,
    )
    return result


async def classify_query(
    query: str,
    scenario_override: str | None = None,
    tracker: TokenTracker | None = None,
) -> ClassificationResult:
    """Full classification pipeline: rules first, LLM refinement second.

    Args:
        query: User query to classify.
        scenario_override: If set, forces scenario (skips detection).
        tracker: Token tracker for metrics.

    Returns:
        ClassificationResult with scenario, complexity, risk, reasoning.
    """
    # Step 1: Rule-based heuristics
    rules = classify_by_rules(query)

    # Step 2: If rules are confident enough, skip LLM
    if rules["confidence"] >= 0.7:
        return ClassificationResult(
            scenario=Scenario(scenario_override or rules["scenario"]),
            complexity=ComplexityLevel(rules["complexity"]),
            risk=RiskLevel(rules["risk"]),
            reasoning=f"Rule-based: {rules['signals']}",
        )

    # Step 3: LLM-assisted classification
    try:
        llm_result = await classify_with_llm(query, tracker=tracker)
        # Override scenario if forced
        if scenario_override:
            llm_result.scenario = Scenario(scenario_override)
        return llm_result
    except Exception:
        # Fallback to rules
        return ClassificationResult(
            scenario=Scenario(scenario_override or rules["scenario"]),
            complexity=ComplexityLevel(rules["complexity"]),
            risk=RiskLevel(rules["risk"]),
            reasoning=f"LLM fallback to rules: {rules['signals']}",
        )
