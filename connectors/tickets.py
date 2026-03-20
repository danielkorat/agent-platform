"""Mock ticket system connector — simulates ServiceNow/Jira."""

from __future__ import annotations

from typing import Any

from connectors.base import BaseConnector

# ── Sample tickets ───────────────────────────────────────────

_MOCK_TICKETS = [
    {
        "id": "INC-001",
        "title": "Production database connection pool exhausted",
        "severity": "P1",
        "status": "open",
        "description": (
            "The production PostgreSQL database on db-prod-01 is showing connection pool "
            "exhaustion errors. Application pods are returning 503 errors. Pool size is set "
            "to 100 connections but monitoring shows 150+ active connections. Started at "
            "2026-03-19 14:30 UTC. Affecting 3 microservices: order-service, payment-service, "
            "inventory-service. Approximately 2,000 users impacted."
        ),
        "assigned_to": "oncall-team",
        "created": "2026-03-19T14:35:00Z",
        "tags": ["database", "connection-pool", "production", "p1"],
    },
    {
        "id": "INC-002",
        "title": "Kubernetes pod CrashLoopBackOff in staging",
        "severity": "P3",
        "status": "open",
        "description": (
            "The auth-service deployment in staging namespace has 3/5 pods in "
            "CrashLoopBackOff. Logs show OOMKilled with current limit at 512Mi. "
            "Started after deployment v2.4.1 was rolled out at 2026-03-19 10:00 UTC. "
            "Memory profiling suggests a leak in the JWT validation middleware."
        ),
        "assigned_to": "platform-team",
        "created": "2026-03-19T10:15:00Z",
        "tags": ["kubernetes", "oomkilled", "staging", "memory-leak"],
    },
    {
        "id": "INC-003",
        "title": "SSL certificate expiring in 7 days",
        "severity": "P2",
        "status": "open",
        "description": (
            "SSL certificate for api.example.com expires on 2026-03-27. Auto-renewal "
            "via cert-manager failed with ACME challenge error. DNS challenge provider "
            "returning timeout. Need manual intervention to renew or replace certificate."
        ),
        "assigned_to": "security-team",
        "created": "2026-03-19T09:00:00Z",
        "tags": ["ssl", "certificate", "expiry", "cert-manager"],
    },
    {
        "id": "INC-004",
        "title": "CI/CD pipeline failures on main branch",
        "severity": "P3",
        "status": "investigating",
        "description": (
            "The main branch CI pipeline has been failing for 4 hours. Unit tests pass "
            "but integration tests timeout at the database migration step. Suspect the "
            "test database server is under heavy load from another team's load testing. "
            "Blocking 12 PRs from merging."
        ),
        "assigned_to": "devops-team",
        "created": "2026-03-19T08:00:00Z",
        "tags": ["ci-cd", "pipeline", "integration-tests", "blocked"],
    },
    {
        "id": "INC-005",
        "title": "API latency spike on payment gateway",
        "severity": "P2",
        "status": "open",
        "description": (
            "Payment gateway API latency increased from 200ms p95 to 1.5s p95 starting "
            "at 2026-03-19 16:00 UTC. No recent deployments. Upstream provider status "
            "page shows no issues. Internal monitoring shows the proxy layer adding "
            "~1s latency. Envoy sidecar CPU usage at 95% on affected pods."
        ),
        "assigned_to": "payments-team",
        "created": "2026-03-19T16:10:00Z",
        "tags": ["latency", "payment", "envoy", "proxy", "p2"],
    },
]


class TicketConnector(BaseConnector):
    """Mock ticket system connector."""

    @property
    def name(self) -> str:
        return "ticket_system"

    async def search(self, query: str, **kwargs) -> list[dict[str, Any]]:
        """Search tickets by keyword match."""
        query_lower = query.lower()
        results = []
        for ticket in _MOCK_TICKETS:
            searchable = f"{ticket['title']} {ticket['description']} {' '.join(ticket['tags'])}".lower()
            if any(word in searchable for word in query_lower.split()):
                results.append(ticket)
        return results

    async def get(self, item_id: str) -> dict[str, Any] | None:
        for ticket in _MOCK_TICKETS:
            if ticket["id"] == item_id:
                return ticket
        return None

    @property
    def is_read_only(self) -> bool:
        return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Simulate ticket actions (update, close, escalate)."""
        return {
            "status": "simulated",
            "action": action,
            "params": params,
            "message": f"Action '{action}' would be executed in production",
        }
