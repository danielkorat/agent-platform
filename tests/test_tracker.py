"""Tests for the token tracker."""

from token_tracker import TokenTracker


class TestTokenTracker:
    def test_track_call(self):
        tracker = TokenTracker("test-001")
        rec = tracker.track_call(
            caller="test", hardware="XPU", model="test-model",
            input_tokens=100, output_tokens=50, latency_s=1.0,
        )
        assert rec.seq == 1
        assert tracker.total_input_tokens == 100
        assert tracker.total_output_tokens == 50
        assert tracker.total_calls == 1

    def test_hw_summary(self):
        tracker = TokenTracker("test-002")
        tracker.track_call("a", "XPU", "model-a", 100, 50, 1.0)
        tracker.track_call("b", "Xeon", "model-b", 200, 30, 2.0)
        tracker.track_call("c", "XPU", "model-a", 150, 70, 1.5)

        summary = tracker.get_hw_summary()
        assert "XPU" in summary
        assert "Xeon" in summary
        assert summary["XPU"]["in_tokens"] == 250
        assert summary["XPU"]["calls"] == 2
        assert summary["Xeon"]["in_tokens"] == 200

    def test_tool_tracking(self):
        tracker = TokenTracker("test-003")
        tracker.track_tool("web_search", 2.5)
        tracker.track_tool("web_search", 1.8)
        tracker.track_tool("retrieval", 0.3)

        metrics = tracker.to_metrics_dict()
        assert len(metrics["tool_times"]["web_search"]) == 2
        assert len(metrics["tool_times"]["retrieval"]) == 1

    def test_latency_breakdown(self):
        tracker = TokenTracker("test-004")
        tracker.track_node("classify", 0.2, 0.1)
        tracker.track_node("retrieve", 0.5, 0.0)

        breakdown = tracker.get_latency_breakdown()
        assert breakdown["classify"] == 0.2
        assert breakdown["retrieve"] == 0.5
        assert "total_elapsed_s" in breakdown
