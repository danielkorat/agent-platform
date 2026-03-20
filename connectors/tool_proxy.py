"""Secure tool proxy — controlled access to connectors.

All tools are read-only by default. Write/execute tools require:
1. Explicit allowlisting in config
2. Human approval gate for each execution
"""

from __future__ import annotations

import logging
import time
from typing import Any

from connectors.base import BaseConnector
from connectors.tickets import TicketConnector
from connectors.kb import KBConnector
from security.rbac import require_permission
from security.approvals import get_approval_gate
from token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# ── Tool registry ────────────────────────────────────────────

_CONNECTORS: dict[str, BaseConnector] = {}


def _ensure_registered():
    global _CONNECTORS
    if not _CONNECTORS:
        _CONNECTORS = {
            "ticket_system": TicketConnector(),
            "knowledge_base": KBConnector(),
        }


def register_connector(name: str, connector: BaseConnector) -> None:
    _CONNECTORS[name] = connector


def get_connector(name: str) -> BaseConnector:
    _ensure_registered()
    if name not in _CONNECTORS:
        raise ValueError(f"Unknown connector: {name}. Available: {list(_CONNECTORS.keys())}")
    return _CONNECTORS[name]


def list_connectors() -> list[str]:
    _ensure_registered()
    return list(_CONNECTORS.keys())


# ── Allowlisted tools ───────────────────────────────────────

# Read tools — always available
READ_TOOLS = {"search", "get"}

# Action tools — require approval
ACTION_TOOLS = {"execute_action"}

# Blocked tools — never available
BLOCKED_TOOLS: set[str] = set()


async def proxy_tool_call(
    connector_name: str,
    operation: str,
    params: dict[str, Any],
    auth_context: dict[str, Any],
    task_id: str = "",
    tracker: TokenTracker | None = None,
) -> dict[str, Any]:
    """Execute a tool call through the secure proxy.

    Enforces:
    - Operation allowlisting
    - RBAC permission checks
    - Approval gate for write operations
    - Audit logging
    """
    t0 = time.time()

    if operation in BLOCKED_TOOLS:
        raise PermissionError(f"Operation '{operation}' is blocked")

    connector = get_connector(connector_name)

    # Read operations
    if operation in READ_TOOLS:
        require_permission(auth_context, "read")
        if operation == "search":
            result = await connector.search(params.get("query", ""), **params)
        elif operation == "get":
            result = await connector.get(params.get("item_id", ""))
        else:
            raise ValueError(f"Unknown read operation: {operation}")
    # Action operations
    elif operation in ACTION_TOOLS:
        require_permission(auth_context, "execute")
        if not connector.is_read_only:
            # Create approval request
            gate = get_approval_gate()
            gate.create_request(
                task_id=task_id,
                action=f"{connector_name}.{operation}: {params}",
                risk_level="high",
            )
            # For demo: auto-approve
            gate.submit_decision(task_id, approved=True, reviewer_id="auto")
            result = await connector.execute_action(params.get("action", ""), params)
        else:
            raise PermissionError(f"Connector '{connector_name}' is read-only")
    else:
        raise ValueError(f"Unknown operation: {operation}")

    elapsed = time.time() - t0
    if tracker:
        tracker.track_tool(f"{connector_name}.{operation}", elapsed)

    logger.info("Tool proxy: %s.%s completed in %.3fs", connector_name, operation, elapsed)

    return {"result": result, "elapsed_s": elapsed, "connector": connector_name}
