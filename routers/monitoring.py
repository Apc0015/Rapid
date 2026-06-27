"""
routers/monitoring.py — Observability endpoints.

  GET /audit         — Immutable audit trail (admin/manager/ceo/board_member)
  GET /agents/stats  — Per-agent performance metrics (same roles)
  GET /health        — Public system health check
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from agents.system.audit_logger import get_audit
from agents.system.governance_filter import get_governance
from shared import AGENT_REGISTRY
from .deps import get_current_user

router = APIRouter(tags=["monitoring"])

_ALLOWED_AUDIT_ROLES = ("admin", "manager", "ceo", "board_member")


def _require_audit_access(current_user: dict) -> dict:
    if current_user.get("role") not in _ALLOWED_AUDIT_ROLES:
        raise HTTPException(status_code=403, detail="Admin or manager access required")
    return current_user


# ── Audit trail ───────────────────────────────────────────────────────────────

@router.get("/audit")
async def audit_trail(
    filter_uid: Optional[str] = None,
    event_type: Optional[str] = None,
    limit:      int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Admin/manager — returns the immutable audit log."""
    _require_audit_access(current_user)
    audit = get_audit()
    return audit.query_audit_trail(
        user_id=filter_uid, event_type=event_type, limit=min(limit, 500)
    )


# ── Agent stats ───────────────────────────────────────────────────────────────

@router.get("/agents/stats")
async def agent_stats(current_user: dict = Depends(get_current_user)):
    """Admin/manager — per-agent performance statistics."""
    _require_audit_access(current_user)
    audit = get_audit()
    return {agent_id: audit.get_agent_stats(agent_id) for agent_id in AGENT_REGISTRY}


# ── Health check ──────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    """Public health check — returns system status without auth."""
    from infrastructure.doc_master import get_doc_master
    from infrastructure.db_master import get_db_master
    from infrastructure.faiss_store import all_dept_indices
    doc = get_doc_master()
    db  = get_db_master()

    # Summarise per-dept FAISS index doc counts
    faiss_summary: dict = {}
    try:
        for dept, idx in all_dept_indices().items():
            faiss_summary[dept] = idx.doc_count
    except Exception:
        pass

    return {
        "status":              "ok",
        "version":             "1.0.0",
        "agents":              list(AGENT_REGISTRY.keys()),
        "faiss_doc_counts":    faiss_summary,
        "db_schemas_loaded":   list(db._schema_cache.keys()),
        "constitution_loaded": bool(get_governance().constitution),
    }
