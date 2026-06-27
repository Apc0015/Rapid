from __future__ import annotations
"""
QdrantStore — Qdrant-backed vector store for RAPID.

Mirrors the DeptFaissIndex interface exactly so DocMaster needs no changes.
Enable via env var: USE_QDRANT=true  (QDRANT_URL defaults to http://localhost:6333)

Each department maps to one Qdrant collection (rapid_<dept_tag>).
Dense vectors are stored in Qdrant; BM25 is kept in memory, rebuilt from
Qdrant payload on startup — same as the FAISS path.

Lazy initialisation: the Qdrant client and collection are created on first use,
so startup never blocks even if Qdrant is not yet reachable.
"""

import asyncio
import logging
import os
import uuid as _uuid
from typing import Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi

from infrastructure.faiss_store import Chunk  # shared dataclass

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_id_to_uuid(chunk_id: str) -> str:
    """Deterministic UUID from string chunk_id (Qdrant requires UUID or uint64 ids)."""
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, chunk_id))


# ── Per-department Qdrant index ───────────────────────────────────────────────

class DeptQdrantIndex:
    """
    One Qdrant collection per department. Same async interface as DeptFaissIndex.

    Vector operations delegate to AsyncQdrantClient.
    BM25 index is kept in memory and rebuilt from Qdrant payload on first use.
    """

    def __init__(self, dept_tag: str, dim: int, url: str) -> None:
        self.dept_tag   = dept_tag
        self.dim        = dim
        self._url       = url
        self._collection = f"rapid_{dept_tag}"
        self._lock       = asyncio.Lock()

        # Lazy state — populated on first _ensure_ready() call
        self._client     = None          # AsyncQdrantClient
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_meta: List[dict]      = []
        self._ready      = False

    # ── Lazy init ─────────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            from qdrant_client import AsyncQdrantClient
            self._client = AsyncQdrantClient(url=self._url)
        return self._client

    async def _ensure_ready(self) -> None:
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            from qdrant_client.models import VectorParams, Distance
            client = self._get_client()
            collections = [c.name for c in (await client.get_collections()).collections]
            if self._collection not in collections:
                await client.create_collection(
                    self._collection,
                    vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
                )
                logger.info(f"[Qdrant] Created collection '{self._collection}'")
            await self._load_bm25()
            self._ready = True

    # ── BM25 (in-memory, sourced from Qdrant payload) ─────────────────────────

    async def _load_bm25(self) -> None:
        try:
            client = self._get_client()
            points, _ = await client.scroll(
                self._collection,
                limit=20000,
                with_payload=True,
                with_vectors=False,
            )
            self._bm25_meta = [p.payload for p in points if p.payload]
            self._rebuild_bm25()
            logger.debug(f"[Qdrant/{self.dept_tag}] BM25 loaded — {len(self._bm25_meta)} chunks")
        except Exception as e:
            logger.warning(f"[Qdrant/{self.dept_tag}] BM25 load failed: {e}")

    def _rebuild_bm25(self) -> None:
        if not self._bm25_meta:
            self._bm25 = None
            return
        corpus = [m.get("text", "").lower().split() for m in self._bm25_meta]
        self._bm25 = BM25Okapi(corpus)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    async def add(self, chunk_id: str, text: str, source: str, embedding: List[float]) -> None:
        await self.add_batch([(chunk_id, text, source, embedding)])

    async def add_batch(self, chunks: List[Tuple[str, str, str, List[float]]]) -> None:
        await self._ensure_ready()
        async with self._lock:
            from qdrant_client.models import PointStruct
            client = self._get_client()
            points = [
                PointStruct(
                    id=_chunk_id_to_uuid(chunk_id),
                    vector=list(embedding),
                    payload={"chunk_id": chunk_id, "text": text, "source": source},
                )
                for chunk_id, text, source, embedding in chunks
            ]
            await client.upsert(self._collection, points=points)
            await self._load_bm25()
            logger.info(f"[Qdrant/{self.dept_tag}] Added {len(points)} chunks")

    async def delete_source(self, source_name: str) -> int:
        await self._ensure_ready()
        async with self._lock:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
            client = self._get_client()
            before = await self._count()
            await client.delete(
                self._collection,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="source", match=MatchValue(value=source_name))]
                    )
                ),
            )
            await self._load_bm25()
            after = await self._count()
            removed = max(0, before - after)
            logger.info(f"[Qdrant/{self.dept_tag}] Deleted {removed} chunks for source='{source_name}'")
            return removed

    # ── Search ────────────────────────────────────────────────────────────────

    async def vector_search(
        self, embedding: List[float], top_k: int = 10
    ) -> List[Tuple[Chunk, float]]:
        await self._ensure_ready()
        client = self._get_client()
        try:
            results = await client.search(
                self._collection,
                query_vector=list(embedding),
                limit=top_k,
                with_payload=True,
            )
        except Exception as e:
            logger.error(f"[Qdrant/{self.dept_tag}] vector_search failed: {e}")
            return []
        return [
            (
                Chunk(
                    chunk_id=r.payload["chunk_id"],
                    text=r.payload["text"],
                    source=r.payload["source"],
                    dept_tag=self.dept_tag,
                ),
                float(r.score),
            )
            for r in results
            if r.payload
        ]

    async def bm25_search(
        self, query_text: str, top_k: int = 10
    ) -> List[Tuple[Chunk, float]]:
        await self._ensure_ready()
        async with self._lock:
            if self._bm25 is None or not self._bm25_meta:
                return []
            tokens = query_text.lower().split()
            scores = self._bm25.get_scores(tokens)
            ranked = sorted(
                [(i, float(scores[i])) for i in range(len(scores)) if scores[i] > 0],
                key=lambda x: x[1],
                reverse=True,
            )[:top_k]
            return [
                (
                    Chunk(
                        chunk_id=self._bm25_meta[i]["chunk_id"],
                        text=self._bm25_meta[i]["text"],
                        source=self._bm25_meta[i]["source"],
                        dept_tag=self.dept_tag,
                    ),
                    score,
                )
                for i, score in ranked
            ]

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def _count(self) -> int:
        try:
            info = await self._get_client().get_collection(self._collection)
            return info.vectors_count or 0
        except Exception:
            return 0

    @property
    def doc_count(self) -> int:
        return len(self._bm25_meta)

    def list_sources(self) -> List[str]:
        return list({m.get("source", "") for m in self._bm25_meta if m.get("source")})


# ── Registry: one index per dept ─────────────────────────────────────────────

_qdrant_indices: Dict[str, DeptQdrantIndex] = {}


def get_qdrant_dept_index(
    dept_tag: str,
    dim: int = 768,
    url: Optional[str] = None,
) -> DeptQdrantIndex:
    """Get or create the Qdrant index for a department."""
    if dept_tag not in _qdrant_indices:
        resolved_url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        _qdrant_indices[dept_tag] = DeptQdrantIndex(dept_tag, dim=dim, url=resolved_url)
    return _qdrant_indices[dept_tag]
