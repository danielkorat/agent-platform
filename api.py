"""FastAPI gateway — API endpoints with SSE streaming.

Endpoints:
- POST /api/task         — submit a new task
- GET  /api/task/{id}/stream — SSE stream of progress events
- GET  /api/task/{id}    — get task result
- POST /api/approval/{id} — submit approval decision
- GET  /api/approvals    — list pending approvals
- GET  /api/connectors   — list available connectors
- GET  /health           — health check
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings
from models import (
    ApprovalDecision, ProgressEvent, TaskRequest, TaskResponse,
    TaskResult, TaskStatus, TaskMetrics,
)
from token_tracker import TokenTracker
from graphs.shared.state import AgentState
from security.auth import authenticate, AuthError
from security.approvals import get_approval_gate
from connectors.tool_proxy import list_connectors
from db.session import init_db

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agent Platform",
    description="Enterprise Agent Platform — LangGraph + vLLM on Intel Xeon 6 + Arc Pro B60",
    version="0.1.0",
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory task tracking
_tasks: dict[str, dict[str, Any]] = {}
_queues: dict[str, asyncio.Queue] = {}


# ── Startup / Shutdown ───────────────────────────────────────

@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("Agent Platform API started on port %d", settings.api_port)


# ── Task submission ──────────────────────────────────────────

@app.post("/api/task", response_model=TaskResponse)
async def submit_task(request: TaskRequest, req: Request):
    """Submit a new task for processing."""
    # Authenticate
    auth_header = req.headers.get("Authorization")
    try:
        auth_ctx = authenticate(auth_header)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    task_id = str(uuid.uuid4())[:12]
    tracker = TokenTracker(task_id)

    # Create event queue for SSE
    queue: asyncio.Queue = asyncio.Queue()
    _queues[task_id] = queue

    # Store task metadata
    _tasks[task_id] = {
        "id": task_id,
        "request": request.model_dump(),
        "status": TaskStatus.PENDING,
        "auth_context": auth_ctx,
        "tracker": tracker,
        "created_at": datetime.utcnow(),
    }

    # Launch graph execution in background
    asyncio.create_task(_run_task(task_id, request, auth_ctx, tracker, queue))

    return TaskResponse(task_id=task_id, status=TaskStatus.PENDING)


async def _run_task(
    task_id: str,
    request: TaskRequest,
    auth_ctx: dict[str, Any],
    tracker: TokenTracker,
    queue: asyncio.Queue,
) -> None:
    """Execute the appropriate graph and stream progress events."""
    try:
        _tasks[task_id]["status"] = TaskStatus.RUNNING
        await queue.put(ProgressEvent(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            message="Task started",
            component="orchestrator",
            progress_pct=5.0,
        ))

        # Build initial state
        initial_state: AgentState = {
            "request_id": task_id,
            "tenant_id": request.tenant_id,
            "user_id": request.user_id,
            "scenario": request.scenario.value,
            "user_query": request.query,
            "auth_context": auth_ctx,
            "metrics": {"_tracker": tracker},
            "errors": [],
            "node_trace": [],
        }

        # Select graph
        if request.scenario.value == "it_ops":
            from graphs.it_ops.graph import get_it_ops_graph
            graph = get_it_ops_graph()
        else:
            from graphs.deep_research.graph import get_deep_research_graph
            graph = get_deep_research_graph()

        await queue.put(ProgressEvent(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            message="Classifying request...",
            component="classifier",
            hardware=get_settings().secondary_llm_hardware,
            progress_pct=10.0,
        ))

        # Execute graph
        final_state = await graph.ainvoke(initial_state)

        # Build result
        errors = final_state.get("errors", [])
        status = TaskStatus.FAILED if errors else TaskStatus.COMPLETE

        hw_summary = tracker.get_hw_summary()
        metrics = TaskMetrics(
            elapsed_s=tracker.elapsed_s,
            input_tokens=tracker.total_input_tokens,
            output_tokens=tracker.total_output_tokens,
            llm_calls=tracker.total_calls,
            execution_path=final_state.get("execution_path", ""),
            model_endpoints_used=list(hw_summary.keys()),
            latency_breakdown=tracker.get_latency_breakdown(),
            hw_utilization=hw_summary,
        )

        _tasks[task_id].update({
            "status": status,
            "final_state": final_state,
            "metrics": metrics,
        })

        await queue.put(ProgressEvent(
            task_id=task_id,
            status=status,
            message="Task complete" if status == TaskStatus.COMPLETE else "Task failed",
            progress_pct=100.0,
            hw_summary=hw_summary,
            metrics=metrics,
        ))

    except Exception as e:
        logger.exception("Task %s failed: %s", task_id, e)
        _tasks[task_id]["status"] = TaskStatus.FAILED

        await queue.put(ProgressEvent(
            task_id=task_id,
            status=TaskStatus.FAILED,
            message=f"Error: {e}",
            progress_pct=100.0,
        ))

    finally:
        await queue.put(None)  # Sentinel to end SSE stream


# ── SSE Streaming ────────────────────────────────────────────

@app.get("/api/task/{task_id}/stream")
async def stream_task(task_id: str):
    """Stream task progress events via Server-Sent Events."""
    if task_id not in _queues:
        raise HTTPException(status_code=404, detail="Task not found")

    queue = _queues[task_id]

    async def event_generator():
        while True:
            event = await queue.get()
            if event is None:
                yield f"data: {json.dumps({'status': 'done'})}\n\n"
                break
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Task result ──────────────────────────────────────────────

@app.get("/api/task/{task_id}")
async def get_task(task_id: str):
    """Get task status and result."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]
    state = task.get("final_state", {})

    return TaskResult(
        task_id=task_id,
        status=task["status"],
        scenario=task["request"]["scenario"],
        execution_path=state.get("execution_path", ""),
        final_output=state.get("final_output", ""),
        citations=state.get("citations", []),
        approval_required=state.get("approval_required", False),
        approval_status=state.get("approval_status", "not_required"),
        metrics=task.get("metrics"),
        errors=state.get("errors", []),
    )


# ── Approvals ────────────────────────────────────────────────

@app.get("/api/approvals")
async def list_approvals():
    """List pending approval requests."""
    gate = get_approval_gate()
    return {"pending": gate.get_pending()}


@app.post("/api/approval/{task_id}")
async def submit_approval(task_id: str, decision: ApprovalDecision):
    """Submit an approval decision."""
    gate = get_approval_gate()
    try:
        result = gate.submit_decision(
            task_id=task_id,
            approved=decision.approved,
            reviewer_id=decision.reviewer_id,
            comment=decision.comment,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Utility endpoints ────────────────────────────────────────

@app.get("/api/connectors")
async def get_connectors():
    """List available data connectors."""
    return {"connectors": list_connectors()}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "llm_base_url": settings.llm_base_url,
        "secondary_llm_base_url": settings.secondary_llm_base_url,
    }


# ── Mount static frontend ───────────────────────────────────
import os
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
