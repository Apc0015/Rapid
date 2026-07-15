"""
routers/packs.py — Industry Pack Selection & Customization API

Endpoints
─────────
  GET  /packs                        → List all available industry packs
  GET  /packs/current                → Get the active pack for current tenant
  GET  /packs/history                → All packs ever applied to this tenant
  GET  /packs/{pack_id}              → Full pack definition (KPIs, risks, onboarding)
  GET  /packs/{pack_id}/onboarding   → Ordered onboarding steps for a pack
  POST /packs/{pack_id}/apply        → Apply a pack to the current tenant
  POST /packs/{pack_id}/customize    → Apply custom overrides on top of active pack
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.deps import get_current_user
from industry_packs.base_pack import get_pack_registry, get_tenant_pack, list_tenant_packs

router = APIRouter(prefix="/packs", tags=["industry-packs"])
logger = logging.getLogger("rapid.packs_router")


def _get_tenant(current_user: dict) -> str:
    return current_user.get("tenant_id") or current_user.get("sub", "default")


def _require_admin(current_user: dict) -> None:
    role = current_user.get("role", "employee")
    if role not in ("admin", "ceo", "c_suite", "board_member"):
        raise HTTPException(status_code=403, detail="Admin role required to manage industry packs.")


# ── Request models ─────────────────────────────────────────────────────────────

class ApplyPackRequest(BaseModel):
    answers:   dict[str, Any] = {}    # onboarding answers keyed by step key
    overrides: dict[str, Any] = {}    # optional overrides on top of pack defaults


class CustomizePackRequest(BaseModel):
    overrides: dict[str, Any]         # partial overrides: kpis, risks, governance_flags


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_packs(
    current_user: dict = Depends(get_current_user),
):
    """
    List all available industry packs.
    Returns summary metadata — use GET /packs/{pack_id} for full definition.
    """
    registry = get_pack_registry()
    packs = registry.list_all()
    return {
        "packs": packs,
        "count": len(packs),
    }


@router.get("/current")
async def get_current_pack(
    current_user: dict = Depends(get_current_user),
):
    """
    Return the active industry pack for the current tenant.
    Includes the stored onboarding answers and any custom overrides.
    """
    tenant_id = _get_tenant(current_user)
    record = get_tenant_pack(tenant_id)
    if not record:
        return {
            "tenant_id": tenant_id,
            "active_pack": None,
            "message": "No industry pack applied yet. Use POST /packs/{pack_id}/apply to get started.",
        }

    registry = get_pack_registry()
    pack = registry.get(record["pack_id"])
    pack_summary = pack.to_dict() if pack else {"pack_id": record["pack_id"], "name": "Unknown"}
    return {
        "tenant_id":  tenant_id,
        "active_pack": pack_summary,
        "applied_at": record.get("applied_at"),
        "answers":    record.get("answers", {}),
        "overrides":  record.get("overrides", {}),
    }


@router.get("/history")
async def get_pack_history(
    current_user: dict = Depends(get_current_user),
):
    """Return all packs ever applied to this tenant (most recent first)."""
    tenant_id = _get_tenant(current_user)
    records = list_tenant_packs(tenant_id)
    return {
        "tenant_id": tenant_id,
        "history":   records,
        "count":     len(records),
    }


@router.get("/{pack_id}")
async def get_pack(
    pack_id:      str,
    current_user: dict = Depends(get_current_user),
):
    """
    Full pack definition including all KPI templates, risk templates,
    onboarding steps, and governance flags.
    """
    registry = get_pack_registry()
    pack = registry.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' not found.")
    return pack.full_dict()


@router.get("/{pack_id}/onboarding")
async def get_onboarding_steps(
    pack_id:      str,
    current_user: dict = Depends(get_current_user),
):
    """
    Return the ordered onboarding questionnaire for a pack.
    Clients use this to render the pack setup wizard step-by-step.
    """
    registry = get_pack_registry()
    pack = registry.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' not found.")

    steps = [
        {
            "step":       s.step,
            "key":        s.key,
            "question":   s.question,
            "input_type": s.input_type,
            "options":    s.options,
            "required":   s.required,
            "hint":       s.hint,
        }
        for s in sorted(pack.onboarding_steps, key=lambda s: s.step)
    ]
    return {
        "pack_id":   pack_id,
        "pack_name": pack.name,
        "steps":     steps,
        "total":     len(steps),
    }


@router.post("/{pack_id}/apply")
async def apply_pack(
    pack_id:      str,
    body:         ApplyPackRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Apply an industry pack to the current tenant.
    Stores onboarding answers and activates pack configuration.
    Admin / CEO role required.

    Body:
      answers   — dict of { step_key: answer } from the onboarding wizard
      overrides — optional partial overrides on top of pack defaults
    """
    _require_admin(current_user)
    tenant_id = _get_tenant(current_user)

    registry = get_pack_registry()
    pack = registry.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' not found.")

    # Validate required onboarding answers
    required_keys = {s.key for s in pack.onboarding_steps if s.required}
    missing = required_keys - set(body.answers.keys())
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required onboarding answers: {sorted(missing)}",
        )

    result = registry.apply(
        pack_id   = pack_id,
        tenant_id = tenant_id,
        answers   = body.answers,
        overrides = body.overrides,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    logger.info(f"[Packs] Pack '{pack_id}' applied to tenant={tenant_id} by user={current_user.get('sub','?')}")
    return result


@router.post("/{pack_id}/customize")
async def customize_pack(
    pack_id:      str,
    body:         CustomizePackRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Apply custom overrides on top of an already-applied pack.
    Lets tenants replace specific KPI targets, add custom risks,
    or toggle governance flags without re-doing onboarding.

    Admin / CEO role required.

    Body:
      overrides — partial dict; merged with existing overrides.
        Supports keys:
          kpi_overrides      — {kpi_name: {target_value: "...", unit: "..."}}
          custom_risks       — [{title, severity, category, description, mitigation}]
          governance_flags   — {flag_name: true/false}
          departments        — list of dept_ids to activate
    """
    _require_admin(current_user)
    tenant_id = _get_tenant(current_user)

    registry = get_pack_registry()
    pack = registry.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' not found.")

    # Load existing record, merge overrides
    from industry_packs.base_pack import get_tenant_pack, apply_pack_to_tenant
    record = get_tenant_pack(tenant_id)
    existing_overrides: dict = {}
    existing_answers:   dict = {}

    if record and record.get("pack_id") == pack_id:
        existing_overrides = record.get("overrides", {})
        existing_answers   = record.get("answers", {})
    elif not record:
        raise HTTPException(
            status_code=400,
            detail=f"Pack '{pack_id}' is not applied to this tenant yet. Use POST /packs/{pack_id}/apply first.",
        )

    # Deep merge overrides
    merged = {**existing_overrides}
    for k, v in body.overrides.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v

    result = apply_pack_to_tenant(pack, tenant_id, existing_answers, merged)
    logger.info(f"[Packs] Pack '{pack_id}' customized for tenant={tenant_id}")
    return {
        **result,
        "overrides_applied": merged,
        "message": "Customizations saved. Pack configuration updated.",
    }
