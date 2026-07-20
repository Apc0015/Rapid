"""
routers/monitoring.py — Observability endpoints.

  GET /audit         — Immutable audit trail (admin/manager/ceo/board_member)
  GET /agents/stats  — Per-agent performance metrics (same roles)
  GET /health        — Public system health check
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse

from agents.system.audit_logger import get_audit
from agents.system.governance_filter import get_governance
from shared import AGENT_REGISTRY
from .deps import get_current_user

router = APIRouter(tags=["monitoring"])

_ALLOWED_AUDIT_ROLES = ("admin", "ceo")


def _require_audit_access(current_user: dict) -> dict:
    if current_user.get("role") not in _ALLOWED_AUDIT_ROLES:
        raise HTTPException(status_code=403, detail="Tenant administrator access required")
    return current_user


# ── Audit trail ───────────────────────────────────────────────────────────────

@router.get("/audit")
async def audit_trail(
    filter_uid: Optional[str] = None,
    event_type: Optional[str] = None,
    limit:      int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Tenant administrator — returns the tenant's immutable audit log."""
    _require_audit_access(current_user)
    audit = get_audit()
    return audit.query_audit_trail(
        user_id=filter_uid, event_type=event_type, tenant_id=str(current_user.get("tenant_id") or "default"), limit=min(limit, 500)
    )


# ── Agent stats ───────────────────────────────────────────────────────────────

@router.get("/agents/stats")
async def agent_stats(current_user: dict = Depends(get_current_user)):
    """Tenant administrator — per-agent performance statistics for this tenant."""
    _require_audit_access(current_user)
    audit = get_audit()
    tenant_id = str(current_user.get("tenant_id") or "default")
    return {agent_id: audit.get_agent_stats(agent_id, tenant_id) for agent_id in AGENT_REGISTRY}


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


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    checks = {}
    try:
        from infrastructure.job_queue import get_job_queue
        queue = get_job_queue()
        checks["job_queue"] = {"status": "ready", "stats": queue.stats()}
        workers = queue.worker_status()
        require_worker = os.getenv("RAPID_REQUIRE_JOB_WORKER", "false").lower() in {"1", "true", "yes"}
        checks["job_worker"] = {
            **workers,
            "required": require_worker,
            "status": "ready" if workers["active_count"] or not require_worker else "failed",
        }
    except Exception as error:
        checks["job_queue"] = {"status": "failed", "error": str(error)}
    try:
        from infrastructure.organization_data_store import get_organization_data_store
        get_organization_data_store().list_sources("__readiness__")
        checks["organization_data"] = {"status": "ready"}
    except Exception as error:
        checks["organization_data"] = {"status": "failed", "error": str(error)}
    ready = all(check["status"] == "ready" for check in checks.values())
    if not ready:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    from infrastructure.job_queue import get_job_queue
    from infrastructure.runtime_metrics import get_runtime_metrics
    return PlainTextResponse(get_runtime_metrics().prometheus(get_job_queue().stats()), media_type="text/plain; version=0.0.4")
