"""
routers/llm.py — LLM provider configuration (admin only, runtime).

  POST /llm/configure              — Switch global provider / update API key without restart
  GET  /llm/models                 — List live models for a provider (hits the API)
  GET  /llm/status                 — Show which providers are currently configured

  ── Phase 4 additions ──
  GET  /llm/registry/providers     — List all supported providers from registry
  GET  /llm/registry/models        — List catalog models (optionally filter by provider)
  GET  /tenants/{tenant_id}/llm    — Get a tenant's LLM config
  PUT  /tenants/{tenant_id}/llm    — Update a tenant's LLM config (validated against registry)
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from .deps import require_admin, get_current_user

router = APIRouter(prefix="/llm", tags=["llm"])
logger = logging.getLogger("rapid.llm")


# ── Providers list ───────────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers(current_user: dict = Depends(get_current_user)):
    """List all configured LLM providers and their availability status."""
    from infrastructure.llm_client import get_llm
    llm = get_llm()

    anthropic_key  = os.getenv("ANTHROPIC_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    openai_key     = os.getenv("OPENAI_API_KEY", "")

    if anthropic_key:
        active = "anthropic"
    elif openrouter_key:
        active = "openrouter"
    else:
        active = "ollama"

    return {
        "active": active,
        "providers": [
            {
                "name":      "anthropic",
                "available": bool(anthropic_key),
                "model":     llm.anthropic_fast_model if anthropic_key else None,
                "note":      None if anthropic_key else "ANTHROPIC_API_KEY not set",
            },
            {
                "name":      "openrouter",
                "available": bool(openrouter_key),
                "model":     None,
                "note":      None if openrouter_key else "OPENROUTER_API_KEY not set",
            },
            {
                "name":      "openai",
                "available": bool(openai_key),
                "model":     os.getenv("OPENAI_MODEL", "text-embedding-3-small"),
                "note":      None if openai_key else "OPENAI_API_KEY not set (used for embeddings)",
            },
            {
                "name":      "ollama",
                "available": True,
                "model":     llm.ollama_model,
                "note":      f"Local at {llm.ollama_url}",
            },
        ],
    }


# ── Health check ──────────────────────────────────────────────────────────────

@router.get("/health")
async def llm_health(current_user: dict = Depends(get_current_user)):
    """Test the active LLM provider with a minimal prompt and report latency."""
    from infrastructure.llm_client import get_llm
    llm = get_llm()

    anthropic_key  = os.getenv("ANTHROPIC_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    if anthropic_key:
        provider_name = "anthropic"
        model_name    = llm.anthropic_fast_model
    elif openrouter_key:
        provider_name = "openrouter"
        model_name    = "openrouter-default"
    else:
        provider_name = "ollama"
        model_name    = llm.ollama_model

    start = time.monotonic()
    try:
        await llm.complete("ping", system="Reply with exactly one word: pong")
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"status": "ok", "provider": provider_name, "model": model_name,
                "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"status": "error", "provider": provider_name, "model": model_name,
                "latency_ms": latency_ms, "error": str(e)}


# ── Prompt test ───────────────────────────────────────────────────────────────

class TestPromptRequest(BaseModel):
    prompt: str
    system: Optional[str] = None


@router.post("/test")
async def test_prompt(req: TestPromptRequest, current_user: dict = Depends(require_admin)):
    """Test any prompt against the current LLM. Admin only."""
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be empty")
    from infrastructure.llm_client import get_llm
    llm = get_llm()
    start = time.monotonic()
    try:
        response = await llm.complete(req.prompt, system=req.system or "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")
    latency_ms = int((time.monotonic() - start) * 1000)
    return {"response": response, "latency_ms": latency_ms}


# ── Configure ─────────────────────────────────────────────────────────────────

class LLMConfigRequest(BaseModel):
    provider:      str                    # anthropic | openrouter | openai | ollama
    api_key:       Optional[str] = None   # not needed for Ollama
    model:         Optional[str] = None   # fast/default model for this provider
    strong_model:  Optional[str] = None   # stronger model (used for decomposition + fusion)
    ollama_url:    Optional[str] = None
    ollama_model:  Optional[str] = None


def _persist_env(updates: dict) -> None:
    """Write key=value pairs to .env, creating the file if it doesn't exist."""
    env_path = Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    for env_var, env_val in updates.items():
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{env_var}="):
                new_lines.append(f"{env_var}={env_val}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"{env_var}={env_val}")
        lines = new_lines
    env_path.write_text("\n".join(lines) + "\n")


@router.post("/configure")
async def llm_configure(req: LLMConfigRequest, current_user: dict = Depends(require_admin)):
    """Admin-only. Set an LLM provider at runtime without restarting."""
    user_id = current_user["sub"]

    from infrastructure.llm_client import get_llm
    import config as cfg
    llm = get_llm()
    env_updates: dict = {}

    if req.provider == "ollama":
        raw_url = (req.ollama_url or "http://localhost:11434").rstrip("/")
        # Normalise: always store the /v1 base so _ollama_complete works correctly
        url = raw_url if raw_url.endswith("/v1") else raw_url + "/v1"
        model = req.ollama_model or req.model or "llama3.2"
        llm.ollama_url   = url
        llm.ollama_model = model
        cfg.OLLAMA_BASE_URL = url
        cfg.OLLAMA_MODEL    = model
        env_updates["OLLAMA_BASE_URL"] = url
        env_updates["OLLAMA_MODEL"]    = model
        message = f"Ollama configured — {url}  model: {model}"

    else:
        env_key_map = {
            "anthropic":  "ANTHROPIC_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "openai":     "OPENAI_API_KEY",
        }
        if req.provider not in env_key_map:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider '{req.provider}'. Use: anthropic, openrouter, openai, ollama"
            )
        if not req.api_key:
            raise HTTPException(status_code=400, detail="api_key is required for this provider")

        env_var = env_key_map[req.provider]
        os.environ[env_var] = req.api_key
        if req.provider == "anthropic":
            llm.anthropic_key = req.api_key
            if req.model:
                llm.anthropic_fast_model = req.model
                env_updates["ANTHROPIC_MODEL"] = req.model
            if req.strong_model:
                llm.anthropic_strong_model = req.strong_model
                env_updates["ANTHROPIC_STRONG_MODEL"] = req.strong_model
        elif req.provider == "openrouter":
            llm.openrouter_key = req.api_key
            if req.model:
                cfg.OPENROUTER_MODEL        = req.model
                cfg.OPENROUTER_STRONG_MODEL = req.model
                env_updates["OPENROUTER_MODEL"] = req.model
        elif req.provider == "openai":
            llm.openai_key = req.api_key
            if req.model:
                env_updates["OPENAI_MODEL"] = req.model
        env_updates[env_var] = req.api_key
        model_note = f"  model: {req.model}" if req.model else ""
        message = f"{req.provider.capitalize()} configured — key saved.{model_note}"

    _persist_env(env_updates)
    logger.info(f"[llm/configure] Admin {user_id} configured provider={req.provider}")
    return {"status": "configured", "provider": req.provider, "message": message}


