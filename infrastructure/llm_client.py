"""
Unified async LLM client.
Primary: Anthropic Claude (if ANTHROPIC_API_KEY is set).
Secondary: OpenRouter (if OPENROUTER_API_KEY is set).
Fallback: Ollama (local).

Per-request provider preference:
    Users can pass preferred_provider in QueryRequest.
    Call set_preferred_provider("anthropic") at the start of a request
    and every LLM call in that request will use that provider automatically,
    without any function-signature changes elsewhere in the codebase.
"""

from __future__ import annotations
import asyncio
import contextvars
import os
import json
import logging
import aiohttp
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ── Per-request active LLM client ────────────────────────────────────────────
# Holds the tenant-configured LLM client for the current async request.
# Uses a ContextVar so 100 concurrent requests each get their own client
# without interfering with each other.
#
# Flow:
#   1. _run_query() in main.py calls get_llm_for_tenant(tenant_id)
#   2. It sets the result here via set_active_llm()
#   3. Every agent, pipeline and helper that calls get_llm() automatically
#      gets the tenant's client — no other file needs to change.
#
# Falls back to the global singleton if never set (dev / test mode).

_active_llm: contextvars.ContextVar = contextvars.ContextVar(
    "active_llm", default=None
)


def set_active_llm(client) -> None:
    """
    Set the LLM client for the current request context.
    Call once at the top of _run_query(); all downstream get_llm() calls
    in the same async task will return this client automatically.
    """
    _active_llm.set(client)


def get_active_llm():
    """Return the active LLM client for this request, or None if not set."""
    return _active_llm.get()


# ── Per-request provider preference (fallback auto-chain) ────────────────────
# Used internally when no tenant adapter is set (e.g. during startup or tests).
_preferred_provider: contextvars.ContextVar[str] = contextvars.ContextVar(
    "preferred_provider", default="auto"
)

VALID_PROVIDERS = {"anthropic", "openrouter", "openai", "ollama", "auto"}


def set_preferred_provider(provider: str) -> None:
    p = (provider or "auto").lower().strip()
    if p not in VALID_PROVIDERS:
        p = "auto"
    _preferred_provider.set(p)


def get_preferred_provider() -> str:
    return _preferred_provider.get()

# ── Ollama concurrency limiter ────────────────────────────────────────────────
# Local Ollama can only handle one request at a time efficiently.
# This semaphore serialises concurrent calls so they queue rather than pile up.
# Created lazily per event loop: on Python 3.9 a module-level Semaphore binds
# to the import-time loop and fails under any other loop with
# "Future attached to a different loop".
_ollama_semaphores: dict = {}


def _ollama_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _ollama_semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(1)
        _ollama_semaphores[loop] = sem
    return sem

# ── Prompt logger (firewall validation) ──────────────────────────────────────
_prompt_log: list[str] = []

def get_prompt_log() -> list[str]:
    """Return all prompts sent to the LLM (for firewall validation in tests)."""
    return _prompt_log

def clear_prompt_log():
    _prompt_log.clear()


