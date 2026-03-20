"""Authentication — JWT-based token verification.

Supports:
- JWT bearer token validation
- API key authentication (simpler path)
- Bypass when require_auth=False (dev mode)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Authentication or authorization failure."""
    pass


def _b64_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return urlsafe_b64decode(s + "=" * padding)


def _b64_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def create_token(user_id: str, tenant_id: str, roles: list[str], ttl_s: int = 3600) -> str:
    """Create a simple HMAC-SHA256 signed JWT-like token."""
    secret = get_settings().jwt_secret
    header = _b64_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_data = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_s,
    }
    payload = _b64_encode(json.dumps(payload_data).encode())
    signature = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    sig_str = _b64_encode(signature)
    return f"{header}.{payload}.{sig_str}"


def verify_token(token: str) -> dict[str, Any]:
    """Verify and decode a JWT token. Raises AuthError on failure."""
    secret = get_settings().jwt_secret
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Invalid token format")

    header_b64, payload_b64, sig_b64 = parts
    expected_sig = hmac.new(
        secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    actual_sig = _b64_decode(sig_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise AuthError("Invalid token signature")

    payload = json.loads(_b64_decode(payload_b64))
    if payload.get("exp", 0) < time.time():
        raise AuthError("Token expired")

    return payload


def authenticate(auth_header: str | None) -> dict[str, Any]:
    """Authenticate a request. Returns auth context dict.

    In dev mode (require_auth=False), returns a default context.
    """
    s = get_settings()
    if not s.require_auth:
        return {
            "user_id": "anonymous",
            "tenant_id": "default",
            "roles": ["admin"],
            "authenticated": False,
        }

    if not auth_header:
        raise AuthError("Missing Authorization header")

    # API key auth
    if auth_header.startswith("ApiKey "):
        api_key = auth_header[7:]
        if hmac.compare_digest(api_key, s.api_key):
            return {
                "user_id": "api_user",
                "tenant_id": "default",
                "roles": ["user"],
                "authenticated": True,
            }
        raise AuthError("Invalid API key")

    # Bearer token auth
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_token(token)
        return {
            "user_id": payload["sub"],
            "tenant_id": payload.get("tenant_id", "default"),
            "roles": payload.get("roles", []),
            "authenticated": True,
        }

    raise AuthError("Unsupported auth scheme")
