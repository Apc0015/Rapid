"""
Unified async LLM client.
Primary: Anthropic Claude (if ANTHROPIC_API_KEY is set).
Secondary: OpenRouter (if OPENROUTER_API_KEY is set).
Fallback: Ollama (local).
"""

from __future__ import annotations
import asyncio
import os
import json
import logging
import aiohttp
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ── Ollama concurrency limiter ────────────────────────────────────────────────
# Local Ollama can only handle one request at a time efficiently.
# This semaphore serialises concurrent calls so they queue rather than pile up.
_ollama_semaphore = asyncio.Semaphore(1)

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
        self.anthropic_fast_model   = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
        self.anthropic_strong_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        self.openrouter_key         = openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.openai_key             = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.openai_model           = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
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
        provider: 'auto' (default — tries Anthropic → OpenRouter → Ollama)
                  'anthropic' | 'openrouter' | 'ollama'
        strong: use the stronger/slower model (for decomposition, fusion)
        """
        _prompt_log.append(f"[SYSTEM] {system}\n[USER] {prompt}")

        # Explicit provider requested
        if provider == "ollama":
            return await self._ollama_complete(prompt, system)
        if provider == "anthropic":
            return await self._anthropic_complete(prompt, system, strong=strong)
        if provider == "openrouter":
            return await self._openrouter_complete(prompt, system, strong=strong)

        # Auto: try in priority order
        errors = []

        if self.anthropic_key:
            try:
                return await self._anthropic_complete(prompt, system, strong=strong)
            except Exception as e:
                logger.warning(f"Anthropic LLM failed ({e}), trying next provider")
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
            raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")

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

    async def _ollama_complete(self, prompt: str, system: str) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Use instance attributes so runtime config changes take effect
        base = self.ollama_url.rstrip("/")
        model = self.ollama_model
        payload = {"model": model, "messages": messages, "stream": False}

        async with _ollama_semaphore:
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


# ── Singleton ─────────────────────────────────────────────────────────────────
_client: Optional[LLMClient] = None

def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
