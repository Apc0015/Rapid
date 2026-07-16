"""Common employee workspace API backed by the synthetic demo organization."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from infrastructure.demo_workspace import WorkspaceError, get_demo_workspace_store
from infrastructure.tenant_admin_store import get_tenant_admin_store
from routers.deps import DEPARTMENT_OPERATOR_ROLES, TENANT_ADMIN_ROLES, get_current_user

router = APIRouter(prefix="/workspace", tags=["workspace"])


def _tenant(user: dict) -> str:
    return str(user.get("tenant_id") or "default")


def _raise(error: WorkspaceError) -> None:
    raise HTTPException(status_code=404 if "not found" in str(error).lower() else 400, detail=str(error))

def _require_admin(user: dict) -> None:
    if user.get("role") not in TENANT_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Organization administrator role required")


def _require_workspace_operator(user: dict) -> None:
    if user.get("role") not in DEPARTMENT_OPERATOR_ROLES:
        raise HTTPException(status_code=403, detail="Department operator role required to manage meetings and actions")


def _enabled_departments(user: dict) -> set[str]:
    profile_departments = set(get_tenant_admin_store().operating_profile(_tenant(user))["departments"])
    if user.get("role") in {"admin", "ceo"}:
        return profile_departments
    return profile_departments & set(user.get("depts") or [])


def _require_enabled_department(user: dict, department: str) -> None:
    if department and department not in _enabled_departments(user):
        raise HTTPException(status_code=403, detail="This department is not enabled for your organization or account")


class ActionStatusRequest(BaseModel):
    status: Literal["open", "in_progress", "done"]


class MeetingRequest(BaseModel):
    title: str
    meeting_type: str = "Operating review"
    department: str = ""
    starts_at: str
    duration_minutes: int = 30
    facilitator: str
    attendees: list[str] = []
    agenda: list[str]
    recurrence: Literal["none", "daily", "weekly", "biweekly", "monthly", "quarterly"] = "none"


class MeetingUpdateRequest(BaseModel):
    title: Optional[str] = None
    meeting_type: Optional[str] = None
    department: Optional[str] = None
    starts_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    facilitator: Optional[str] = None
    attendees: Optional[list[str]] = None
    agenda: Optional[list[str]] = None
    notes: Optional[str] = None
    decisions: Optional[list[str]] = None
    recurrence: Optional[Literal["none", "daily", "weekly", "biweekly", "monthly", "quarterly"]] = None
    status: Optional[Literal["scheduled", "in_progress", "completed", "cancelled"]] = None
class MeetingActionRequest(BaseModel):
    title: str
    owner: str
    department: str
    due_date: str
    priority: Literal["low", "medium", "high"] = "medium"


@router.get("/overview")
async def overview(current_user: dict = Depends(get_current_user)):
    return get_demo_workspace_store().overview(_tenant(current_user), _enabled_departments(current_user))

@router.post("/demo/reset")
async def reset_demo(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return get_demo_workspace_store().reset_workspace(_tenant(current_user))


@router.get("/meetings")
async def meetings(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return {"meetings": get_demo_workspace_store().list_meetings(_tenant(current_user), status, _enabled_departments(current_user))}


@router.post("/meetings", status_code=201)
async def create_meeting(body: MeetingRequest, current_user: dict = Depends(get_current_user)):
    try:
        _require_workspace_operator(current_user)
        if not body.department and current_user.get("role") not in TENANT_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Only a tenant administrator can schedule an organization-wide meeting")
        _require_enabled_department(current_user, body.department)
        meeting = get_demo_workspace_store().create_meeting(
            _tenant(current_user), body.title, body.meeting_type, body.department, body.starts_at,
            body.duration_minutes, body.facilitator, body.attendees, body.agenda, body.recurrence,
        )
        return {"meeting": meeting}
    except WorkspaceError as error:
        _raise(error)


@router.get("/meetings/{meeting_id}")
async def meeting(meeting_id: str, current_user: dict = Depends(get_current_user)):
    try:
        item = get_demo_workspace_store().get_meeting(_tenant(current_user), meeting_id)
        _require_enabled_department(current_user, item["department"])
        return {"meeting": item}
    except WorkspaceError as error:
        _raise(error)

@router.put("/meetings/{meeting_id}")
async def update_meeting(meeting_id: str, body: MeetingUpdateRequest, current_user: dict = Depends(get_current_user)):
    try:
        _require_workspace_operator(current_user)
        existing = get_demo_workspace_store().get_meeting(_tenant(current_user), meeting_id)
        _require_enabled_department(current_user, existing["department"])
        values = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
        _require_enabled_department(current_user, str(values.get("department") or existing["department"]))
        return {"meeting": get_demo_workspace_store().update_meeting(_tenant(current_user), meeting_id, values)}
    except WorkspaceError as error: _raise(error)

@router.post("/meetings/{meeting_id}/actions", status_code=201)
async def create_meeting_action(meeting_id: str, body: MeetingActionRequest, current_user: dict = Depends(get_current_user)):
    try:
        _require_workspace_operator(current_user)
        meeting = get_demo_workspace_store().get_meeting(_tenant(current_user), meeting_id)
        _require_enabled_department(current_user, meeting["department"])
        _require_enabled_department(current_user, body.department)
        return {"action": get_demo_workspace_store().create_meeting_action(_tenant(current_user), meeting_id, body.title, body.owner, body.department, body.due_date, body.priority)}
    except WorkspaceError as error: _raise(error)


@router.get("/actions")
async def actions(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return {"actions": get_demo_workspace_store().list_actions(_tenant(current_user), status, _enabled_departments(current_user))}


@router.get("/records")
async def records(entity_type: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return {"records": get_demo_workspace_store().list_entities(_tenant(current_user), entity_type, _enabled_departments(current_user))}


@router.get("/notifications")
async def notifications(include_read: bool = False, current_user: dict = Depends(get_current_user)):
    return {"notifications": get_demo_workspace_store().list_notifications(_tenant(current_user), include_read)}


@router.post("/notifications/{notification_id}/read")
async def read_notification(notification_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return {"notification": get_demo_workspace_store().mark_notification_read(_tenant(current_user), notification_id)}
    except WorkspaceError as error:
        _raise(error)


@router.get("/search")
async def search(q: str, limit: int = 30, current_user: dict = Depends(get_current_user)):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Search limit must be between 1 and 100")
    try:
        return get_demo_workspace_store().search(_tenant(current_user), q, limit, _enabled_departments(current_user))
    except WorkspaceError as error:
        _raise(error)


@router.post("/actions/{action_id}/status")
async def update_action(action_id: str, body: ActionStatusRequest, current_user: dict = Depends(get_current_user)):
    try:
        _require_workspace_operator(current_user)
        allowed_actions = {item["id"] for item in get_demo_workspace_store().list_actions(_tenant(current_user), departments=_enabled_departments(current_user))}
        if action_id not in allowed_actions:
            raise HTTPException(status_code=404, detail="Action not found")
        return {"action": get_demo_workspace_store().update_action_status(_tenant(current_user), action_id, body.status)}
    except WorkspaceError as error:
        _raise(error)
