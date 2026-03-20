"""PII and secret redaction.

Scans text for common PII patterns and replaces them before model exposure.
"""

from __future__ import annotations

import re

# Patterns ordered by priority
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]"),
    ("phone", re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    ("credit_card", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "[CARD]"),
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
    ("api_key", re.compile(
        r"\b(?:sk-|pk-|tvly-|ghp_|gho_|xoxb-|xoxp-)[A-Za-z0-9_-]{16,}\b"
    ), "[API_KEY]"),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}"), "Bearer [TOKEN]"),
    ("password_field", re.compile(
        r'(?:password|passwd|pwd|secret|token)\s*[=:]\s*["\']?[^\s"\']{4,}',
        re.IGNORECASE,
    ), "[REDACTED_SECRET]"),
]


def redact_pii(text: str, patterns: list[str] | None = None) -> str:
    """Replace PII/secret patterns in text.

    Args:
        text: Input text to scan.
        patterns: Optional list of pattern names to apply.
                  If None, applies all patterns.

    Returns:
        Redacted text.
    """
    for name, pattern, replacement in _PATTERNS:
        if patterns and name not in patterns:
            continue
        text = pattern.sub(replacement, text)
    return text


def contains_pii(text: str) -> list[str]:
    """Check if text contains any PII patterns. Returns list of pattern names found."""
    found = []
    for name, pattern, _ in _PATTERNS:
        if pattern.search(text):
            found.append(name)
    return found
