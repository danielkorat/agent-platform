"""Output safety policies — content filtering and guardrails."""

from __future__ import annotations

from typing import Any


# Topics/patterns that should not appear in outputs
_BLOCKED_PATTERNS = [
    "DROP TABLE",
    "DELETE FROM",
    "sudo rm -rf",
    "format c:",
]


def check_output_safety(output: str) -> list[str]:
    """Check output for dangerous content. Returns list of violations."""
    violations = []
    output_upper = output.upper()
    for pattern in _BLOCKED_PATTERNS:
        if pattern.upper() in output_upper:
            violations.append(f"Blocked pattern: {pattern}")
    return violations


def apply_output_policies(
    output: str,
    risk_level: str = "low",
    approval_required: bool = False,
) -> dict[str, Any]:
    """Apply output policies based on risk level.

    Returns dict with 'output', 'approval_required', 'policy_notes'.
    """
    violations = check_output_safety(output)
    policy_notes = []

    if violations:
        policy_notes.extend(violations)
        # Don't block — flag for review
        approval_required = True

    if risk_level in ("high", "critical"):
        approval_required = True
        policy_notes.append(f"High-risk output (risk={risk_level}) requires approval")

    return {
        "output": output,
        "approval_required": approval_required,
        "policy_notes": policy_notes,
    }
