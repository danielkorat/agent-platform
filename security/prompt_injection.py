"""Prompt injection detection.

Treats all retrieved content as untrusted input.
Separates system instructions from user/retrieved text.
"""

from __future__ import annotations

import re


# Heuristic patterns that indicate prompt injection attempts
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(previous|all|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(your|all|the)\s+(rules|instructions|guidelines)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"new\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"override\s+(system|safety|security)", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\]", re.IGNORECASE),
    re.compile(r"```\s*system\s*\n", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+(have\s+)?no\s+restrictions", re.IGNORECASE),
    re.compile(r"pretend\s+(you|that)\s+(are|can|have)", re.IGNORECASE),
]


def detect_injection(text: str) -> list[str]:
    """Scan text for prompt injection patterns.

    Returns list of matched pattern descriptions (empty if clean).
    """
    matches = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return matches


def is_safe(text: str) -> bool:
    """Returns True if no injection patterns detected."""
    return len(detect_injection(text)) == 0


def sanitize_retrieved_content(chunks: list[dict]) -> list[dict]:
    """Mark chunks that contain potential injection patterns.

    Does NOT remove them — just flags them so the system can decide.
    """
    for chunk in chunks:
        text = chunk.get("text", "")
        injections = detect_injection(text)
        if injections:
            chunk["_injection_warning"] = True
            chunk["_injection_patterns"] = injections
    return chunks
