from __future__ import annotations
"""
routers/nl_agent_creator.py — Natural Language Agent Creator

Lets a tenant administrator describe a new specialist agent in plain English.
The LLM parses the description into structured config fields and stores a
tenant-scoped configuration for activation by the tenant-aware runtime.

Endpoint
────────
  POST /agents/create-from-text

Example body:
  {
    "dept": "finance",
    "description": "Add a GST specialist who handles gst, itc and hsn queries
                    and can search the tax_docs folder and query the tax_compliance table"
  }
"""

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.deps import require_admin
from infrastructure.custom_agent_store import create_custom_agent, list_custom_agents
from infrastructure.llm_client import get_llm

router = APIRouter(prefix="/agents", tags=["agent-creator"])
logger = logging.getLogger("rapid.nl_agent_creator")

_VALID_DEPTS = {
    "finance", "hr", "legal", "sales", "marketing",
    "ops", "it", "procurement", "rd", "customer_success",
}
_VALID_TOOLS = {"db_query", "document_search", "calculation", "peer_consult"}


def _tenant(current_user: dict) -> str:
    return str(current_user.get("tenant_id") or "default")


def _require_department_access(current_user: dict, department: str) -> None:
    if current_user.get("role") not in {"admin", "ceo"} and department not in set(current_user.get("depts") or []):
        raise HTTPException(status_code=403, detail="You do not have access to this department")

# ── System prompt for the LLM parser ─────────────────────────────────────────

_PARSE_SYSTEM = """You are an AI agent configuration parser for an enterprise platform called RAPID.

Your job: read a plain English description and extract a structured agent config as JSON.

Output ONLY a valid JSON object with these fields (no explanation, no markdown):
{
  "role_title":      "short professional title, e.g. 'GST Compliance Specialist'",
  "specialization":  "one-liner about what this agent specialises in",
  "bid_keywords":    ["keyword1", "keyword2", ...],
  "permitted_tables": ["table1", "table2", ...],
  "doc_folders":     ["folder/path1/", ...],
  "tools_available": ["db_query", "document_search"],
  "system_prompt":   "optional extra instruction for the agent's LLM prompt, or empty string"
}

Rules:
- bid_keywords: extract all domain terms, abbreviations, and synonyms from the description.
  Always include at least 3-5 keywords. Think about what users would type when they need this agent.
- permitted_tables: extract any table names mentioned. If none mentioned, use an empty list [].
- doc_folders: extract any folder/path names mentioned. If none mentioned, use an empty list [].
- tools_available: default to ["db_query", "document_search"] unless the description mentions
  "calculation" or "peer_consult" or "consult other agents".
- system_prompt: if the description mentions a specific instruction style or authority
  (e.g. "always cite regulations", "be concise"), include it here. Otherwise "".
- role_title: derive a clean, professional 2-4 word title from the description.

Output ONLY the JSON. No prose. No markdown fences.
"""


# ── Request model ─────────────────────────────────────────────────────────────

class NLCreateRequest(BaseModel):
    dept: str = Field(..., description="Department: finance, hr, legal, sales, etc.")
    description: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Plain English description of the agent you want to create.",
        examples=[
            "Add a GST specialist who handles gst, itc and hsn queries "
            "and can search the tax_docs folder and query the tax_compliance table"
        ],
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/create-from-text", status_code=201)
async def create_agent_from_text(
    req: NLCreateRequest,
    current_user: dict = Depends(require_admin),
):
    """
    Create a specialist agent using plain English.

    The admin just describes what they want — the system figures out the config.

    **Example:**
    ```json
    {
      "dept": "finance",
      "description": "Add a GST specialist who handles gst, itc and hsn queries
                      and can search the tax_docs folder and query the tax_compliance table"
    }
    ```

    No JSON configuration knowledge required.
    """
    # Validate dept
    if req.dept not in _VALID_DEPTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown department '{req.dept}'. Valid: {sorted(_VALID_DEPTS)}"
        )
    _require_department_access(current_user, req.dept)
    tenant_id = _tenant(current_user)

    # ── Step 1: Parse plain English → structured config via LLM ──────────────
    config = await _parse_description(req.dept, req.description)

    # ── Step 2: Validate & clamp extracted fields ─────────────────────────────
    role_title = config.get("role_title", "").strip()
    if not role_title:
        raise HTTPException(
            status_code=422,
            detail="Could not extract a role_title from the description. "
                   "Please be more specific, e.g. 'Add a Tax Specialist to finance'."
        )

    # Clamp tools to valid set
    tools = [t for t in config.get("tools_available", []) if t in _VALID_TOOLS]
    if not tools:
        tools = ["db_query", "document_search"]

    # Check for duplicates in this dept
    existing = list_custom_agents(tenant_id, dept_tag=req.dept, active_only=False)
    if any(a["role_title"].lower() == role_title.lower() for a in existing):
        raise HTTPException(
            status_code=409,
            detail=f"An agent named '{role_title}' already exists in dept '{req.dept}'. "
                   "Use PATCH /agents/custom/{dept}/{agent_id} to update it."
        )

    # ── Step 3: Persist to SQLite ──────────────────────────────────────────────
    record = create_custom_agent(
        tenant_id=tenant_id,
        dept_tag=req.dept,
        role_title=role_title,
        specialization=config.get("specialization", ""),
        bid_keywords=config.get("bid_keywords", []),
        permitted_tables=config.get("permitted_tables", []),
        doc_folders=config.get("doc_folders", []),
        tools_available=tools,
        system_prompt=config.get("system_prompt", ""),
        created_by=current_user.get("sub", "admin"),
    )

    logger.info(
        f"[NLCreate] Created '{role_title}' for dept={req.dept} "
        f"by {current_user.get('sub','?')} | activation=awaiting_tenant_runtime"
    )

    return {
        "message": f"Agent '{role_title}' created for dept '{req.dept}' from plain text.",
        "original_description": req.description,
        "parsed_config": record,
        "activation_status": "awaiting_tenant_runtime",
    }


# ── LLM parser ────────────────────────────────────────────────────────────────

async def _parse_description(dept: str, description: str) -> Dict[str, Any]:
    """
    Ask the LLM to extract structured agent config from a plain English description.
    Returns a dict with role_title, specialization, bid_keywords, etc.
    Raises HTTPException on parse failure.
    """
    llm = get_llm()

    prompt = (
        f"Department: {dept}\n"
        f"Admin description: {description}\n\n"
        "Extract the agent configuration as JSON."
    )

    try:
        raw = await llm.complete(prompt, system=_PARSE_SYSTEM)
    except Exception as e:
        logger.error(f"[NLCreate] LLM call failed: {e!r}")
        raise HTTPException(
            status_code=503,
            detail="LLM unavailable. Please try again or use the JSON endpoint instead."
        )

    # Strip markdown fences if LLM added them
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"[NLCreate] LLM returned non-JSON: {raw!r}")
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not parse the agent description automatically. "
                "Please be more specific or use the JSON endpoint at "
                "POST /agents/custom/{dept}."
            )
        )

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="Unexpected LLM output format.")

    return parsed
