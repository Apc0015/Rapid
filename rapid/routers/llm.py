"""
routers/llm.py — LLM provider configuration (admin only, runtime).

  POST /llm/configure   — Switch provider / update API key without restart
  GET  /llm/models      — List available models for a provider
  GET  /llm/status      — Show which providers are currently configured
"""

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from .deps import require_admin

router = APIRouter(prefix="/llm", tags=["llm"])
logger = logging.getLogger("rapid.llm")


# ── Configure ─────────────────────────────────────────────────────────────────

class LLMConfigRequest(BaseModel):
    provider:     str                    # anthropic | openrouter | openai | ollama
    api_key:      Optional[str] = None   # not needed for Ollama
    model:        Optional[str] = None
    ollama_url:   Optional[str] = None
    ollama_model: Optional[str] = None


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
                llm.anthropic_fast_model   = req.model
                llm.anthropic_strong_model = req.model
                env_updates["ANTHROPIC_MODEL"] = req.model
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
