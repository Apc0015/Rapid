"""Tests for the BM25 full-text search engine."""

import os
import sys
import tempfile
import shutil
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.search.full_text_search import FullTextSearchEngine, _tokenize


class TestTokenizer:
    def test_basic_tokenize(self):
        tokens = _tokenize("The quick brown fox jumps over the lazy dog")
        assert "quick" in tokens
        assert "brown" in tokens
        assert "the" not in tokens  # stopword

    def test_stopword_removal(self):
        tokens = _tokenize("I am a student in the university")
        assert "student" in tokens
        assert "university" in tokens
        assert "am" not in tokens
        assert "the" not in tokens

    def test_lowercase(self):
        tokens = _tokenize("Hello World PYTHON")
        assert "hello" in tokens
        assert "world" in tokens
        assert "python" in tokens

    def test_empty_input(self):
        assert _tokenize("") == []

    def test_punctuation_removal(self):
        tokens = _tokenize("hello, world! test-case foo_bar")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens


class TestFullTextSearch:
    @pytest.fixture(autouse=True)
    def setup_engine(self, tmp_path):
        db_path = str(tmp_path / "test_ft.db")
        self.engine = FullTextSearchEngine(db_path=db_path)

    @pytest.fixture(autouse=True)
    def check_bm25(self):
        pytest.importorskip("rank_bm25")

    def test_index_and_search(self):
        self.engine.index_document("doc1", "Python is a great programming language for data science")
        self.engine.index_document("doc2", "Java is widely used in enterprise software development")
        self.engine.index_document("doc3", "Machine learning uses Python extensively")

        results = self.engine.search_keyword("Python programming", top_k=3)
        assert len(results) > 0
        # Python docs should rank higher
        found_python = any("python" in r["document"].lower() for r in results)
        assert found_python

    def test_search_no_results(self):
        self.engine.index_document("doc1", "The quick brown fox")
        results = self.engine.search_keyword("zzzznonexistent", top_k=5)
        assert len(results) == 0

    def test_empty_corpus(self):
        results = self.engine.search_keyword("test", top_k=5)
        assert results == []

    def test_reindex_document(self):
        self.engine.index_document("doc1", "original content about dogs")
        self.engine.index_document("doc2", "unrelated text about weather forecast")
        self.engine.index_document("doc3", "programming language features comparison")
        self.engine.index_document("doc4", "database performance optimization tips")
        self.engine.index_document("doc1", "updated content about cats and kittens")
        results = self.engine.search_keyword("cats kittens", top_k=5)
        found_cats = any("cats" in r["document"].lower() for r in results)
        assert found_cats

    def test_multiple_documents(self):
        for i in range(10):
            self.engine.index_document(f"doc_{i}", f"Document number {i} about topic {i}")
        results = self.engine.search_keyword("document topic", top_k=5)
        assert len(results) <= 5


class TestHybridMerge:
    def test_merge_disjoint(self):
        semantic = [
            {"document": "sem1", "metadata": {"chunk_id": "a"}, "score": 0.9},
            {"document": "sem2", "metadata": {"chunk_id": "b"}, "score": 0.8},
        ]
        keyword = [
            {"document": "kw1", "metadata": {"chunk_id": "c"}, "score": 5.0},
            {"document": "kw2", "metadata": {"chunk_id": "d"}, "score": 3.0},
        ]
        results = FullTextSearchEngine.hybrid_merge(semantic, keyword, alpha=0.5, top_k=3)
        assert len(results) <= 3
        assert all("search_type" in r["metadata"] for r in results)

    def test_merge_overlapping(self):
        semantic = [
            {"document": "shared_doc", "metadata": {"chunk_id": "x"}, "score": 0.9},
        ]
        keyword = [
            {"document": "shared_doc", "metadata": {"chunk_id": "x"}, "score": 5.0},
        ]
        results = FullTextSearchEngine.hybrid_merge(semantic, keyword, alpha=0.5, top_k=5)
        # Shared doc should appear once with boosted score
        assert len(results) == 1
        assert results[0]["metadata"]["chunk_id"] == "x"

    def test_merge_empty_semantic(self):
        keyword = [
            {"document": "kw1", "metadata": {"chunk_id": "a"}, "score": 5.0},
        ]
        results = FullTextSearchEngine.hybrid_merge([], keyword, alpha=0.5, top_k=5)
        assert len(results) == 1

    def test_merge_empty_keyword(self):
        semantic = [
            {"document": "sem1", "metadata": {"chunk_id": "a"}, "score": 0.9},
        ]
        results = FullTextSearchEngine.hybrid_merge(semantic, [], alpha=0.5, top_k=5)
        assert len(results) == 1

    def test_alpha_weighting(self):
        semantic = [
            {"document": "sem1", "metadata": {"chunk_id": "s1"}, "score": 0.9},
        ]
        keyword = [
            {"document": "kw1", "metadata": {"chunk_id": "k1"}, "score": 5.0},
        ]
        # alpha=1.0 → all semantic weight
        results_sem = FullTextSearchEngine.hybrid_merge(semantic, keyword, alpha=1.0, top_k=2)
        # alpha=0.0 → all keyword weight
        results_kw = FullTextSearchEngine.hybrid_merge(semantic, keyword, alpha=0.0, top_k=2)
        # First results should differ
        assert results_sem[0]["metadata"]["chunk_id"] == "s1"
        assert results_kw[0]["metadata"]["chunk_id"] == "k1"
