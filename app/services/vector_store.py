"""
Vector Store — ChromaDB wrapper for document chunk storage and retrieval.

Extracted from the old rag/engine.py VectorDB class.
No LangChain dependency. Direct ChromaDB usage.
"""

import hashlib
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")


class VectorStore:
    """
    ChromaDB-backed vector store for document chunks.

    Collection name is tagged with embedding dimension to prevent
    dimension mismatch when switching embedding providers.
    """

    def __init__(self, embedding_manager):
        self.embedding_manager = embedding_manager
        self._client = None
        self._collection = None
        self._current_dim: Optional[int] = None

    def _get_collection(self):
        """Lazy-init ChromaDB collection. Re-initializes on dimension change."""
        try:
            import chromadb
        except ImportError:
            raise ImportError("chromadb not installed. Run: pip install chromadb")

        dim = self.embedding_manager.get_dimension()

        if self._collection is not None and dim == self._current_dim:
            return self._collection

        os.makedirs(CHROMA_DIR, exist_ok=True)
        self._client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection_name = f"rapid_docs_{dim}d"

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._current_dim = dim
        logger.info("VectorStore initialized: collection=%s (%d dims)", collection_name, dim)
        return self._collection

    # ─── Document management ──────────────────────────────────────────────────

    def add_document(
        self,
        doc_id: str,
        chunks: List[str],
        metadata: Dict,
    ) -> None:
        """Index a document's chunks into ChromaDB."""
        if not chunks:
            return

        collection = self._get_collection()

        # Delete existing chunks for this doc_id before re-indexing
        self.delete_document(doc_id)

        embeddings = self.embedding_manager.embed(chunks)

        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metas = [
            {
                "doc_id": doc_id,
                "chunk_id": i,
                "chunk_text": chunk,
                **{k: str(v) for k, v in metadata.items()},
            }
            for i, chunk in enumerate(chunks)
        ]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metas,
        )
        logger.info("VectorStore: indexed %d chunks for doc_id=%s", len(chunks), doc_id)

    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks for a document."""
        try:
            collection = self._get_collection()
            results = collection.get(where={"doc_id": doc_id})
            if results and results.get("ids"):
                collection.delete(ids=results["ids"])
                logger.info("VectorStore: deleted %d chunks for doc_id=%s", len(results["ids"]), doc_id)
        except Exception as e:
            logger.warning("VectorStore delete failed for %s: %s", doc_id, e)

    def list_documents(self) -> List[Dict]:
        """Return list of unique documents (one entry per doc_id)."""
        try:
            collection = self._get_collection()
            results = collection.get()
            if not results or not results.get("metadatas"):
                return []

            seen = {}
            for meta in results["metadatas"]:
                doc_id = meta.get("doc_id", "")
                if doc_id and doc_id not in seen:
                    seen[doc_id] = {
                        "doc_id": doc_id,
                        "filename": meta.get("filename", doc_id),
                        "doc_type": meta.get("doc_type", "unknown"),
                        "doc_subtype": meta.get("doc_subtype", ""),
                        "upload_timestamp": meta.get("upload_timestamp", ""),
                    }
            return list(seen.values())
        except Exception as e:
            logger.warning("VectorStore list_documents failed: %s", e)
            return []

    # ─── Retrieval ────────────────────────────────────────────────────────────

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where_filter: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Semantic similarity search.

        Returns list of dicts with keys:
          document, metadata, distance (lower = more similar)
        """
        try:
            collection = self._get_collection()
            kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": min(top_k, max(collection.count(), 1)),
                "include": ["documents", "metadatas", "distances"],
            }
            if where_filter:
                kwargs["where"] = where_filter

            results = collection.query(**kwargs)
            if not results or not results.get("ids") or not results["ids"][0]:
                return []

            output = []
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                output.append({
                    "document": doc,
                    "metadata": meta,
                    "score": dist,           # cosine distance (lower = better)
                })
            return output
        except Exception as e:
            logger.warning("VectorStore search failed: %s", e)
            return []

    def get_collection_stats(self) -> Dict:
        try:
            collection = self._get_collection()
            return {
                "total_chunks": collection.count(),
                "collection_name": collection.name,
                "embedding_dim": self._current_dim,
            }
        except Exception as e:
            return {"error": str(e)}