# ── Models ────────────────────────────────────────────────────────────────────

@router.get("/models")
async def llm_models(provider: str, api_key: str = "", ollama_url: str = "",
                     current_user: dict = Depends(require_admin)):
    """Admin-only. Fetch available models for a given provider."""
    import aiohttp

    try:
        if provider == "anthropic":
            key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                raise HTTPException(status_code=400, detail="No Anthropic API key provided")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    r.raise_for_status()
                    data = await r.json()
                    models = sorted([m["id"] for m in data.get("data", [])
                                     if "claude" in m["id"].lower()], reverse=True)
                    return {"provider": "anthropic", "models": models}

        elif provider == "openai":
            key = api_key or os.environ.get("OPENAI_API_KEY", "")
            if not key:
                raise HTTPException(status_code=400, detail="No OpenAI API key provided")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    r.raise_for_status()
                    data = await r.json()
                    models = sorted([
                        m["id"] for m in data.get("data", [])
                        if any(p in m["id"] for p in ("gpt-4", "gpt-3.5", "o1", "o3", "o4"))
                    ], reverse=True)
                    return {"provider": "openai", "models": models}

        elif provider == "openrouter":
            key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
            if not key:
                raise HTTPException(status_code=400, detail="No OpenRouter API key provided")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    r.raise_for_status()
                    data = await r.json()
                    return {"provider": "openrouter", "models": sorted(m["id"] for m in data.get("data", []))}

        elif provider == "ollama":
            base = (ollama_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")).replace("/v1", "")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{base}/api/tags", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    r.raise_for_status()
                    data = await r.json()
                    return {"provider": "ollama", "models": [m["name"] for m in data.get("models", [])]}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach {provider}: {str(e)}")


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def llm_status(current_user: dict = Depends(require_admin)):
    """Admin-only. Show which LLM providers are currently configured."""
    from infrastructure.llm_client import get_llm
    llm = get_llm()
    return {
        "anthropic":  bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY", "").strip()),
        "openai":     bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "ollama":     bool(getattr(llm, "ollama_url", "") or os.environ.get("OLLAMA_BASE_URL", "")),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4: Registry endpoints — catalog of all supported providers & models
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/registry/providers")
async def registry_providers(current_user: dict = Depends(get_current_user)):
    """
    List all LLM providers supported by RAPID with their specs:
    API style, required config keys, default models, and cost tiers.
    """
    from infrastructure.llm_registry import list_providers
    return {"providers": list_providers()}


@router.get("/registry/models")
async def registry_models(
    provider: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    List all known models (optionally scoped to one provider).
    Returns context windows, cost tiers, and capabilities from the catalog.
    """
    from infrastructure.llm_registry import list_models
    models = list_models(provider_id=provider)
    if provider and not models:
        from infrastructure.llm_registry import PROVIDER_REGISTRY
        if provider not in PROVIDER_REGISTRY:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown provider '{provider}'. "
                       f"Valid: {', '.join(PROVIDER_REGISTRY.keys())}"
            )
    return {"provider": provider, "models": models, "count": len(models)}


@router.get("/registry/providers/{provider_id}/recommended")
async def registry_recommended_config(
    provider_id: str,
    strong: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """
    Return a recommended config skeleton for a provider.
    Useful for admin UIs and onboarding flows.
    """
    from infrastructure.llm_registry import get_recommended_config, PROVIDER_REGISTRY
    if provider_id not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_id}'")
    return {
        "provider_id": provider_id,
        "recommended_config": get_recommended_config(provider_id, use_strong=strong),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4: Tenant LLM config endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TenantLLMConfigRequest(BaseModel):
    provider:    str                    # e.g. "anthropic", "openai"
    model:       str                    # exact model_id
    llm_config:  dict = {}              # api_key, base_url, etc.


def _require_tenant_scope(tenant_id: str, current_user: dict) -> None:
    if tenant_id != str(current_user.get("tenant_id") or "default"):
        raise HTTPException(status_code=404, detail="Tenant not found")


@router.get("/tenants/{tenant_id}/llm")
async def get_tenant_llm_config(
    tenant_id: str,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Get the current LLM config for a tenant.
    The api_key is redacted (shown as "**set**" or "**not set**").
    """
    _require_tenant_scope(tenant_id, current_user)
    from infrastructure.tenant_manager import get_tenant_manager
    tm = get_tenant_manager()
    tenant = tm.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    import json
    raw_cfg = tenant.get("llm_config") or "{}"
    cfg = json.loads(raw_cfg) if isinstance(raw_cfg, str) else (raw_cfg or {})

    # Redact API key
    if "api_key" in cfg:
        cfg["api_key"] = "**set**"

    return {
        "tenant_id":    tenant_id,
        "llm_provider": tenant.get("llm_provider", "anthropic"),
        "llm_model":    tenant.get("llm_model", "claude-3-5-haiku-20241022"),
        "llm_config":   cfg,
    }


@router.put("/tenants/{tenant_id}/llm")
async def update_tenant_llm_config(
    tenant_id: str,
    req: TenantLLMConfigRequest,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Update the LLM configuration for a specific tenant.
    Validates provider and model against the registry before saving.
    Invalidates the in-memory adapter cache for this tenant.
    """
    _require_tenant_scope(tenant_id, current_user)
    from infrastructure.llm_registry import validate_tenant_llm_config, PROVIDER_REGISTRY
    from infrastructure.tenant_manager import get_tenant_manager
    from infrastructure.llm_adapter import invalidate_tenant_adapter
    import json

    # 1. Validate against registry
    errors = validate_tenant_llm_config(req.provider, req.model, req.llm_config)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": errors, "hint": f"Valid providers: {list(PROVIDER_REGISTRY.keys())}"}
        )

    # 2. Check tenant exists
    tm = get_tenant_manager()
    tenant = tm.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    # 3. Persist to tenants table
    tm.update_tenant(
        tenant_id,
        llm_provider=req.provider,
        llm_model=req.model,
        llm_config=json.dumps(req.llm_config),
    )

    # 4. Invalidate adapter cache so next call gets fresh config
    invalidate_tenant_adapter(tenant_id)

    logger.info(
        f"[llm/tenant] Admin {current_user['sub']} updated LLM config for tenant '{tenant_id}': "
        f"{req.provider}/{req.model}"
    )

    return {
        "status":     "updated",
        "tenant_id":  tenant_id,
        "provider":   req.provider,
        "model":      req.model,
        "message":    f"Tenant '{tenant_id}' now using {req.provider}/{req.model}",
    }
