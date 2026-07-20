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
        self._openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        self._openrouter_base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        # Strip /v1 to get the raw Ollama base for /api/embeddings endpoint
        self._ollama_raw  = self._ollama_base.replace("/v1", "")

    def refresh(self):
        """Re-read env vars (called after runtime LLM reconfiguration)."""
        self._ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        self._openai_key  = os.getenv("OPENAI_API_KEY", "")
        self._openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        self._openrouter_base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        self._ollama_raw  = self._ollama_base.replace("/v1", "")

    # ── Public API ────────────────────────────────────────────────────────────

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Embed a single string. Returns a float list.
        model: override the default embedding model (per-dept config passes this).
        """
        embedding, _ = await self.embed_with_metadata(text, model=model)
        return embedding

    async def embed_with_metadata(self, text: str, model: Optional[str] = None) -> tuple[List[float], str]:
        """Return an embedding and the backend label used to produce it."""
        target_model = model or _DEFAULT_OLLAMA_EMBED_MODEL

        # Try Ollama first (always available offline)
        try:
            return await self._ollama_embed(text, target_model), "ollama"
        except Exception as e:
            logger.warning(f"Ollama embed failed (model={target_model}): {e}")

        if self._openrouter_key:
            try:
                openrouter_model = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")
                return await self._openrouter_embed(text, openrouter_model), "openrouter"
            except Exception as e:
                logger.error(f"OpenRouter embed fallback failed: {e}")

        # Online fallback — OpenAI
        if self._openai_key:
            try:
                return await self._openai_embed(text), "openai"
            except Exception as e:
                logger.error(f"OpenAI embed fallback also failed: {e}")

        if os.getenv("RAPID_ENV", "development") == "production":
            raise RuntimeError("No production embedding provider is available")
        logger.warning("All embedding backends failed — using local token-hash retrieval for development")
        return _hash_embed(text, dim=_DIMS.get(target_model, _DEFAULT_DIM)), "local_token_hash"

    async def embed_batch(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """Embed a list of texts concurrently."""
        embeddings, _ = await self.embed_batch_with_metadata(texts, model=model)
        return embeddings

    async def embed_batch_with_metadata(self, texts: List[str], model: Optional[str] = None) -> tuple[List[List[float]], str]:
        if not texts:
            return [], "none"
        target_model = model or _DEFAULT_OLLAMA_EMBED_MODEL
        first, backend = await self.embed_with_metadata(texts[0], model=target_model)
        if len(texts) == 1:
            return [first], backend
        if backend == "ollama":
            remaining = await asyncio.gather(*(self._ollama_embed(text, target_model) for text in texts[1:]))
        elif backend == "openrouter":
            openrouter_model = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")
            remaining = await asyncio.gather(*(self._openrouter_embed(text, openrouter_model) for text in texts[1:]))
        elif backend == "openai":
            remaining = await asyncio.gather(*(self._openai_embed(text) for text in texts[1:]))
        else:
            dim = len(first)
            remaining = [_hash_embed(text, dim=dim) for text in texts[1:]]
        return [first, *remaining], backend

    async def embed_for_tenant(self, text: str, tenant_id: str, model: Optional[str] = None) -> tuple[List[float], str]:
        embeddings, backend = await self.embed_batch_for_tenant([text], tenant_id, model=model)
        return embeddings[0], backend

    async def embed_batch_for_tenant(self, texts: List[str], tenant_id: str, model: Optional[str] = None) -> tuple[List[List[float]], str]:
        """Use the model provider selected in the tenant admin portal."""
        if not texts:
            return [], "none"
        from infrastructure.secret_vault import get_secret_vault
        from infrastructure.tenant_admin_store import get_tenant_admin_store

        runtime = get_tenant_admin_store().active_model_runtime(tenant_id)
        provider = runtime["provider"]
        from infrastructure.tenant_policy import get_tenant_policy
        get_tenant_policy(tenant_id).require_provider(provider)
        try:
            if provider == "ollama":
                target_model = model or os.getenv("OLLAMA_EMBEDDING_MODEL", _DEFAULT_OLLAMA_EMBED_MODEL)
                tasks = [self._ollama_embed_at(text, target_model, runtime["endpoint"]) for text in texts]
                return await asyncio.gather(*tasks), "tenant_ollama"
            if provider == "openrouter":
                key = get_secret_vault().resolve(runtime["credential_ref"], tenant_id)
                target_model = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")
                tasks = [self._openrouter_embed_at(text, target_model, runtime["endpoint"], key) for text in texts]
                return await asyncio.gather(*tasks), "tenant_openrouter"
            raise RuntimeError(f"Unsupported tenant embedding provider: {provider}")
        except Exception:
            if os.getenv("RAPID_ENV", "development") == "production":
                raise
            dim = _DIMS.get(model or _DEFAULT_OLLAMA_EMBED_MODEL, _DEFAULT_DIM)
            logger.warning("Tenant embedding provider unavailable — using local token-hash retrieval for development")
            return [_hash_embed(text, dim=dim) for text in texts], "local_token_hash"

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
        return await self._ollama_embed_at(text, model, self._ollama_raw)

    async def _ollama_embed_at(self, text: str, model: str, endpoint: str) -> List[float]:
        raw_endpoint = endpoint.rstrip("/").removesuffix("/v1")
        async with _embed_semaphore():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{raw_endpoint}/api/embeddings",
                    json={"model": model, "prompt": text},
                    timeout=aiohttp.ClientTimeout(total=max(2, int(os.getenv("RAPID_EMBEDDING_TIMEOUT_SECONDS", "10")))),
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

    async def _openrouter_embed(self, text: str, model: str) -> List[float]:
        return await self._openrouter_embed_at(text, model, self._openrouter_base, self._openrouter_key)

    async def _openrouter_embed_at(self, text: str, model: str, endpoint: str, api_key: str) -> List[float]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("RAPID_PUBLIC_URL", "https://rapid.local"),
            "X-Title": "RAPID Organization OS",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{endpoint.rstrip('/')}/embeddings",
                headers=headers,
                json={"input": text, "model": model},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["data"][0]["embedding"]


# ── Hash fallback (non-semantic, dev only) ─────────────────────────────────────

def _hash_embed(text: str, dim: int = 768) -> List[float]:
    """Deterministic token hashing for useful local lexical similarity in development."""
    import hashlib
    import math
    import re

    vector = [0.0] * dim
    tokens = re.findall(r"[a-zA-Z0-9_/-]+", text.lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[slot] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


# ── Singleton ──────────────────────────────────────────────────────────────────

_embedder: Optional[EmbeddingService] = None


def get_embedder() -> EmbeddingService:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder
