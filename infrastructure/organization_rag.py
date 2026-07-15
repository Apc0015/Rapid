"""Governed hybrid retrieval for organization data sources."""
from __future__ import annotations

import logging
from typing import Any

from infrastructure.dept_config import get_dept_config
from infrastructure.embedding_service import get_embedder
from infrastructure.faiss_store import get_dept_index
from infrastructure.organization_data_store import OrganizationDataStore, get_organization_data_store

logger = logging.getLogger(__name__)


class OrganizationRagService:
    def __init__(self, store: OrganizationDataStore | None = None):
        self.store = store or get_organization_data_store()

    async def index_document(self, tenant_id: str, department: str, document_id: str) -> dict[str, Any]:
        document = self.store.get_document(tenant_id, document_id)
        if document["department"] != department:
            raise ValueError("Document is outside this department")
        chunks = document["chunks"]
        if not chunks:
            raise ValueError("Document contains no chunks to index")
        model = get_dept_config().get_rag(department).get("embedding_model", "nomic-embed-text")
        embeddings, backend = await get_embedder().embed_batch_for_tenant([chunk["content"] for chunk in chunks], tenant_id, model=model)
        dim = len(embeddings[0])
        index = get_dept_index(department, dim=dim, tenant_id=tenant_id)
        await index.add_batch([
            (chunk["id"], chunk["content"], document["name"], embedding)
            for chunk, embedding in zip(chunks, embeddings)
        ])
        self.store.mark_document_indexed(tenant_id, document_id, f"{model}:{backend}")
        return {"document_id": document_id, "chunks_indexed": len(chunks), "embedding_model": model, "embedding_backend": backend}

    async def search(self, tenant_id: str, department: str, query: str, source_id: str | None = None, limit: int = 8) -> dict[str, Any]:
        lexical = self.store.search(tenant_id, department, query, source_id, max(limit * 2, limit))
        lexical_by_id = {item["chunk_id"]: item for item in lexical["citations"]}
        model = get_dept_config().get_rag(department).get("embedding_model", "nomic-embed-text")
        backend = "unavailable"
        vector_results = []
        try:
            if not self.store.has_indexed_chunks(tenant_id, department):
                raise RuntimeError("No indexed chunks are available yet")
            embedding, backend = await get_embedder().embed_for_tenant(query, tenant_id, model=model)
            index = get_dept_index(department, dim=len(embedding), tenant_id=tenant_id)
            vector_results = await index.vector_search(embedding, top_k=max(limit * 2, limit))
        except Exception as error:
            logger.warning("Organization vector retrieval unavailable for %s/%s: %s", tenant_id, department, error)

        vector_by_id = {chunk.chunk_id: (rank, score) for rank, (chunk, score) in enumerate(vector_results, start=1)}
        lexical_ranks = {item["chunk_id"]: rank for rank, item in enumerate(lexical["citations"], start=1)}
        candidate_ids = set(vector_by_id) | set(lexical_ranks)
        ranked: list[tuple[float, str]] = []
        for chunk_id in candidate_ids:
            score = 0.0
            if chunk_id in vector_by_id:
                score += 0.62 / (60 + vector_by_id[chunk_id][0])
            if chunk_id in lexical_ranks:
                score += 0.38 / (60 + lexical_ranks[chunk_id])
            ranked.append((score, chunk_id))
        ranked.sort(reverse=True)

        citations = []
        for rrf_score, chunk_id in ranked:
            citation = lexical_by_id.get(chunk_id)
            if citation is None:
                try:
                    chunk = self.store.get_chunk(tenant_id, chunk_id)
                except Exception:
                    continue
                if source_id and chunk["source_id"] != source_id:
                    continue
                citation = {
                    "chunk_id": chunk["id"], "document_id": chunk["document_id"], "document_name": chunk["document_name"],
                    "source_id": chunk["source_id"], "source_name": chunk["source_name"], "classification": chunk["classification"],
                    "excerpt": chunk["content"][:500], "score": 0,
                }
            citations.append({**citation, "hybrid_score": round(rrf_score, 6)})
            if len(citations) >= limit:
                break

        retrieval = "hybrid_semantic" if vector_results and backend not in {"local_token_hash", "unavailable"} else ("hybrid_local" if vector_results else "lexical_fallback")
        return {
            "query": query,
            "department": department,
            "citations": citations,
            "count": len(citations),
            "retrieval": retrieval,
            "embedding_backend": backend,
            "permission_scope": {"tenant_id": tenant_id, "department": department, "source_id": source_id},
        }


def get_organization_rag() -> OrganizationRagService:
    return OrganizationRagService()
