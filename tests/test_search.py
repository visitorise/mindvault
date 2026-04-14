"""Tests for the hybrid search layer (BM25 + TF-IDF cosine)."""

import json
import math
from pathlib import Path

import pytest

from mindvault.search import (
    _cosine_similarity,
    _expand_query_tokens,
    _is_cjk,
    _snippet,
    _title_heading_boost,
    _tokenize,
    search,
)
from mindvault.index import _compute_idf


class TestTokenize:
    def test_basic_english(self):
        tokens = _tokenize("Hello World foo")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo" in tokens  # len 3 = kept (> 2)

    def test_short_english_filtered(self):
        tokens = _tokenize("I am ok do it")
        # "am", "ok", "do", "it" are all <= 2 chars
        assert "am" not in tokens
        assert "ok" not in tokens

    def test_korean_kept(self):
        tokens = _tokenize("택시 장부 앱")
        assert "택시" in tokens
        assert "장부" in tokens
        assert "앱" in tokens  # 1-char CJK kept

    def test_punctuation_stripped(self):
        tokens = _tokenize("hello, world! test.")
        assert "hello" in tokens
        assert "world" in tokens


class TestExpandQueryTokens:
    def test_camelcase_split(self):
        expanded = _expand_query_tokens(["runIncremental"])
        assert "runIncremental" in expanded  # original preserved
        assert "run" in expanded
        assert "incremental" in expanded

    def test_snake_case_split(self):
        expanded = _expand_query_tokens(["search_index"])
        assert "search" in expanded
        assert "index" in expanded

    def test_no_duplicate(self):
        expanded = _expand_query_tokens(["test"])
        assert expanded.count("test") == 1


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = {"a": 1.0, "b": 2.0}
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        vec_a = {"a": 1.0}
        vec_b = {"b": 1.0}
        assert _cosine_similarity(vec_a, vec_b) == 0.0

    def test_empty_vector(self):
        assert _cosine_similarity({}, {"a": 1.0}) == 0.0


class TestTitleHeadingBoost:
    def test_title_match(self):
        doc = {"title": "MindVault Rules Engine", "headings": []}
        boost = _title_heading_boost(doc, {"rules"})
        assert boost == 2.0  # 1.0 base + 1.0 title match

    def test_heading_match(self):
        doc = {"title": "Something", "headings": ["## Rules Setup"]}
        boost = _title_heading_boost(doc, {"rules"})
        assert boost == 1.5  # 1.0 base + 0.5 heading match

    def test_no_match(self):
        doc = {"title": "Something", "headings": []}
        boost = _title_heading_boost(doc, {"unrelated"})
        assert boost == 1.0

    def test_multiple_matches(self):
        doc = {"title": "Rules Engine Config", "headings": ["## Setup Guide"]}
        boost = _title_heading_boost(doc, {"rules", "config", "setup"})
        # rules in title (+1), config in title (+1), setup in heading (+0.5)
        assert boost == 3.5


class TestSearchIntegration:
    @pytest.fixture
    def search_index(self, tmp_path):
        """Create a minimal search index for testing."""
        docs = {
            "rules.md": {
                "title": "MindVault Rules Engine",
                "headings": ["## Adding Rules", "## Rule Types"],
                "tokens": _tokenize(
                    "MindVault Rules Engine add rule trigger warn block "
                    "check rules project global scope command output"
                ),
                "hash": "abc123",
            },
            "lore.md": {
                "title": "Lore System",
                "headings": ["## Recording Decisions"],
                "tokens": _tokenize(
                    "Lore system record decisions failures learnings "
                    "rollback tradeoff auto detect hook"
                ),
                "hash": "def456",
            },
            "query.md": {
                "title": "Query Layer",
                "headings": ["## BM25 Search", "## Graph Traversal"],
                "tokens": _tokenize(
                    "query search BM25 graph traversal wiki context "
                    "knowledge token budget layer"
                ),
                "hash": "ghi789",
            },
        }
        idf = _compute_idf(docs)
        index_data = {"version": 1, "doc_count": 3, "docs": docs, "idf": idf}
        index_path = tmp_path / "search_index.json"
        index_path.write_text(json.dumps(index_data, ensure_ascii=False))
        return index_path

    def test_title_match_ranks_first(self, search_index):
        results = search("rules engine", search_index, top_k=3)
        assert results[0]["title"] == "MindVault Rules Engine"

    def test_relevant_result_higher(self, search_index):
        results = search("lore record decision", search_index, top_k=3)
        assert results[0]["title"] == "Lore System"

    def test_empty_query_returns_empty(self, search_index):
        results = search("", search_index, top_k=3)
        assert results == []

    def test_no_match_returns_empty(self, search_index):
        results = search("xyznonexistent", search_index, top_k=3)
        assert results == []

    def test_dynamic_threshold_filters(self, search_index):
        results = search("rules", search_index, top_k=10)
        if len(results) > 1:
            # All results should be >= 20% of top score
            threshold = results[0]["score"] * 0.2
            for r in results:
                assert r["score"] >= threshold

    def test_score_is_positive(self, search_index):
        results = search("query search", search_index, top_k=3)
        for r in results:
            assert r["score"] > 0
