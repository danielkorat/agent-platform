"""Tests for the retrieval subsystem."""

import pytest
from retrieval.fusion import reciprocal_rank_fusion
from retrieval.packer import pack_context, _text_overlap


class TestRRF:
    def test_single_list(self):
        results = [
            {"chunk_id": "a", "text": "foo"},
            {"chunk_id": "b", "text": "bar"},
        ]
        fused = reciprocal_rank_fusion(results)
        assert len(fused) == 2
        assert fused[0]["chunk_id"] == "a"  # higher rank

    def test_merge_two_lists(self):
        list1 = [{"chunk_id": "a", "text": "foo"}, {"chunk_id": "b", "text": "bar"}]
        list2 = [{"chunk_id": "b", "text": "bar"}, {"chunk_id": "c", "text": "baz"}]
        fused = reciprocal_rank_fusion(list1, list2)
        # "b" appears in both lists → highest RRF score
        assert fused[0]["chunk_id"] == "b"

    def test_empty_lists(self):
        fused = reciprocal_rank_fusion([], [])
        assert fused == []


class TestContextPacker:
    def test_deduplication(self):
        chunks = [
            {"text": "The quick brown fox jumps over the lazy dog", "chunk_id": "c1"},
            {"text": "The quick brown fox jumps over the lazy dog", "chunk_id": "c2"},
            {"text": "Something completely different", "chunk_id": "c3"},
        ]
        packed = pack_context(chunks)
        # Near-duplicate c2 should be removed
        assert len(packed) == 2

    def test_source_diversity(self):
        chunks = [
            {"text": f"Text {i}", "chunk_id": f"c{i}", "source": "same_source"}
            for i in range(10)
        ]
        packed = pack_context(chunks, max_per_source=2)
        assert len(packed) == 2

    def test_max_chunks_limit(self):
        chunks = [
            {"text": f"Unique text number {i}", "chunk_id": f"c{i}", "source": f"s{i}"}
            for i in range(20)
        ]
        packed = pack_context(chunks, max_chunks=5)
        assert len(packed) == 5

    def test_text_overlap_same(self):
        assert _text_overlap("hello world", "hello world") == 1.0

    def test_text_overlap_different(self):
        assert _text_overlap("hello world", "foo bar baz") == 0.0
