"""
infrastructure/llm_adapter.py — Per-Tenant LLM Adapter.

Replaces the global get_llm() singleton with a tenant-aware routing layer.
Each tenant can configure their own LLM provider, model, and API key via
the tenants.llm_provider / llm_model / llm_config columns.

Call flow
─────────
  1. get_llm_for_tenant(tenant_id) reads tenant row from rapid.db
  2. Looks up provider spec in llm_registry.PROVIDER_REGISTRY
  3. Returns a TenantLLMAdapter that wraps LLMClient with the right config
  4. Adapters are cached per-tenant (invalidated on config update)

If no tenant config is set, falls back to the global env-var-based LLMClient.

Usage
─────
    # In any agent or router:
    from infrastructure.llm_adapter import get_llm_for_tenant

    llm = await get_llm_for_tenant(tenant_id)
    answer = await llm.complete(prompt, system=system_prompt)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from typing import Optional

import aiohttp

import config
from infrastructure.llm_client import LLMClient, get_llm
from infrastructure.llm_registry import (
    PROVIDER_REGISTRY,
    APIStyle,
    get_provider,
    get_model,
)

logger = logging.getLogger(__name__)


# ── Tenant LLM Adapter ────────────────────────────────────────────────────────

class TenantLLMAdapter:
    """
    A thin wrapper around the provider HTTP calls, configured for one tenant.

    Mirrors the LLMClient.complete() / json_complete() / embed() interface so
    call sites don't need to know whether they're using a global or per-tenant
    client.

    provider_id  — e.g. "anthropic", "openai", "ollama"
    model_id     — the exact model string sent to the API
    cfg          — tenant's llm_config dict (api_key, base_url, etc.)
    api_style    — APIStyle.ANTHROPIC_MESSAGES | OPENAI_CHAT | GOOGLE_GENERATE
    strong_model — alternative model for strong=True calls (falls back to model_id)
    """

    def __init__(
        self,
        tenant_id:    str,
        provider_id:  str,
        model_id:     str,
        cfg:          dict,
        api_style:    str,
        strong_model: Optional[str] = None,
    ):
        self.tenant_id    = tenant_id
        self.provider_id  = provider_id
        self.model_id     = model_id
        self.cfg          = cfg
        self.api_style    = api_style
        self.strong_model = strong_model or model_id

        # Pre-resolve connection details
        provider = get_provider(provider_id)
        self._base_url = cfg.get("base_url") or (provider.base_url if provider else "")
        self._api_key  = cfg.get("api_key", "")

    # ── Public interface (mirrors LLMClient) ──────────────────────────────────

    async def complete(
        self,
        prompt: str,
        system: str = "",
        strong: bool = False,
        **kwargs,
    ) -> str:
        """Call the configured provider and return the completion string."""
        model = self.strong_model if strong else self.model_id
        try:
            if self.api_style == APIStyle.ANTHROPIC_MESSAGES:
                return await self._anthropic_complete(prompt, system, model)
            elif self.api_style == APIStyle.OPENAI_CHAT:
                return await self._openai_complete(prompt, system, model)
            elif self.api_style == APIStyle.GOOGLE_GENERATE:
                return await self._google_complete(prompt, system, model)
            else:
                raise ValueError(f"Unknown api_style: {self.api_style}")
        except Exception as e:
            logger.error(
                f"[TenantLLM:{self.tenant_id}] {self.provider_id}/{model} failed: {e}"
            )
            raise

    async def json_complete(
        self,
        prompt: str,
        system: str = "",
        strong: bool = False,
    ) -> dict:
        """Complete and parse JSON response."""
        system_with_json = (system + "\nRespond with valid JSON only. No markdown fences.").strip()
        raw = await self.complete(prompt, system=system_with_json, strong=strong)
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)

    async def embed(self, text: str) -> list[float]:
        """
        Embeddings — delegate to global LLMClient for now (OpenAI embeddings).
        Tenant-specific embedding providers can be added in Phase 7 (vector search).
        """
        return await get_llm().embed(text)

    # ── Provider implementations ──────────────────────────────────────────────

    async def _anthropic_complete(self, prompt: str, system: str, model: str) -> str:
        api_key = self._api_key or config.__dict__.get("ANTHROPIC_API_KEY", "")
        # Also check env if not in tenant config
        if not api_key:
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY", "")

        if not api_key:
            raise ValueError(f"Tenant '{self.tenant_id}': anthropic api_key not configured")

        base = self._base_url.rstrip("/")
        headers = {
            "x-api-key": api_key,
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

    async def _openai_complete(self, prompt: str, system: str, model: str) -> str:
        """
        Handles: openai, openrouter, azure, ollama, siliconflow
        (all are OpenAI-chat-compatible).
        """
        import os

        api_key = self._api_key
        base    = self._base_url.rstrip("/")

        # Provider-specific defaults when tenant hasn't set api_key
        if not api_key:
            if self.provider_id == "openrouter":
                api_key = os.getenv("OPENROUTER_API_KEY", "")
            elif self.provider_id == "openai":
                api_key = os.getenv("OPENAI_API_KEY", "")
            elif self.provider_id == "siliconflow":
                api_key = os.getenv("SILICONFLOW_API_KEY", "")
            elif self.provider_id == "azure":
                api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
            # ollama: no key needed

        headers: dict = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # OpenRouter extra headers
        if self.provider_id == "openrouter":
            headers["HTTP-Referer"] = self.cfg.get("site_url", "https://github.com/rapid-ai")
            headers["X-Title"]      = self.cfg.get("site_name", "RAPID")

        # Azure uses a different URL pattern
        if self.provider_id == "azure":
            deployment = self.cfg.get("deployment_name", model)
            api_version = self.cfg.get("api_version", "2024-02-01")
            endpoint    = self.cfg.get("endpoint", base).rstrip("/")
            url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
            # Azure uses api-key header instead of Bearer
            headers.pop("Authorization", None)
            headers["api-key"] = api_key
        else:
            url = f"{base}/chat/completions"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {"model": model, "messages": messages, "max_tokens": 2048}

        timeout = aiohttp.ClientTimeout(total=300 if self.provider_id == "ollama" else 90)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()

    async def _google_complete(self, prompt: str, system: str, model: str) -> str:
        import os
        api_key = self._api_key or os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError(f"Tenant '{self.tenant_id}': google api_key not configured")

        base = self._base_url.rstrip("/")
        url  = f"{base}/models/{model}:generateContent?key={api_key}"

        contents = []
        if system:
            # Gemini uses "user" role for system context via system_instruction
            pass

        contents.append({
            "role": "user",
            "parts": [{"text": f"{system}\n\n{prompt}".strip() if system else prompt}],
        })

        payload: dict = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 2048},
        }
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
            # Reset contents to just the user message
            payload["contents"] = [{"role": "user", "parts": [{"text": prompt}]}]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── Tenant config loader ──────────────────────────────────────────────────────

def _load_tenant_llm_config(tenant_id: str) -> Optional[dict]:
    """
    Read llm_provider / llm_model / llm_config from the tenants table.
    Returns None if tenant not found.
    """
    try:
        conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT llm_provider, llm_model, llm_config FROM tenants WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        conn.close()

        if not row:
            return None

        raw_cfg = row["llm_config"]
        cfg = json.loads(raw_cfg) if raw_cfg else {}

        return {
            "provider_id": row["llm_provider"] or "anthropic",
            "model_id":    row["llm_model"]    or "claude-3-5-haiku-20241022",
            "cfg":         cfg,
        }
    except Exception as e:
        logger.warning(f"[LLMAdapter] Could not load tenant config for '{tenant_id}': {e}")
        return None


# ── Adapter cache ─────────────────────────────────────────────────────────────
# LRU-style dict: tenant_id → TenantLLMAdapter
# Invalidated explicitly when tenant LLM config changes.

_adapter_cache: dict[str, TenantLLMAdapter] = {}
_cache_lock = asyncio.Lock()


def invalidate_tenant_adapter(tenant_id: str) -> None:
    """Call this after updating a tenant's LLM config to flush the cache."""
    _adapter_cache.pop(tenant_id, None)
    logger.debug(f"[LLMAdapter] Cache invalidated for tenant '{tenant_id}'")


