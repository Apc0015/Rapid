"""
Chunking Service — document text chunking strategies.

Extracted from the old rag/engine.py ChunkingOptimizer and _chunk_text.
Used during document upload to prepare chunks for vector indexing.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

# Optimal chunk sizes per document type (words, with overlap)
_CHUNKING_CONFIGS = {
    "legal": {"chunk_size": 780, "overlap": 120},
    "academic": {"chunk_size": 640, "overlap": 100},
    "financial_doc": {"chunk_size": 560, "overlap": 90},
    "medical": {"chunk_size": 580, "overlap": 90},
    "code": {"chunk_size": 400, "overlap": 60},
    "narrative": {"chunk_size": 480, "overlap": 80},
    "tabular": {"chunk_size": 300, "overlap": 40},
    "default": {"chunk_size": 480, "overlap": 80},
}

# Type-specific top-K hints for retrieval
_TOP_K_HINTS = {
    "academic": 7,
    "legal": 5,
    "financial_doc": 6,
    "medical": 6,
    "code": 5,
    "narrative": 4,
    "tabular": 3,
    "default": 4,
}


@dataclass
class ChunkConfig:
    chunk_size: int      # words per chunk
    overlap: int         # overlap words between chunks
    top_k_hint: int      # recommended top-K for retrieval


class ChunkingService:
    """Provides optimal text chunking based on document type."""

    def get_config(self, doc_type: str) -> ChunkConfig:
        cfg = _CHUNKING_CONFIGS.get(doc_type, _CHUNKING_CONFIGS["default"])
        top_k = _TOP_K_HINTS.get(doc_type, _TOP_K_HINTS["default"])
        return ChunkConfig(
            chunk_size=cfg["chunk_size"],
            overlap=cfg["overlap"],
            top_k_hint=top_k,
        )

    def chunk_text(
        self,
        text: str,
        doc_type: str = "narrative",
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ) -> List[str]:
        """
        Split text into overlapping word-based chunks.

        Args:
            text: Full document text
            doc_type: Used to look up optimal parameters if not overridden
            chunk_size: Override chunk size (words)
            overlap: Override overlap (words)

        Returns:
            List of chunk strings
        """
        config = self.get_config(doc_type)
        size = chunk_size or config.chunk_size
        ovlp = overlap or config.overlap
        step = max(size - ovlp, 1)

        words = text.split()
        if not words:
            return []

        chunks = []
        for i in range(0, len(words), step):
            chunk = " ".join(words[i : i + size])
            if chunk.strip():
                chunks.append(chunk)
            if i + size >= len(words):
                break

        return chunks

    def chunk_by_paragraphs(self, text: str, max_words_per_chunk: int = 500) -> List[str]:
        """
        Split by paragraphs, merging short ones and splitting long ones.
        Better for narrative documents with clear paragraph structure.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current_words = []

        for para in paragraphs:
            para_words = para.split()
            if len(current_words) + len(para_words) <= max_words_per_chunk:
                current_words.extend(para_words)
            else:
                if current_words:
                    chunks.append(" ".join(current_words))
                # If paragraph itself is too long, split it
                if len(para_words) > max_words_per_chunk:
                    sub_chunks = self.chunk_text(para, chunk_size=max_words_per_chunk, overlap=50)
                    chunks.extend(sub_chunks[:-1])  # save last for potential merge
                    current_words = sub_chunks[-1].split() if sub_chunks else []
                else:
                    current_words = para_words

        if current_words:
            chunks.append(" ".join(current_words))

        return [c for c in chunks if c.strip()]
