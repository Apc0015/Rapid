from __future__ import annotations
"""
EmbeddingService — unified local/online embedding interface.

Priority:
  1. Configured model for the department  (per-dept override)
  2. Ollama local model                   (offline — default nomic-embed-text)
  3. OpenAI text-embedding-3-small        (online fallback if OPENAI_API_KEY set)

All callers go through:
  await get_embedder().embed(text, dept_tag=None)

The service auto-detects which backend to use based on available keys + config.
"""

import asyncio
import logging
import os
from typing import List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# Known embedding dimensions per model
_DIMS: dict[str, int] = {
    "nomic-embed-text": 768,
    "nomic-embed-text:latest": 768,
    "all-minilm:l6-v2": 384,
    "all-minilm": 384,
    "locusai/all-minilm-l6-v2:latest": 384,
    "embeddinggemma:latest": 768,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

_DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"
_DEFAULT_DIM = 768

# Semaphore for Ollama embedding calls (same constraint as LLM calls).
# Created lazily per event loop: on Python 3.9 a module-level Semaphore binds
# to the import-time loop, so any other loop (asyncio.run in a script, a
# thread's loop) fails with "Future attached to a different loop" — this is
# what silently broke every batch ingestion.
_embed_semaphores: dict = {}


def _embed_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _embed_semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(2)  # embeddings are lighter, allow 2 concurrent
        _embed_semaphores[loop] = sem
    return sem


class EmbeddingService:
    """
    Async embedding service. Works fully offline via Ollama.
    Falls back to OpenAI when API key is present.
    """

    def __init__(self):
        self._ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        self._openai_key  = os.getenv("OPENAI_API_KEY", "")
        # Strip /v1 to get the raw Ollama base for /api/embeddings endpoint
        self._ollama_raw  = self._ollama_base.replace("/v1", "")

    def refresh(self):
        """Re-read env vars (called after runtime LLM reconfiguration)."""
        self._ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        self._openai_key  = os.getenv("OPENAI_API_KEY", "")
        self._ollama_raw  = self._ollama_base.replace("/v1", "")

    # ── Public API ────────────────────────────────────────────────────────────

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Embed a single string. Returns a float list.
        model: override the default embedding model (per-dept config passes this).
        """
        target_model = model or _DEFAULT_OLLAMA_EMBED_MODEL

        # Try Ollama first (always available offline)
        try:
            return await self._ollama_embed(text, target_model)
        except Exception as e:
            logger.warning(f"Ollama embed failed (model={target_model}): {e}")

        # Online fallback — OpenAI
        if self._openai_key:
            try:
                return await self._openai_embed(text)
            except Exception as e:
                logger.error(f"OpenAI embed fallback also failed: {e}")

        # Last resort — deterministic hash (dev only, not semantic)
        logger.error("All embedding backends failed — using hash placeholder (NOT semantic)")
        return _hash_embed(text, dim=_DIMS.get(target_model, _DEFAULT_DIM))

    async def embed_batch(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """Embed a list of texts concurrently."""
        tasks = [self.embed(t, model=model) for t in texts]
        return await asyncio.gather(*tasks)

    def dim_for_model(self, model: Optional[str] = None) -> int:
        """Return the embedding dimension for the given model."""
        m = model or _DEFAULT_OLLAMA_EMBED_MODEL
        return _DIMS.get(m, _DEFAULT_DIM)

    # ── Backends ──────────────────────────────────────────────────────────────

    async def _ollama_embed(self, text: str, model: str) -> List[float]:
        """
        Call Ollama /api/embeddings (native endpoint, not OpenAI-compatible).
        More reliable than /v1/embeddings for embedding-only models.
        """
        async with _embed_semaphore():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._ollama_raw}/api/embeddings",
                    json={"model": model, "prompt": text},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    embedding = data.get("embedding", [])
                    if not embedding:
                        raise ValueError(f"Empty embedding returned by Ollama model '{model}'")
                    return embedding

    async def _openai_embed(self, text: str, model: str = "text-embedding-3-small") -> List[float]:
        headers = {
            "Authorization": f"Bearer {self._openai_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json={"input": text, "model": model},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["data"][0]["embedding"]


# ── Hash fallback (non-semantic, dev only) ─────────────────────────────────────

def _hash_embed(text: str, dim: int = 768) -> List[float]:
    import hashlib
    h = hashlib.sha256(text.encode()).digest()
    raw = list(h) * (dim // len(h) + 1)
    raw = raw[:dim]
    total = sum(raw) or 1
    return [v / total for v in raw]


# ── Singleton ──────────────────────────────────────────────────────────────────

_embedder: Optional[EmbeddingService] = None


def get_embedder() -> EmbeddingService:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder
