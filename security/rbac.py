"""Role-Based Access Control (RBAC).

Defines permissions for different roles and enforces access policies.
"""

from __future__ import annotations

from typing import Any


# ── Role definitions ─────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "read", "write", "execute", "approve",
        "manage_users", "view_audit", "manage_connectors",
        "access_all_tenants",
    },
    "analyst": {
        "read", "execute", "view_audit",
    },
    "operator": {
        "read", "write", "execute", "approve",
    },
    "viewer": {
        "read",
    },
}


class RBACError(Exception):
    """Insufficient permissions."""
    pass


def check_permission(auth_context: dict[str, Any], permission: str) -> bool:
    """Check if the auth context grants the given permission."""
    roles = auth_context.get("roles", [])
    for role in roles:
        if permission in ROLE_PERMISSIONS.get(role, set()):
            return True
    return False


def require_permission(auth_context: dict[str, Any], permission: str) -> None:
    """Enforce a permission check. Raises RBACError if denied."""
    if not check_permission(auth_context, permission):
        user = auth_context.get("user_id", "unknown")
        raise RBACError(f"User '{user}' lacks permission '{permission}'")


def check_tenant_access(auth_context: dict[str, Any], target_tenant: str) -> bool:
    """Check if user can access the target tenant's resources."""
    if check_permission(auth_context, "access_all_tenants"):
        return True
    return auth_context.get("tenant_id") == target_tenant


def require_tenant_access(auth_context: dict[str, Any], target_tenant: str) -> None:
    if not check_tenant_access(auth_context, target_tenant):
        raise RBACError(f"Access denied to tenant '{target_tenant}'")
