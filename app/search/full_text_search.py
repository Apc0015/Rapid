"""
Full-text search engine using BM25 for keyword-based retrieval.
Complements vector search for hybrid retrieval.
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

SEARCH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "search")
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
        """Load BM25 index from disk."""
        if os.path.exists(INDEX_PATH):
            try:
                with open(INDEX_PATH, 'r') as f:
                    data = json.load(f)
                self.documents = data.get("documents", [])
                self.corpus = [doc["tokens"] for doc in self.documents]
                if self.corpus:
                    try:
                        from rank_bm25 import BM25Okapi
                        self.bm25 = BM25Okapi(self.corpus)
                        logger.info(f"Loaded BM25 index with {len(self.documents)} documents")
                    except ImportError:
                        logger.warning("rank-bm25 not installed. Keyword search disabled.")
                        self.bm25 = None
            except Exception as e:
                logger.warning(f"Failed to load BM25 index: {e}")

    def _save_index(self):
        """Save BM25 index to disk."""
        try:
            with open(INDEX_PATH, 'w') as f:
                json.dump({"documents": self.documents}, f)
            logger.debug(f"Saved BM25 index with {len(self.documents)} documents")
        except Exception as e:
            logger.error(f"Failed to save BM25 index: {e}")

    def index_document(
        self,
        doc_id: str,
        text: str,
        chunk_size: int = 512,
        overlap: int = 64,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Index a document for keyword search.
        
        Args:
            doc_id: Unique document identifier
            text: Full document text
            chunk_size: Words per chunk
            overlap: Overlap words between chunks
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank-bm25 not installed. Skipping keyword indexing.")
            return

        words = text.split()
        step = max(chunk_size - overlap, 1)
        
        for i in range(0, len(words), step):
            chunk_text = " ".join(words[i:i + chunk_size])
            # Simple tokenization: lowercase + split
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
        
        # Rebuild BM25 index
        self.corpus = [doc["tokens"] for doc in self.documents]
        self.bm25 = BM25Okapi(self.corpus)
        self._save_index()
        
        logger.info(f"Indexed document {doc_id} for keyword search ({len(self.documents)} total chunks)")

    def search_keyword(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search documents using BM25 keyword matching.
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of results with document, metadata, and score
        """
        if not self.bm25 or not self.documents:
            logger.warning("BM25 index not initialized")
            return []
        
        # Tokenize query
        query_tokens = query.lower().split()
        
        # Get BM25 scores
        scores = self.bm25.get_scores(query_tokens)
        
        # Get top-k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:  # Only include non-zero scores
                doc = self.documents[idx]
                # Convert BM25 score to distance-like metric (lower is better)
                # ChromaDB uses distance, so we normalize similarly
                distance = 1.0 / (1.0 + scores[idx])
                
                results.append({
                    "document": doc["text"],
                    "metadata": {
                        "doc_id": doc["doc_id"],
                        "chunk_id": doc["chunk_id"],
                        **(doc.get("metadata") or {}),
                    },
                    "score": distance
                })
        
        logger.debug(f"Keyword search returned {len(results)} results")
        return results

    @staticmethod
    def hybrid_merge(
        semantic_results: List[Dict],
        keyword_results: List[Dict],
        alpha: float = 0.5,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Merge semantic and keyword search results using Reciprocal Rank Fusion (RRF).
        
        Args:
            semantic_results: Results from vector search
            keyword_results: Results from BM25 search
            alpha: Weight for semantic results (0-1). keyword weight = 1-alpha
            top_k: Number of final results to return
            
        Returns:
            Merged and ranked results
        """
        scores = defaultdict(float)
        docs = {}
        
        # RRF constant (commonly 60)
        k = 60
        
        # Add semantic results with rank-based scoring
        for rank, result in enumerate(semantic_results, 1):
            chunk_id = result['metadata'].get('chunk_id', 0)
            key = f"{result['metadata']['doc_id']}_{chunk_id}"
            scores[key] += alpha * (1.0 / (rank + k))
            docs[key] = result
        
        # Add keyword results with rank-based scoring
        for rank, result in enumerate(keyword_results, 1):
            chunk_id = result['metadata'].get('chunk_id', 0)
            key = f"{result['metadata']['doc_id']}_{chunk_id}"
            scores[key] += (1 - alpha) * (1.0 / (rank + k))
            if key not in docs:
                docs[key] = result
        
        # Sort by combined score and return top-k
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)[:top_k]
        merged_results = [docs[key] for key in sorted_keys]
        
        logger.debug(
            f"Merged {len(semantic_results)} semantic + {len(keyword_results)} keyword "
            f"results into {len(merged_results)} final results"
        )
        
        return merged_results

    def clear_index(self):
        """Clear all indexed documents."""
        self.documents = []
        self.corpus = []
        self.bm25 = None
        self._save_index()
        logger.info("Cleared BM25 index")

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "total_chunks": len(self.documents),
            "indexed": self.bm25 is not None,
            "index_path": INDEX_PATH
        }
