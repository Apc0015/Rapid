"""
routers/users.py — User request workflow (dept review, division review, admin approval).

  GET  /users/dept-requests                        — Dept head: pending requests
  POST /users/requests/{id}/dept-approve           — Dept head approve
  POST /users/requests/{id}/dept-reject            — Dept head reject
  GET  /users/admin-requests                       — Admin: admin_review stage
  POST /users/requests/{id}/admin-approve          — Admin final approval
  POST /users/requests/{id}/admin-reject           — Admin reject
  GET  /users/division-requests                    — Division head: pending
  POST /users/requests/{id}/division-approve       — Division head approve
  POST /users/requests/{id}/division-reject        — Division head reject
  GET  /users/list                                 — Admin/manager: all portal users
  GET  /users/requests                             — Admin: all requests (filterable)
  GET  /users/requests/pending-count               — Pending count for current user
  GET  /users/meta                                 — Public: valid roles/depts/divisions
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from infrastructure.user_registry import (
    get_dept_requests, dept_head_approve, dept_head_reject, get_user_dept_head_of,
    get_admin_review_requests, admin_approve, admin_reject,
    get_all_division_requests_for_user, get_user_division_head_of,
    division_head_approve, division_head_reject,
    list_all_requests, list_portal_users, get_pending_count_for_user,
    ALL_ROLES, ALL_DEPTS, ALL_DIVISIONS, DIVISION_DEPTS, DIVISION_CSUITE,
)
from shared import spokesperson
from .deps import get_current_user, require_admin, require_role

# Role dependency: dept heads and admins can perform dept-level review actions
_require_dept_reviewer = require_role("dept_head", "admin")

router = APIRouter(tags=["users"])


# ── Request bodies ────────────────────────────────────────────────────────────

class DeptReviewBody(BaseModel):
    dept:     str
    projects: list = []
    notes:    str  = ""


class AdminReviewBody(BaseModel):
    notes: str = ""


class DivisionReviewBody(BaseModel):
    division: str
    notes:    str = ""


# ── Dept head workflow ────────────────────────────────────────────────────────

@router.get("/users/dept-requests")
async def dept_requests_list(current_user: dict = Depends(get_current_user)):
    """Dept head: requests pending their review."""
    user_id = current_user["sub"]
    my_depts = get_user_dept_head_of(user_id)
    if not my_depts and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="You are not assigned as head of any department")
    all_reqs = [r for dept in my_depts for r in get_dept_requests(dept, user_id)]
    seen = set()
    unique = [r for r in all_reqs if not (r["request_id"] in seen or seen.add(r["request_id"]))]
    return {"requests": unique, "my_depts": my_depts}


@router.post("/users/requests/{req_id}/dept-approve")
async def dept_approve(req_id: str, body: DeptReviewBody,
                       current_user: dict = Depends(_require_dept_reviewer)):
    """Dept head approves their dept slice of a request."""
    user_id = current_user["sub"]
    try:
        req = dept_head_approve(req_id, body.dept, user_id, body.projects, body.notes)
        return {"status": req["stage"], "request_id": req_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/requests/{req_id}/dept-reject")
async def dept_reject(req_id: str, body: DeptReviewBody,
                      current_user: dict = Depends(_require_dept_reviewer)):
    """Dept head rejects a request."""
    user_id = current_user["sub"]
    try:
        dept_head_reject(req_id, body.dept, user_id, body.notes)
        return {"status": "rejected", "request_id": req_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Admin approval workflow ───────────────────────────────────────────────────

@router.get("/users/admin-requests")
async def admin_requests_list(current_user: dict = Depends(require_admin)):
    """Admin: requests at admin_review stage."""
    return {"requests": get_admin_review_requests()}


@router.post("/users/requests/{req_id}/admin-approve")
async def admin_approve_req(req_id: str, body: AdminReviewBody,
                            current_user: dict = Depends(require_admin)):
    """Admin final approval — creates the user account."""
    admin_id = current_user["sub"]
    try:
        req = admin_approve(req_id, admin_id, body.notes)
        spokesperson.reload_users()
        return {
            "status":        "approved",
            "rapid_user_id": req["rapid_user_id"],
            "login_key":     req["login_key"],
            "message":       f"Account created. Login: {req['login_key']}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/requests/{req_id}/admin-reject")
async def admin_reject_req(req_id: str, body: AdminReviewBody,
                           current_user: dict = Depends(require_admin)):
    """Admin rejects a request."""
    admin_id = current_user["sub"]
    try:
        admin_reject(req_id, admin_id, body.notes)
        return {"status": "rejected", "request_id": req_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Division / C-Suite review ─────────────────────────────────────────────────

@router.get("/users/division-requests")
async def division_requests_list(current_user: dict = Depends(get_current_user)):
    """Division head / C-Suite: requests pending their division review."""
    user_id = current_user["sub"]
    my_divs = get_user_division_head_of(user_id)
    if not my_divs and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="You are not assigned as head of any division")
    reqs, divs = get_all_division_requests_for_user(user_id)
    return {"requests": reqs, "my_divisions": divs}


@router.post("/users/requests/{req_id}/division-approve")
async def division_approve(req_id: str, body: DivisionReviewBody,
                           current_user: dict = Depends(get_current_user)):
    """Division head approves their division slice."""
    user_id = current_user["sub"]
    try:
        req = division_head_approve(req_id, body.division, user_id, body.notes)
        return {"status": req["stage"], "request_id": req_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/requests/{req_id}/division-reject")
async def division_reject(req_id: str, body: DivisionReviewBody,
                          current_user: dict = Depends(get_current_user)):
    """Division head rejects a request."""
    user_id = current_user["sub"]
    try:
        division_head_reject(req_id, body.division, user_id, body.notes)
        return {"status": "rejected", "request_id": req_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Shared user utilities ─────────────────────────────────────────────────────

@router.get("/users/list")
async def portal_users(current_user: dict = Depends(get_current_user)):
    """Leadership roles: list portal users for scoped team assignment."""
    if current_user.get("role") not in ("admin", "ceo", "c_suite", "manager", "dept_head", "division_head"):
        raise HTTPException(status_code=403, detail="A leadership role is required")
    return {"users": list_portal_users()}


@router.get("/users/requests")
async def all_requests(current_user: dict = Depends(require_admin),
                       stage: Optional[str] = None):
    """Admin: all requests, optionally filtered by stage."""
    return {"requests": list_all_requests(stage)}


@router.get("/users/requests/pending-count")
async def pending_count(current_user: dict = Depends(get_current_user)):
    """Count of requests needing this user's action across all stages."""
    user_id = current_user["sub"]
    return {"count": get_pending_count_for_user(user_id)}


@router.get("/users/meta")
async def user_meta():
    """Public: valid roles, departments, and divisions (no auth required)."""
    return {
        "roles":           ALL_ROLES,
        "departments":     ALL_DEPTS,
        "divisions":       ALL_DIVISIONS,
        "division_depts":  DIVISION_DEPTS,
        "division_csuite": DIVISION_CSUITE,
    }
