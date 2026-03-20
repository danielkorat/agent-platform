"""LangChain-compatible ChatOpenAI wrappers for LangGraph agent nodes."""

from __future__ import annotations

import os

import httpx
from langchain_openai import ChatOpenAI

from config import get_settings


def _suppress_proxy_env() -> dict[str, str | None]:
    """Temporarily remove ALL_PROXY/all_proxy to prevent ChatOpenAI init crash."""
    saved: dict[str, str | None] = {}
    for var in ("ALL_PROXY", "all_proxy"):
        saved[var] = os.environ.pop(var, None)
    return saved


def _restore_proxy_env(saved: dict[str, str | None]) -> None:
    for var, val in saved.items():
        if val is not None:
            os.environ[var] = val


def create_agent_llm(secondary: bool = False) -> ChatOpenAI:
    """Create a ChatOpenAI instance pointing at the vLLM server.

    Uses trust_env=False to bypass corporate proxy for localhost.
    """
    s = get_settings()
    base_url = s.secondary_llm_base_url if secondary else s.llm_base_url
    model = s.secondary_llm_model if secondary else s.llm_model

    saved = _suppress_proxy_env()
    try:
        llm = ChatOpenAI(
            base_url=base_url,
            model=model,
            api_key="not-needed",
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,
            http_async_client=httpx.AsyncClient(trust_env=False, timeout=120.0),
        )
    finally:
        _restore_proxy_env(saved)
    return llm


def get_agent_hardware(secondary: bool = False) -> str:
    s = get_settings()
    return s.secondary_llm_hardware if secondary else s.llm_hardware


def get_agent_model(secondary: bool = False) -> str:
    s = get_settings()
    return s.secondary_llm_model if secondary else s.llm_model