# ── Public API ────────────────────────────────────────────────────────────────

async def get_llm_for_tenant(tenant_id: str = "default") -> "LLMClient | TenantLLMAdapter":
    """
    Return the LLM client configured for this tenant.

    - If tenant has custom llm_config in DB → returns TenantLLMAdapter
    - If tenant not found or config missing → falls back to global get_llm()
    - Adapters are cached after first build (invalidate with invalidate_tenant_adapter)
    """
    # Fast path: cache hit
    if tenant_id in _adapter_cache:
        return _adapter_cache[tenant_id]

    # Load from DB
    tenant_cfg = _load_tenant_llm_config(tenant_id)

    if not tenant_cfg:
        logger.debug(f"[LLMAdapter] No tenant config for '{tenant_id}', using global LLM")
        return get_llm()

    provider_id = tenant_cfg["provider_id"]
    model_id    = tenant_cfg["model_id"]
    cfg         = tenant_cfg["cfg"]

    provider = get_provider(provider_id)
    if not provider:
        logger.warning(
            f"[LLMAdapter] Tenant '{tenant_id}' has unknown provider '{provider_id}', "
            f"falling back to global LLM"
        )
        return get_llm()

    # Resolve fast/strong models
    fm = provider.fast_model
    sm = provider.strong_model
    strong_model = cfg.get("strong_model") or (sm.model_id if sm else model_id)
    # Strip __custom__ sentinel
    if strong_model == "__custom__":
        strong_model = model_id

    adapter = TenantLLMAdapter(
        tenant_id    = tenant_id,
        provider_id  = provider_id,
        model_id     = model_id,
        cfg          = cfg,
        api_style    = provider.api_style,
        strong_model = strong_model,
    )

    _adapter_cache[tenant_id] = adapter
    logger.info(
        f"[LLMAdapter] Built adapter for tenant '{tenant_id}': "
        f"{provider_id}/{model_id}"
    )
    return adapter


def get_llm_for_tenant_sync(tenant_id: str = "default") -> "LLMClient | TenantLLMAdapter":
    """
    Synchronous version for use in non-async contexts (e.g. agent __init__).
    No caching — use get_llm_for_tenant() (async) in hot paths.
    """
    tenant_cfg = _load_tenant_llm_config(tenant_id)
    if not tenant_cfg:
        return get_llm()

    provider_id = tenant_cfg["provider_id"]
    model_id    = tenant_cfg["model_id"]
    cfg         = tenant_cfg["cfg"]

    provider = get_provider(provider_id)
    if not provider:
        return get_llm()

    sm = provider.strong_model
    strong_model = cfg.get("strong_model") or (sm.model_id if sm else model_id)
    if strong_model == "__custom__":
        strong_model = model_id

    return TenantLLMAdapter(
        tenant_id    = tenant_id,
        provider_id  = provider_id,
        model_id     = model_id,
        cfg          = cfg,
        api_style    = provider.api_style,
        strong_model = strong_model,
    )
