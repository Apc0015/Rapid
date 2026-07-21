"""
routers/admin.py — Admin-only org structure management.

  GET    /admin/dept-heads                          — List dept head assignments
  POST   /admin/dept-heads                          — Assign dept head
  DELETE /admin/dept-heads/{dept}                   — Remove dept head

  GET    /admin/divisions                           — List division / C-Suite assignments
  POST   /admin/divisions                           — Assign division head / C-Suite
  DELETE /admin/divisions/{division}                — Remove division head

  GET    /admin/agent-requests                      — List agent onboarding requests
  POST   /admin/agent-requests/{id}/approve         — Approve and auto-onboard
  POST   /admin/agent-requests/{id}/reject          — Reject with optional note

  GET    /admin/audit/retention                     — Audit retention stats
  POST   /admin/audit/purge-expired                 — Manually trigger retention purge
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from infrastructure.user_registry import (
    get_dept_heads, set_dept_head, remove_dept_head,
    get_divisions, set_division_head, remove_division_head,
    ALL_DEPTS, ALL_DIVISIONS, DIVISION_DEPTS, DIVISION_CSUITE,
)
from shared import spokesperson
from .deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Dept heads ────────────────────────────────────────────────────────────────

class DeptHeadBody(BaseModel):
    dept:    str
    user_id: str   # user to assign as dept head


@router.get("/dept-heads")
async def list_dept_heads(current_user: dict = Depends(require_admin)):
    """Admin: current dept head assignments."""
    return {"dept_heads": get_dept_heads(), "all_depts": ALL_DEPTS}


@router.post("/dept-heads")
async def assign_dept_head(body: DeptHeadBody,
                           current_user: dict = Depends(require_admin)):
    """Admin assigns a user as department head."""
    admin_id = current_user["sub"]
    try:
        result = set_dept_head(body.dept, body.user_id, admin_id)
        spokesperson.reload_users()
        return {"status": "ok", "assignment": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/dept-heads/{dept}")
async def unassign_dept_head(dept: str, current_user: dict = Depends(require_admin)):
    """Admin removes a dept head assignment."""
    admin_id = current_user["sub"]
    remove_dept_head(dept, admin_id)
    return {"status": "ok"}


# ── Divisions / C-Suite ───────────────────────────────────────────────────────

class DivisionHeadBody(BaseModel):
    division: str
    user_id:  str   # user to assign as division head / C-Suite
    title:    str = ""


@router.get("/divisions")
async def list_divisions(current_user: dict = Depends(require_admin)):
    """Admin: all divisions, their departments, and current C-Suite assignments."""
    return {
        "divisions":       get_divisions(),
        "all_divisions":   ALL_DIVISIONS,
        "division_depts":  DIVISION_DEPTS,
        "division_csuite": DIVISION_CSUITE,
    }


@router.post("/divisions")
async def assign_division_head(body: DivisionHeadBody,
                               current_user: dict = Depends(require_admin)):
    """Admin assigns a C-Suite exec / division head."""
    admin_id = current_user["sub"]
    try:
        result = set_division_head(body.division, body.user_id, admin_id, body.title)
        spokesperson.reload_users()
        return {"status": "ok", "assignment": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/divisions/{division}")
async def unassign_division_head(division: str, current_user: dict = Depends(require_admin)):
    """Admin removes a division head assignment."""
    admin_id = current_user["sub"]
    remove_division_head(division, admin_id)
    return {"status": "ok"}


# ── Audit retention management ────────────────────────────────────────────────

@router.get("/audit/retention")
async def audit_retention_stats(current_user: dict = Depends(require_admin)):
    """Admin: view audit log retention window stats."""
    from agents.system.audit_logger import get_audit
    return get_audit().get_retention_stats()


@router.post("/audit/purge-expired")
async def purge_expired_audit_records(current_user: dict = Depends(require_admin)):
    """Admin: manually trigger hard-deletion of audit records past 7-year retention."""
    from agents.system.audit_logger import get_audit
    deleted = get_audit().purge_expired_records()
    return {"status": "ok", "records_deleted": deleted}
