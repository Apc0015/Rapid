from __future__ import annotations
"""
routers/custom_agents.py — Dynamic Agent Management API

Lets admins add specialist agents to any department at runtime —
no code changes, no restarts.

Endpoints
─────────
  GET    /agents/custom                     → List all custom agents (all depts)
  GET    /agents/custom/{dept}              → List custom agents for one dept
  POST   /agents/custom/{dept}              → Create + inject a new agent
  GET    /agents/custom/{dept}/{agent_id}   → Get one agent's config
  PATCH  /agents/custom/{dept}/{agent_id}   → Update config fields
  DELETE /agents/custom/{dept}/{agent_id}   → Remove agent (hard delete)
  POST   /agents/custom/{dept}/reload       → Hot-reload all custom agents for dept

Auth: tenant administrator required for create/update/delete/reload.
      Any authenticated user can list/get within their department scope.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from routers.deps import get_current_user, require_admin
from infrastructure.people_ops_store import DEPARTMENTS
from infrastructure.custom_agent_store import (
    create_custom_agent,
    get_custom_agent,
    list_custom_agents,
    update_custom_agent,
    delete_custom_agent,
)

router = APIRouter(prefix="/agents/custom", tags=["custom-agents"])
logger = logging.getLogger("rapid.custom_agents_router")

_VALID_DEPTS = {
    "finance", "hr", "legal", "sales", "marketing",
    "ops", "it", "procurement", "rd", "customer_success",
}
_VALID_TOOLS = {"db_query", "document_search", "calculation", "peer_consult"}


# ── Request / Response models ─────────────────────────────────────────────────

class CreateAgentRequest(BaseModel):
    role_title: str = Field(..., min_length=2, max_length=80,
                            description="e.g. 'Tax Specialist', 'ESG Analyst'")
    specialization: str = Field("", max_length=300,
                                description="One-liner shown in the agent's LLM system prompt")
    bid_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords that trigger this agent (e.g. ['tax','vat','irs'])"
    )
    permitted_tables: List[str] = Field(
        default_factory=list,
        description="DB tables this agent may query (must be in the dept's constitution scope)"
    )
    doc_folders: List[str] = Field(
        default_factory=list,
        description="RAG document folders this agent searches"
    )
    tools_available: List[str] = Field(
        default=["db_query", "document_search"],
        description="Tools the agent can use: db_query, document_search, calculation, peer_consult"
    )
    system_prompt: str = Field(
        "",
        max_length=2000,
        description="Optional extra system instructions injected into this agent's LLM prompt"
    )

    @field_validator("tools_available")
    @classmethod
    def validate_tools(cls, v: List[str]) -> List[str]:
        invalid = set(v) - _VALID_TOOLS
        if invalid:
            raise ValueError(f"Invalid tools: {invalid}. Valid: {_VALID_TOOLS}")
        return v

    @field_validator("bid_keywords", "permitted_tables", "doc_folders", "tools_available")
    @classmethod
    def no_empty_strings(cls, v: List[str]) -> List[str]:
        return [item.strip() for item in v if item.strip()]


class UpdateAgentRequest(BaseModel):
    role_title:       Optional[str]       = None
    specialization:   Optional[str]       = None
    bid_keywords:     Optional[List[str]] = None
    permitted_tables: Optional[List[str]] = None
    doc_folders:      Optional[List[str]] = None
    tools_available:  Optional[List[str]] = None
    system_prompt:    Optional[str]       = None
    active:           Optional[bool]      = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_dept(dept: str) -> None:
    if dept not in _VALID_DEPTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown department '{dept}'. Valid: {sorted(_VALID_DEPTS)}"
        )


def _get_intra(dept: str):
    """
    Return the live IntraDeptOrchestrator for the given dept from the
    running AgentRegistry singleton. Returns None if unavailable.
    """
    try:
        from shared import AGENT_REGISTRY
        dept_agent = AGENT_REGISTRY.get_dept_agent(dept)
        if dept_agent and hasattr(dept_agent, "_intra"):
            return dept_agent._intra
    except Exception as e:
        logger.warning(f"Could not access live intra orchestrator for dept={dept}: {e}")
    return None


def _allowed_departments(current_user: dict) -> set[str]:
    if current_user.get("role") in {"admin", "ceo"}:
        return set(DEPARTMENTS)
    return set(current_user.get("depts") or []) & set(DEPARTMENTS)


def _tenant(current_user: dict) -> str:
    return str(current_user.get("tenant_id") or "default")


def _require_department_access(current_user: dict, dept: str) -> None:
    if dept not in _allowed_departments(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this department")


def _safe_agent_record(record: dict, current_user: dict) -> dict:
    """Managers can inspect their team roster but not system prompts or data topology."""
    if current_user.get("role") in {"admin", "ceo"}:
        return record
    safe = dict(record)
    for key in ("system_prompt", "permitted_tables", "doc_folders", "tools_available", "bid_keywords"):
        safe.pop(key, None)
    return safe


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_all_custom_agents(
    active_only: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """List all custom agents across all departments."""
    allowed = _allowed_departments(current_user)
    agents = [
        _safe_agent_record(agent, current_user)
        for agent in list_custom_agents(_tenant(current_user), active_only=active_only)
        if agent.get("dept_tag") in allowed
    ]
    return {
        "custom_agents": agents,
        "count": len(agents),
        "filter": {"active_only": active_only},
    }


@router.get("/{dept}")
async def list_dept_custom_agents(
    dept: str,
    active_only: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """List all custom agents for a specific department."""
    _validate_dept(dept)
    _require_department_access(current_user, dept)
    agents = list_custom_agents(_tenant(current_user), dept_tag=dept, active_only=active_only)
    for agent in agents:
        agent["activation_status"] = "awaiting_tenant_runtime"

    return {
        "dept": dept,
        "custom_agents": [_safe_agent_record(agent, current_user) for agent in agents],
        "count": len(agents),
        "live_specialist_count": 0,
    }


@router.post("/{dept}", status_code=201)
async def create_dept_agent(
    dept: str,
    req: CreateAgentRequest,
    current_user: dict = Depends(require_admin),
):
    """
    Create a new specialist agent for a department.

    The configuration is persisted within the current tenant. It is activated
    only by a tenant-aware agent runtime, never by the shared process registry.

    Example body:
    ```json
    {
      "role_title": "Tax Specialist",
      "specialization": "Corporate tax, VAT, deferred tax, withholding tax",
      "bid_keywords": ["tax", "vat", "irs", "deferred", "withholding", "tax rate"],
      "permitted_tables": ["tax_compliance", "financials"],
      "doc_folders": ["finance/tax_docs/"],
      "tools_available": ["db_query", "document_search"],
      "system_prompt": "You are a corporate tax specialist. Always cite the relevant tax code."
    }
    ```
    """
    _validate_dept(dept)
    _require_department_access(current_user, dept)

    # Check for duplicate role_title in this dept
    tenant_id = _tenant(current_user)
    existing = list_custom_agents(tenant_id, dept_tag=dept, active_only=False)
    if any(a["role_title"].lower() == req.role_title.lower() for a in existing):
        raise HTTPException(
            status_code=409,
            detail=f"An agent named '{req.role_title}' already exists in dept '{dept}'. "
                   "Use PATCH to update it or choose a different role_title."
        )

    record = create_custom_agent(
        tenant_id=tenant_id,
        dept_tag=dept,
        role_title=req.role_title,
        specialization=req.specialization,
        bid_keywords=req.bid_keywords,
        permitted_tables=req.permitted_tables,
        doc_folders=req.doc_folders,
        tools_available=req.tools_available,
        system_prompt=req.system_prompt,
        created_by=current_user.get("sub", "admin"),
    )

    logger.info(
        f"[CustomAgents] Created '{req.role_title}' for dept={dept} "
        f"by {current_user.get('sub','?')} | activation=awaiting_tenant_runtime"
    )

    return {
        "message": f"Agent '{req.role_title}' created for dept '{dept}'.",
        "activation_status": "awaiting_tenant_runtime",
        "agent": record,
    }


@router.get("/{dept}/{agent_id}")
async def get_dept_agent(
    dept: str,
    agent_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get the full config of one custom agent."""
    _validate_dept(dept)
    _require_department_access(current_user, dept)
    record = get_custom_agent(agent_id, _tenant(current_user))
    if not record or record["dept_tag"] != dept:
        raise HTTPException(status_code=404, detail="Agent not found in this department")

    record["activation_status"] = "awaiting_tenant_runtime"

    return {"agent": _safe_agent_record(record, current_user)}