class LLMClient:
    """
    Wraps Anthropic, OpenRouter and Ollama behind a single async interface.
    Priority: Anthropic → OpenRouter → Ollama.
    All calls go through complete() — which logs every prompt for firewall validation.
    """

    def __init__(
        self,
        openrouter_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.anthropic_key          = os.getenv("ANTHROPIC_API_KEY", "")
        self.anthropic_base         = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self.anthropic_fast_model   = os.getenv("ANTHROPIC_MODEL",        "claude-3-5-haiku-20241022")
        self.anthropic_strong_model = os.getenv("ANTHROPIC_STRONG_MODEL", "claude-3-5-sonnet-20241022")
        self.openrouter_key         = openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.openai_key             = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.openai_model           = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        # SiliconFlow — OpenAI-compatible, free tier (Qwen / DeepSeek models)
        self.siliconflow_key        = os.getenv("SILICONFLOW_API_KEY", "")
        self.siliconflow_base       = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        self.siliconflow_model      = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        self.siliconflow_strong     = os.getenv("SILICONFLOW_STRONG_MODEL", "Qwen/Qwen2.5-72B-Instruct")
        # Ollama — configurable at runtime
        self.ollama_url             = os.getenv("OLLAMA_BASE_URL", config.OLLAMA_BASE_URL)
        self.ollama_model           = os.getenv("OLLAMA_MODEL",    config.OLLAMA_MODEL)

    # ── Text completion ───────────────────────────────────────────────────────

    async def complete(
        self,
        prompt: str,
        system: str = "",
        provider: str = "auto",
        strong: bool = False,
    ) -> str:
        """
        Call the LLM. Logs the full prompt for firewall validation.

        provider: 'auto' (default) — checks the per-request ContextVar first,
                  then falls through the priority chain:
                  Anthropic → SiliconFlow → OpenRouter → Ollama.
                  Pass 'anthropic' | 'openrouter' | 'openai' | 'ollama' to force
                  a specific provider for this single call.
        strong:   use the stronger/slower model (for decomposition, fusion)
        """
        _prompt_log.append(f"[SYSTEM] {system}\n[USER] {prompt}")

        # If caller passed "auto", check the per-request context var first.
        # This lets users pick their provider via QueryRequest.preferred_provider
        # without touching any downstream function signatures.
        effective_provider = provider
        if effective_provider == "auto":
            effective_provider = get_preferred_provider()  # still "auto" if not set

        # Dispatch to the requested provider directly (skip auto-fallback chain)
        if effective_provider == "ollama":
            return await self._ollama_complete(prompt, system)
        if effective_provider == "anthropic":
            return await self._anthropic_complete(prompt, system, strong=strong)
        if effective_provider in ("openrouter", "openai"):
            return await self._openrouter_complete(prompt, system, strong=strong)
        if effective_provider == "siliconflow":
            return await self._siliconflow_complete(prompt, system, strong=strong)

        # effective_provider == "auto": try in priority order — Anthropic → SiliconFlow → OpenRouter → Ollama
        errors = []

        if self.anthropic_key:
            try:
                return await self._anthropic_complete(prompt, system, strong=strong)
            except Exception as e:
                logger.warning(f"Anthropic LLM failed ({e}), trying next provider")
                errors.append(str(e))

        if self.siliconflow_key:
            try:
                return await self._siliconflow_complete(prompt, system, strong=strong)
            except Exception as e:
                logger.warning(f"SiliconFlow LLM failed ({e}), trying next provider")
                errors.append(str(e))

        if self.openrouter_key:
            try:
                return await self._openrouter_complete(prompt, system, strong=strong)
            except Exception as e:
                logger.warning(f"OpenRouter LLM failed ({e}), falling back to Ollama")
                errors.append(str(e))

        try:
            return await self._ollama_complete(prompt, system)
        except Exception as e:
            logger.error(f"Ollama fallback also failed: {e}")
            errors.append(str(e))

        # ── Graceful degradation ───────────────────────────────────────────────
        # No LLM provider is reachable (no API keys set, Ollama not running).
        # Return a clear message so the API returns 200 instead of crashing with 500.
        # To enable full AI responses, set ANTHROPIC_API_KEY or OPENROUTER_API_KEY
        # in your .env file, or start Ollama locally.
        logger.warning(
            "[LLM] All providers unavailable — returning degraded response. "
            "Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY in .env to enable AI responses."
        )
        return (
            "⚠️ AI response unavailable: no LLM provider is configured. "
            "Please set ANTHROPIC_API_KEY or OPENROUTER_API_KEY in your .env file, "
            "or start Ollama locally, then restart the server."
        )

    async def _anthropic_complete(self, prompt: str, system: str, strong: bool = False) -> str:
        """Call Anthropic Messages API directly."""
        model = self.anthropic_strong_model if strong else self.anthropic_fast_model
        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: dict = {
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        base = self.anthropic_base.rstrip("/")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base}/v1/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["content"][0]["text"].strip()

    async def _openrouter_complete(self, prompt: str, system: str, strong: bool = False) -> str:
        model = config.OPENROUTER_STRONG_MODEL if strong else config.OPENROUTER_MODEL
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/rapid-ai",
            "X-Title": "RAPID",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": model, "messages": messages}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{config.OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()

    async def _siliconflow_complete(self, prompt: str, system: str, strong: bool = False) -> str:
        """Call SiliconFlow OpenAI-compatible API (free tier — Qwen / DeepSeek models)."""
        model = self.siliconflow_strong if strong else self.siliconflow_model
        headers = {
            "Authorization": f"Bearer {self.siliconflow_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": model, "messages": messages, "max_tokens": 2048}

        base = self.siliconflow_base.rstrip("/")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()

    async def _ollama_complete(self, prompt: str, system: str) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Use instance attributes so runtime config changes take effect
        base = self.ollama_url.rstrip("/")
        model = self.ollama_model
        payload = {"model": model, "messages": messages, "stream": False}

        async with _ollama_semaphore():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base}/chat/completions",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()

    # ── Embeddings ────────────────────────────────────────────────────────────

    async def embed(self, text: str) -> list[float]:
        """
        Generate embedding. Uses OpenAI if key available, otherwise falls back
        to a simple hash-based placeholder (for dev without OpenAI key).
        """
        if self.openai_key:
            return await self._openai_embed(text)

        # Dev fallback: use Anthropic-compatible embedding via sentence hashing
        # (not semantic — for dev/testing only when no OpenAI key)
        logger.warning("No OpenAI key — using deterministic placeholder embeddings (dev only)")
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        # Expand to 1536 dims via cyclic repetition
        raw = list(h) * (1536 // len(h) + 1)
        raw = raw[:1536]
        total = sum(raw) or 1
        return [v / total for v in raw]

    async def _openai_embed(self, text: str) -> list[float]:
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        payload = {"input": text, "model": config.EMBEDDING_MODEL}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["data"][0]["embedding"]

    # ── Convenience helpers ───────────────────────────────────────────────────

    async def json_complete(self, prompt: str, system: str = "", strong: bool = False) -> dict:
        """Complete and parse JSON response."""
        system_with_json = (system + "\nRespond with valid JSON only. No markdown fences.").strip()
        raw = await self.complete(prompt, system=system_with_json, strong=strong)
        # strip any accidental markdown fences
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)


# ── Singleton (global fallback) ───────────────────────────────────────────────
_client: Optional[LLMClient] = None

def _get_global_llm() -> LLMClient:
    """Always returns the global env-var-based singleton. Used as fallback."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def get_llm():
    """
    Return the LLM client for the current request.

    Priority:
      1. Tenant-configured client set via set_active_llm() in _run_query()
         → returns the org's chosen provider (Anthropic / OpenRouter / Ollama / etc.)
      2. Global env-var-based LLMClient singleton
         → used in dev, tests, and startup code that runs before any request

    Because this checks a ContextVar, every agent, pipeline and helper gets the
    right client automatically without any parameter changes.
    """
    active = _active_llm.get()
    if active is not None:
        return active
    return _get_global_llm()
