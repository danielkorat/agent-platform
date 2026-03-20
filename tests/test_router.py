"""Tests for the complexity router."""

import pytest
from graphs.shared.router import classify_by_rules


class TestRuleBasedClassification:
    """Test rule-based heuristics for complexity routing."""

    def test_simple_query_classified_fast(self):
        result = classify_by_rules("What is RAG?")
        assert result["complexity"] == "fast"

    def test_comparison_classified_deep(self):
        result = classify_by_rules(
            "Compare RAG pipeline architectures versus traditional search. "
            "Evaluate the tradeoffs between dense retrieval and hybrid approaches "
            "for enterprise knowledge systems."
        )
        assert result["complexity"] == "deep"
        assert result["signals"]["deep"] >= 2

    def test_incident_classified_medium_it_ops(self):
        result = classify_by_rules(
            "Troubleshoot the database connection pool exhaustion on db-prod-01"
        )
        assert result["complexity"] == "medium"
        assert result["scenario"] == "it_ops"

    def test_action_query_high_risk(self):
        result = classify_by_rules(
            "Restart the payment-service pods and deploy hotfix v2.4.2"
        )
        assert result["risk"] in ("medium", "high")

    def test_research_query_deep_research(self):
        result = classify_by_rules(
            "Research the comprehensive impact of speculative decoding on LLM inference throughput"
        )
        assert result["scenario"] == "deep_research"
        assert result["complexity"] == "deep"

    def test_empty_query(self):
        result = classify_by_rules("")
        assert result["complexity"] == "fast"

    def test_medium_length_query(self):
        result = classify_by_rules(
            "How do I fix the SSL certificate renewal failure for api.example.com?"
        )
        assert result["complexity"] == "medium"
