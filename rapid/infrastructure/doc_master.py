from __future__ import annotations
"""
DocMaster — manages all RAG operations.

Replaces ChromaDB with per-department FAISS indexes.
Replaces OpenAI embeddings with local Ollama embedding service.
Each department has its own isolated index and RAG configuration.

Pipeline:
  R1  Classify doc types (LLM, optional)
  R2  HyDE query rewriting (embed hypothetical answer)
  R3  Hybrid search: FAISS vector + BM25 → RRF
  R4  NL summarisation (RAG firewall — caller sees only NL, never chunks)
"""

import logging
from pathlib import Path
from typing import List, Tuple, Optional

from infrastructure.embedding_service import get_embedder
from infrastructure.faiss_store import get_dept_index, Chunk
from infrastructure.dept_config import get_dept_config
from infrastructure.llm_client import get_llm

logger = logging.getLogger(__name__)


class DocMaster:

    # ── Ingestion ─────────────────────────────────────────────────────────────

    async def ingest_document(self, file_path: str, dept_tag: str) -> int:
        """
        Load → chunk → embed → store in dept's FAISS index.
        Returns number of chunks created.
        Uses dept-specific embedding model and chunk size.
        """
        cfg      = get_dept_config().get_rag(dept_tag)
        embedder = get_embedder()
        path     = Path(file_path)
        text     = self._load_text(path)

        chunks   = self._split_into_chunks(
            text,
            chunk_size=cfg["chunk_size"],
            overlap=cfg["chunk_overlap"],
        )
        source_name = path.name
        embed_model = cfg["embedding_model"]
        dim         = embedder.dim_for_model(embed_model)
        index       = get_dept_index(dept_tag, dim=dim)

        # Embed all chunks
        embeddings = await embedder.embed_batch(chunks, model=embed_model)

        batch = []
        for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{dept_tag}::{source_name}::{i}"
            batch.append((chunk_id, chunk_text, source_name, embedding))

        await index.add_batch(batch)
        logger.info(f"Ingested {len(batch)} chunks from '{source_name}' into dept={dept_tag} index")
        return len(batch)

    async def delete_document(self, source_name: str, dept_tag: str) -> int:
        """Remove all chunks for a source file from the dept index."""
        index = get_dept_index(dept_tag)
        removed = await index.delete_source(source_name)
        logger.info(f"Deleted {removed} chunks for '{source_name}' from dept={dept_tag}")
        return removed

    # ── HyDE query rewriting ──────────────────────────────────────────────────

    async def rewrite_query_hyde(self, query_text: str, dept_tag: str = "") -> List[float]:
        """
        HyDE: generate a hypothetical document answer, embed it.
        Uses dept's configured embedding model.
        Falls back to embedding the raw query if LLM fails.
        """
        cfg     = get_dept_config().get_rag(dept_tag) if dept_tag else {}
        model   = cfg.get("embedding_model", "nomic-embed-text") if cfg else "nomic-embed-text"
        llm     = get_llm()

        try:
            system = (
                "You are a corporate knowledge assistant. "
                "Write a short, factual paragraph that directly answers the question. "
                "Write as if it were a passage from an internal policy or report. "
                "Be concise — 3 to 5 sentences only."
            )
            hypothetical = await llm.complete(query_text, system=system)
            return await get_embedder().embed(hypothetical, model=model)
        except Exception as e:
            logger.warning(f"HyDE failed ({e}), falling back to raw query embedding")
            return await get_embedder().embed(query_text, model=model)

    # ── Hybrid search ─────────────────────────────────────────────────────────

    async def hybrid_search(
        self,
        query_embedding: List[float],
        query_text: str,
        dept_tag: str,
        top_k: Optional[int] = None,
    ) -> List[Chunk]:
        """
        Vector search + BM25 → Reciprocal Rank Fusion.
        Scoped entirely to dept_tag's FAISS index.
        """
        cfg     = get_dept_config().get_rag(dept_tag)
        k       = top_k or cfg["top_k"]
        alpha   = cfg["rrf_alpha"]
        b_alpha = cfg["bm25_alpha"]
        dim     = get_embedder().dim_for_model(cfg["embedding_model"])
        index   = get_dept_index(dept_tag, dim=dim)

        vector_results = await index.vector_search(query_embedding, top_k=k * 2)
        bm25_results   = await index.bm25_search(query_text, top_k=k * 2)

        # Filter by similarity threshold
        threshold = cfg.get("similarity_threshold", 0.25)
        vector_results = [(c, s) for c, s in vector_results if s >= threshold]

        combined = self._rrf_combine(vector_results, bm25_results, k, alpha, b_alpha)
        return combined

    # ── NL conversion (RAG firewall) ──────────────────────────────────────────

    async def convert_chunks_to_nl(
        self, chunks: List[Chunk], query: str, dept_tag: str = ""
    ) -> Tuple[str, List[str]]:
        """
        Convert retrieved chunks into a fluent NL summary.
        Grounded only in chunks — LLM cannot add external information.
        Returns (nl_summary, source_citations).
        """
        llm     = get_llm()
        context = "\n\n---\n\n".join(
            f"[Source: {c.source}]\n{c.text}" for c in chunks
        )
        dept_label = dept_tag.upper() if dept_tag else "corporate"
        system = (
            f"You are the {dept_label} department knowledge assistant. "
            "Answer the question using ONLY the provided document excerpts. "
            "If the excerpts don't contain enough information, say so explicitly. "
            "Do not add any facts not present in the excerpts. "
            "Be concise and professional."
        )
        prompt  = f"Question: {query}\n\nDocument excerpts:\n{context}"
        summary = await llm.complete(prompt, system=system)
        citations = list({c.source for c in chunks})
        return summary, citations

    # ── Stats ─────────────────────────────────────────────────────────────────

    def doc_count(self, dept_tag: Optional[str] = None) -> int:
        """Total chunks across all dept indexes, or for a specific dept."""
        from infrastructure.faiss_store import all_dept_indices, get_dept_index
        if dept_tag:
            return get_dept_index(dept_tag).doc_count
        return sum(idx.doc_count for idx in all_dept_indices().values())

    def list_sources(self, dept_tag: str) -> List[str]:
        from infrastructure.faiss_store import get_dept_index
        return get_dept_index(dept_tag).list_sources()

    # ── Text loading ──────────────────────────────────────────────────────────

    def _load_text(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                pages = [page.extract_text() or "" for page in reader.pages]
                text  = "\n\n".join(p for p in pages if p.strip())
                if not text.strip():
                    raise ValueError("PDF appears to be scanned/image-based — no extractable text.")
                return text
            except ImportError:
                raise ValueError("Install 'pypdf': pip install pypdf")
        if suffix == ".docx":
            try:
                from docx import Document
                doc = Document(str(path))
                return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                raise ValueError("Install 'python-docx': pip install python-docx")
        if suffix == ".csv":
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".json":
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            import json as _json
            return _json.dumps(data, indent=2)
        raise ValueError(f"Unsupported file type: {suffix}")

    # ── Chunking ──────────────────────────────────────────────────────────────

    def _split_into_chunks(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Word-based chunking. chunk_size/overlap in approximate tokens."""
        words       = text.split()
        word_chunk  = max(1, int(chunk_size * 0.75))
        word_overlap = max(0, int(overlap * 0.75))
        chunks, start = [], 0
        while start < len(words):
            end = min(start + word_chunk, len(words))
            chunks.append(" ".join(words[start:end]))
            if end == len(words):
                break
            start += word_chunk - word_overlap
        return [c for c in chunks if c.strip()]

    # ── RRF ───────────────────────────────────────────────────────────────────

    def _rrf_combine(
        self,
        vector_results: List[Tuple[Chunk, float]],
        bm25_results:   List[Tuple[Chunk, float]],
        top_k: int,
        alpha: float = 0.6,
        b_alpha: float = 0.4,
        k: int = 60,
    ) -> List[Chunk]:
        """Reciprocal Rank Fusion with configurable alpha weights."""
        vector_ranks = {c.chunk_id: rank + 1 for rank, (c, _) in enumerate(vector_results)}
        bm25_ranks   = {c.chunk_id: rank + 1 for rank, (c, _) in enumerate(bm25_results)}

        all_ids = set(vector_ranks) | set(bm25_ranks)
        rrf_scores: dict[str, float] = {}
        for cid in all_ids:
            v = alpha   / (k + vector_ranks[cid]) if cid in vector_ranks else 0.0
            b = b_alpha / (k + bm25_ranks[cid])   if cid in bm25_ranks   else 0.0
            rrf_scores[cid] = v + b

        ranked_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)[:top_k]

        # Build chunk lookup from both result sets
        chunk_lookup: dict[str, Chunk] = {}
        for c, _ in vector_results:
            chunk_lookup[c.chunk_id] = c
        for c, _ in bm25_results:
            chunk_lookup.setdefault(c.chunk_id, c)

        return [chunk_lookup[cid] for cid in ranked_ids if cid in chunk_lookup]


# ── Singleton ─────────────────────────────────────────────────────────────────

_doc_master: Optional[DocMaster] = None


def get_doc_master() -> DocMaster:
    global _doc_master
    if _doc_master is None:
        _doc_master = DocMaster()
    return _doc_master
