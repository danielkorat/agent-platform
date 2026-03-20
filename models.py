"""Pydantic models for API requests, responses, and SSE events."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────

class Scenario(str, Enum):
    IT_OPS = "it_ops"
    DEEP_RESEARCH = "deep_research"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETE = "complete"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplexityLevel(str, Enum):
    FAST = "fast"
    MEDIUM = "medium"
    DEEP = "deep"


# ── API Models ───────────────────────────────────────────────

class TaskRequest(BaseModel):
    """Incoming task request from a user."""
    query: str = Field(..., min_length=1, max_length=10000)
    scenario: Scenario = Scenario.IT_OPS
    tenant_id: str = "default"
    user_id: str = "anonymous"
    context: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """Response after task submission."""
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskResult(BaseModel):
    """Final result of a completed task."""
    task_id: str
    status: TaskStatus
    scenario: Scenario
    execution_path: str = ""
    final_output: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    approval_required: bool = False
    approval_status: str = "not_required"
    metrics: TaskMetrics | None = None
    errors: list[str] = Field(default_factory=list)


class TaskMetrics(BaseModel):
    """Observability metrics for a task execution."""
    elapsed_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    retrieval_calls: int = 0
    tool_calls: int = 0
    execution_path: str = ""
    model_endpoints_used: list[str] = Field(default_factory=list)
    latency_breakdown: dict[str, float] = Field(default_factory=dict)
    tokens_saved_by_reranking: int = 0
    cache_hit: bool = False
    hw_utilization: dict[str, Any] = Field(default_factory=dict)


# ── SSE Progress Events ─────────────────────────────────────

class ProgressEvent(BaseModel):
    """Server-sent event for real-time task progress."""
    task_id: str
    status: TaskStatus = TaskStatus.RUNNING
    message: str = ""
    detail: str = ""
    progress_pct: float = 0.0

    # Component info
    component: str = ""
    hardware: str = ""
    model_name: str = ""
    tps: float = 0.0

    # Streaming tokens
    thinking_chunk: str = ""

    # Step tracking
    step_start: bool = False
    step_done: bool = False
    step_input_tokens: int = 0
    step_output_tokens: int = 0
    step_hardware: str = ""
    step_model: str = ""
    panel_verb: str = ""
    panel_detail: str = ""

    # Final summary
    hw_summary: dict[str, Any] = Field(default_factory=dict)
    metrics: TaskMetrics | None = None


# ── Structured Output Schemas ────────────────────────────────

class ClassificationResult(BaseModel):
    """Output of the complexity/scenario classifier."""
    scenario: Scenario
    complexity: ComplexityLevel
    risk: RiskLevel
    reasoning: str = ""


class RetrievalPlan(BaseModel):
    """Plan for retrieval strategy."""
    queries: list[str]
    sources: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    expected_depth: int = 1


class ResearchBrief(BaseModel):
    """High-level research brief before sub-task decomposition."""
    objective: str
    scope: str
    key_questions: list[str]
    expected_sources: list[str] = Field(default_factory=list)


class SubTask(BaseModel):
    """A research sub-task for a sub-agent."""
    id: str
    topic: str
    queries: list[str]
    instructions: str = ""


class SubFinding(BaseModel):
    """Cleaned finding from a research sub-agent."""
    sub_task_id: str
    summary: str
    key_facts: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    gaps: list[str] = Field(default_factory=list)


class IncidentSummary(BaseModel):
    """Structured output for IT Ops incident analysis."""
    incident_summary: str
    suspected_causes: list[str] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    approval_required: bool = False
    draft_closure_note: str = ""


class ResearchReport(BaseModel):
    """Structured output for Deep Research scenario."""
    research_brief: str = ""
    executive_answer: str = ""
    findings: list[dict[str, Any]] = Field(default_factory=list)
    gaps_and_unknowns: list[str] = Field(default_factory=list)
    recommendation: str = ""
    citations: list[str] = Field(default_factory=list)


# ── Approval Models ──────────────────────────────────────────

class ApprovalRequest(BaseModel):
    """Request for human approval."""
    task_id: str
    action_description: str
    risk_level: RiskLevel
    supporting_evidence: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    """Human decision on an approval request."""
    task_id: str
    approved: bool
    reviewer_id: str = ""
    comment: str = ""


# ── Audit Record ─────────────────────────────────────────────

class AuditRecord(BaseModel):
    """Immutable audit record for every task execution."""
    task_id: str
    tenant_id: str
    user_id: str
    scenario: str
    query: str
    execution_path: str = ""
    model_endpoints_used: list[str] = Field(default_factory=list)
    retrieved_source_ids: list[str] = Field(default_factory=list)
    reranked_source_ids: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    approval_required: bool = False
    approval_status: str = "not_required"
    final_output_hash: str = ""
    latency_breakdown_ms: dict[str, float] = Field(default_factory=dict)
    token_usage: dict[str, int] = Field(default_factory=dict)
    safety_flags: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
