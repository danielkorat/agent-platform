"""IT Ops prompt templates."""

# ── Entity extraction ────────────────────────────────────────

EXTRACT_ENTITIES_SYSTEM = """\
You are an IT operations specialist. Extract structured entities from the incident description."""

EXTRACT_ENTITIES_USER = """\
Incident description:
{query}

Extract the following entities in JSON format:
- affected_systems: list of systems/services mentioned
- error_codes: any error codes or status codes
- timestamps: any mentioned times/dates
- severity_indicators: words indicating urgency
- affected_users: count or list of affected users
- environment: production/staging/dev if mentioned"""

# ── Root cause analysis ──────────────────────────────────────

ROOT_CAUSE_SYSTEM = """\
You are an expert IT incident analyst. Analyze the incident using the provided context \
from knowledge base articles, runbooks, and similar past incidents."""

ROOT_CAUSE_USER = """\
Incident:
{query}

Extracted entities:
{entities}

Relevant knowledge base context:
{context}

Based on this information:
1. Provide a concise incident summary (2-3 sentences).
2. List 1-3 most likely root causes, ordered by probability.
3. For each root cause, cite the supporting evidence from [Source N].
4. Note any information gaps that would help narrow the diagnosis."""

# ── Remediation actions ──────────────────────────────────────

REMEDIATION_SYSTEM = """\
You are an IT operations advisor. Recommend specific remediation actions \
based on the root cause analysis and available runbooks."""

REMEDIATION_USER = """\
Incident summary:
{summary}

Root cause hypotheses:
{hypotheses}

Available runbooks context:
{context}

For each recommended action:
1. Describe the action clearly.
2. Indicate risk level (low/medium/high).
3. Whether it requires approval.
4. Expected impact.
5. Cite the relevant runbook [Source N] if applicable.

Format as a numbered list of actions."""

# ── Closure note ─────────────────────────────────────────────

CLOSURE_NOTE_SYSTEM = """\
You are writing an incident closure note for the ticketing system."""

CLOSURE_NOTE_USER = """\
Incident: {query}
Summary: {summary}
Root cause: {root_cause}
Actions taken: {actions}

Write a concise, professional closure note suitable for the ticketing system. \
Include: what happened, why, what was done, and any follow-up items."""
