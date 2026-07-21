"""
orgos/reasoning.py — one governed LLM call from a synchronous orgos handler.

orgos handlers are synchronous; the LLM path is async and tenant-scoped. This
runs a single governed synthesis on a dedicated event loop in a worker thread
(same bridge pattern as orgos/knowledge.py), so a specialist can turn structured
state into a real drafted plan/strategy.

Degradation contract (matches knowledge.py): returns None when the model is
unavailable (Ollama down, timeout, import failure). Callers MUST record an
honest fallback — never present a fabricated plan as if the model produced it.
The call is a single deterministic synthesis, not a multi-agent fan-out.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_TIMEOUT = 120.0  # local Ollama on CPU can be slow; cap it hard


def synthesize(prompt: str, tenant_id: str = "default") -> Optional[dict]:
    """Make one governed LLM call bound to this tenant's configured model.

    Returns {"text": str, "confidence": float, "citations": [str]} or None when
    the model backend is unavailable. Empty output is treated as unavailable.
    """
    if not prompt.strip():
        return None

    async def _run() -> dict:
        from infrastructure.db_master import set_current_tenant
        from infrastructure.llm_adapter import get_llm_for_tenant
        from infrastructure.llm_client import set_active_llm
        from shared import spokesperson

        set_current_tenant(tenant_id)
        tenant_llm = await get_llm_for_tenant(tenant_id)
        set_active_llm(tenant_llm)
        result = await spokesperson.handle_general(prompt, "", "")
        return {
            "text": getattr(result, "summary", "") or "",
            "confidence": float(getattr(result, "confidence", 0.0) or 0.0),
            "citations": list(getattr(result, "citations", []) or []),
        }

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            out = ex.submit(asyncio.run, _run()).result(timeout=_TIMEOUT)
        return out if out.get("text", "").strip() else None
    except Exception as e:
        logger.warning("orgos synthesis unavailable for tenant %s (%s)", tenant_id, e)
        return None
