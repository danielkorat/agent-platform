"""Human approval gate.

Any write, execution, or high-risk action requires explicit human approval.
Read-only tools bypass this gate.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


class ApprovalTimeout(Exception):
    """Approval request timed out."""
    pass


class ApprovalDenied(Exception):
    """Approval was explicitly denied."""
    pass


class ApprovalGate:
    """Manages pending approval requests.

    In production, this would connect to a ticketing system, Slack, or email.
    For demo, it uses an in-memory queue with a REST endpoint for approval.
    """

    def __init__(self):
        self._pending: dict[str, dict[str, Any]] = {}
        self._decisions: dict[str, asyncio.Event] = {}

    def create_request(
        self,
        task_id: str,
        action: str,
        risk_level: str,
        evidence: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a pending approval request."""
        request = {
            "task_id": task_id,
            "action": action,
            "risk_level": risk_level,
            "evidence": evidence or [],
            "created_at": time.time(),
            "status": "pending",
            "reviewer": None,
            "comment": None,
        }
        self._pending[task_id] = request
        self._decisions[task_id] = asyncio.Event()
        logger.info("Approval request created: task=%s action=%s risk=%s",
                     task_id, action, risk_level)
        return request

    async def wait_for_decision(self, task_id: str) -> dict[str, Any]:
        """Wait for a human decision, with timeout."""
        timeout = get_settings().approval_timeout_s
        event = self._decisions.get(task_id)
        if not event:
            raise ValueError(f"No pending approval for task {task_id}")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._pending[task_id]["status"] = "timeout"
            raise ApprovalTimeout(
                f"Approval for task {task_id} timed out after {timeout}s"
            )

        return self._pending[task_id]

    def submit_decision(
        self,
        task_id: str,
        approved: bool,
        reviewer_id: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        """Submit a human decision on a pending approval."""
        if task_id not in self._pending:
            raise ValueError(f"No pending approval for task {task_id}")

        self._pending[task_id].update({
            "status": "approved" if approved else "rejected",
            "reviewer": reviewer_id,
            "comment": comment,
        })

        event = self._decisions.get(task_id)
        if event:
            event.set()

        logger.info("Approval decision: task=%s approved=%s reviewer=%s",
                     task_id, approved, reviewer_id)
        return self._pending[task_id]

    def get_pending(self) -> list[dict[str, Any]]:
        """List all pending approval requests."""
        return [r for r in self._pending.values() if r["status"] == "pending"]

    def get_request(self, task_id: str) -> dict[str, Any] | None:
        return self._pending.get(task_id)


# Module-level singleton
_gate = None


def get_approval_gate() -> ApprovalGate:
    global _gate
    if _gate is None:
        _gate = ApprovalGate()
    return _gate