@router.patch("/{dept}/{agent_id}")
async def update_dept_agent(
    dept: str,
    agent_id: str,
    req: UpdateAgentRequest,
    current_user: dict = Depends(require_admin),
):
    """
    Update fields of an existing custom agent.
    Changes are persisted for the tenant-aware agent runtime.
    """
    _validate_dept(dept)
    _require_department_access(current_user, dept)
    tenant_id = _tenant(current_user)
    existing = get_custom_agent(agent_id, tenant_id)
    if not existing or existing["dept_tag"] != dept:
        raise HTTPException(status_code=404, detail="Agent not found in this department")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    record = update_custom_agent(agent_id, tenant_id, **updates)

    return {
        "message": f"Agent '{record['role_title']}' updated.",
        "activation_status": "awaiting_tenant_runtime",
        "agent": record,
    }


@router.delete("/{dept}/{agent_id}", status_code=200)
async def delete_dept_agent(
    dept: str,
    agent_id: str,
    current_user: dict = Depends(require_admin),
):
    """
    Delete a custom agent.
    It is removed from the current tenant's configuration.
    """
    _validate_dept(dept)
    _require_department_access(current_user, dept)
    record = get_custom_agent(agent_id, _tenant(current_user))
    if not record or record["dept_tag"] != dept:
        raise HTTPException(status_code=404, detail="Agent not found in this department")

    role_title = record["role_title"]
    delete_custom_agent(agent_id, _tenant(current_user))

    return {
        "message": f"Agent '{role_title}' deleted from dept '{dept}'.",
        "agent_id": agent_id,
    }


@router.post("/{dept}/reload")
async def reload_dept_agents(
    dept: str,
    current_user: dict = Depends(require_admin),
):
    """
    The shared process registry cannot safely load tenant-specific agents.
    """
    _validate_dept(dept)
    _require_department_access(current_user, dept)
    raise HTTPException(
        status_code=409,
        detail="Tenant-specific agent activation requires the tenant-aware runtime. The configuration is saved but cannot be loaded into the shared runtime.",
    )
