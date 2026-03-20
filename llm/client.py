"""Unified LLM client — wraps vLLM via OpenAI-compatible API.

Supports:
- Streaming chat (with TTFT / ITL / TPS measurement)
- Structured output via instructor
- Hardware-aware routing (primary GPU vs secondary CPU)
- Automatic proxy bypass for localhost
"""

from __future__ import annotations

import time
from typing import Any, Type, TypeVar

import httpx
import instructor
from openai import AsyncOpenAI

from config import get_settings
from token_tracker import TokenTracker

T = TypeVar("T")


def _make_http_client() -> httpx.AsyncClient:
    """Create httpx client that bypasses corporate proxy for localhost."""
    return httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120.0, connect=10.0))


class LLMClient:
    """Async LLM client wrapping a vLLM OpenAI-compatible endpoint.

    Args:
        secondary: If True, uses the secondary (CPU/SLM) endpoint.
        tracker: Optional token tracker for metrics collection.
    """

    def __init__(self, secondary: bool = False, tracker: TokenTracker | None = None):
        s = get_settings()
        if secondary:
            self.base_url = s.secondary_llm_base_url
            self.model = s.secondary_llm_model
            self.hardware = s.secondary_llm_hardware
        else:
            self.base_url = s.llm_base_url
            self.model = s.llm_model
            self.hardware = s.llm_hardware

        self.max_tokens = s.llm_max_tokens
        self.temperature = s.llm_temperature
        self.tracker = tracker

        http_client = _make_http_client()
        self._openai = AsyncOpenAI(
            base_url=self.base_url,
            api_key="not-needed",
            http_client=http_client,
        )
        self._instructor = instructor.from_openai(self._openai)

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        caller: str = "",
        stream: bool = True,
    ) -> str:
        """Send a chat completion request, optionally streaming.

        Returns the full response text. Tracks TTFT, TPS, and token usage.
        """
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_tokens or self.max_tokens
        t0 = time.time()
        ttft_ms = 0.0

        if stream:
            response = await self._openai.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temp,
                max_tokens=max_tok,
                stream=True,
            )
            chunks: list[str] = []
            first_token = True
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    if first_token:
                        ttft_ms = (time.time() - t0) * 1000
                        first_token = False
                    chunks.append(delta.content)
            content = "".join(chunks)
            # Estimate tokens (vLLM streaming doesn't always give usage)
            in_tok = sum(len(m.get("content", "")) for m in messages) // 4
            out_tok = len(content) // 4
        else:
            response = await self._openai.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temp,
                max_tokens=max_tok,
                stream=False,
            )
            content = response.choices[0].message.content or ""
            usage = response.usage
            in_tok = usage.prompt_tokens if usage else 0
            out_tok = usage.completion_tokens if usage else 0

        elapsed = time.time() - t0

        if self.tracker:
            self.tracker.track_call(
                caller=caller,
                hardware=self.hardware,
                model=self.model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_s=elapsed,
                ttft_ms=ttft_ms,
            )

        return content

    async def chat_structured(
        self,
        response_model: Type[T],
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        caller: str = "",
    ) -> T:
        """Get a structured (JSON-schema-validated) response."""
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_tokens or self.max_tokens
        t0 = time.time()

        result = await self._instructor.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temp,
            max_tokens=max_tok,
            response_model=response_model,
        )

        elapsed = time.time() - t0
        # Approximate tokens
        in_tok = sum(len(m.get("content", "")) for m in messages) // 4
        out_tok = len(str(result.model_dump())) // 4 if hasattr(result, "model_dump") else 50

        if self.tracker:
            self.tracker.track_call(
                caller=caller,
                hardware=self.hardware,
                model=self.model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_s=elapsed,
            )

        return result


def get_llm(
    caller: str = "",
    secondary: bool = False,
    tracker: TokenTracker | None = None,
) -> LLMClient:
    """Factory to get an LLM client, routing based on module config."""
    s = get_settings()
    if not secondary and caller in s.secondary_modules_set:
        secondary = True
    return LLMClient(secondary=secondary, tracker=tracker)
