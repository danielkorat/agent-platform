"""Token tracking, hardware utilization, and per-request metrics collection."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallRecord:
    """Single LLM call record."""
    seq: int
    caller: str
    hardware: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    ttft_ms: float = 0.0
    itl_ms: float = 0.0
    tps_out: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class HardwareStats:
    """Accumulated stats per hardware unit."""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_elapsed_s: float = 0.0
    call_count: int = 0

    @property
    def tps(self) -> float:
        return self.output_tokens / self.total_elapsed_s if self.total_elapsed_s > 0 else 0.0


class TokenTracker:
    """Per-request token and latency tracker.

    Create one per task execution. Thread-safe is not needed since
    LangGraph runs nodes sequentially within a single invocation.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.start_time = time.time()
        self._call_log: list[CallRecord] = []
        self._hw_stats: dict[str, HardwareStats] = {}
        self._node_timings: list[dict[str, Any]] = []
        self._tool_times: dict[str, list[float]] = {}
        self._seq = 0

    # ── LLM call tracking ────────────────────────────────────

    def track_call(
        self,
        caller: str,
        hardware: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_s: float,
        ttft_ms: float = 0.0,
        itl_ms: float = 0.0,
    ) -> CallRecord:
        self._seq += 1
        tps = output_tokens / latency_s if latency_s > 0 else 0.0
        rec = CallRecord(
            seq=self._seq,
            caller=caller,
            hardware=hardware,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_s=latency_s,
            ttft_ms=ttft_ms,
            itl_ms=itl_ms,
            tps_out=tps,
        )
        self._call_log.append(rec)
        self._track_hw(hardware, model, input_tokens, output_tokens, latency_s)
        return rec

    def _track_hw(
        self, hardware: str, model: str, in_tok: int, out_tok: int, elapsed: float
    ) -> None:
        stats = self._hw_stats.setdefault(hardware, HardwareStats(model=model))
        stats.input_tokens += in_tok
        stats.output_tokens += out_tok
        stats.total_elapsed_s += elapsed
        stats.call_count += 1

    # ── Tool timing ──────────────────────────────────────────

    def track_tool(self, tool_name: str, elapsed_s: float) -> None:
        self._tool_times.setdefault(tool_name, []).append(elapsed_s)

    # ── Node timing ──────────────────────────────────────────

    def track_node(self, node_name: str, wall_s: float, llm_s: float = 0.0) -> None:
        self._node_timings.append({
            "node": node_name,
            "wall_s": round(wall_s, 3),
            "llm_s": round(llm_s, 3),
            "overhead_s": round(wall_s - llm_s, 3),
        })

    # ── Aggregations ─────────────────────────────────────────

    @property
    def elapsed_s(self) -> float:
        return time.time() - self.start_time

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self._call_log)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self._call_log)

    @property
    def total_calls(self) -> int:
        return len(self._call_log)

    def get_hw_summary(self) -> dict[str, Any]:
        return {
            hw: {
                "model": s.model,
                "in_tokens": s.input_tokens,
                "out_tokens": s.output_tokens,
                "elapsed_s": round(s.total_elapsed_s, 2),
                "tps": round(s.tps, 1),
                "calls": s.call_count,
            }
            for hw, s in self._hw_stats.items()
        }

    def get_latency_breakdown(self) -> dict[str, float]:
        breakdown: dict[str, float] = {}
        for nt in self._node_timings:
            breakdown[nt["node"]] = nt["wall_s"]
        breakdown["total_elapsed_s"] = round(self.elapsed_s, 3)
        return breakdown

    def to_metrics_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "elapsed_s": round(self.elapsed_s, 3),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_calls": self.total_calls,
            "hw_summary": self.get_hw_summary(),
            "latency_breakdown": self.get_latency_breakdown(),
            "tool_times": {k: [round(v, 3) for v in vs] for k, vs in self._tool_times.items()},
            "call_log": [
                {
                    "seq": r.seq,
                    "caller": r.caller,
                    "hardware": r.hardware,
                    "model": r.model,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "latency_s": round(r.latency_s, 3),
                    "ttft_ms": round(r.ttft_ms, 1),
                    "tps_out": round(r.tps_out, 1),
                }
                for r in self._call_log
            ],
            "node_timings": self._node_timings,
        }
