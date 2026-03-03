"""
Full-text search engine using BM25 for keyword-based retrieval.
Complements vector search for hybrid retrieval.

Moved from app/search/full_text_search.py — path updated.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
SEARCH_DIR = os.path.join(DATA_DIR, "search")
INDEX_PATH = os.path.join(SEARCH_DIR, "bm25_index.json")


class FullTextSearchEngine:
    """BM25-based keyword search engine for document retrieval."""

    def __init__(self):
        os.makedirs(SEARCH_DIR, exist_ok=True)
        self.documents = []
        self.corpus = []
        self.bm25 = None
        self._load_index()

    def _load_index(self):
        if os.path.exists(INDEX_PATH):
            try:
                with open(INDEX_PATH) as f:
                    data = json.load(f)
                self.documents = data.get("documents", [])
                self.corpus = [doc["tokens"] for doc in self.documents]
                if self.corpus:
                    try:
                        from rank_bm25 import BM25Okapi
                        self.bm25 = BM25Okapi(self.corpus)
                        logger.info("Loaded BM25 index: %d chunks", len(self.documents))
                    except ImportError:
                        logger.warning("rank-bm25 not installed. Keyword search disabled.")
            except Exception as e:
                logger.warning("Failed to load BM25 index: %s", e)

    def _save_index(self):
        try:
            with open(INDEX_PATH, "w") as f:
                json.dump({"documents": self.documents}, f)
        except Exception as e:
            logger.error("Failed to save BM25 index: %s", e)

    def index_document(
        self,
        doc_id: str,
        text: str,
        chunk_size: int = 512,
        overlap: int = 64,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Index a document for keyword search."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank-bm25 not installed. Skipping keyword indexing.")
            return

        # Remove existing chunks for this doc_id
        self.documents = [d for d in self.documents if d.get("doc_id") != doc_id]

        words = text.split()
        step = max(chunk_size - overlap, 1)
        for i in range(0, len(words), step):
            chunk_text = " ".join(words[i : i + chunk_size])
            tokens = chunk_text.lower().split()
            self.documents.append({
                "doc_id": doc_id,
                "chunk_id": len(self.documents),
                "text": chunk_text,
                "tokens": tokens,
                "metadata": metadata or {},
            })
            if i + chunk_size >= len(words):
                break

        self.corpus = [doc["tokens"] for doc in self.documents]
        self.bm25 = BM25Okapi(self.corpus)
        self._save_index()
        logger.info("Indexed %s for keyword search (%d total chunks)", doc_id, len(self.documents))

    def remove_document(self, doc_id: str):
        """Remove all chunks for a document from the index."""
        before = len(self.documents)
        self.documents = [d for d in self.documents if d.get("doc_id") != doc_id]
        removed = before - len(self.documents)
        if removed > 0:
            self.corpus = [doc["tokens"] for doc in self.documents]
            if self.corpus:
                from rank_bm25 import BM25Okapi
                self.bm25 = BM25Okapi(self.corpus)
            else:
                self.bm25 = None
            self._save_index()
            logger.info("Removed %d chunks for doc_id=%s", removed, doc_id)

    def search_keyword(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search documents using BM25 keyword matching."""
        if not self.bm25 or not self.documents:
            return []

        query_tokens = query.lower().split()
        scores = self.bm25.get_scores(query_tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                doc = self.documents[idx]
                distance = 1.0 / (1.0 + scores[idx])
                results.append({
                    "document": doc["text"],
                    "metadata": {
                        "doc_id": doc["doc_id"],
                        "chunk_id": doc["chunk_id"],
                        **(doc.get("metadata") or {}),
                    },
                    "score": distance,
                })
        return results

    @staticmethod
    def hybrid_merge(
        semantic_results: List[Dict],
        keyword_results: List[Dict],
        alpha: float = 0.6,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        Merge semantic and keyword results using Reciprocal Rank Fusion (RRF).
        alpha: weight for semantic results (0-1); keyword weight = 1-alpha.
        """
        scores = defaultdict(float)
        docs = {}
        k = 60  # RRF constant

        for rank, result in enumerate(semantic_results, 1):
            chunk_id = result["metadata"].get("chunk_id", 0)
            key = f"{result['metadata']['doc_id']}_{chunk_id}"
            scores[key] += alpha * (1.0 / (rank + k))
            docs[key] = result

        for rank, result in enumerate(keyword_results, 1):
            chunk_id = result["metadata"].get("chunk_id", 0)
            key = f"{result['metadata']['doc_id']}_{chunk_id}"
            scores[key] += (1 - alpha) * (1.0 / (rank + k))
            if key not in docs:
                docs[key] = result

        sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_k]
        return [docs[key] for key in sorted_keys]

    def clear_index(self):
        self.documents = []
        self.corpus = []
        self.bm25 = None
        self._save_index()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_chunks": len(self.documents),
            "indexed": self.bm25 is not None,
            "index_path": INDEX_PATH,
        }
