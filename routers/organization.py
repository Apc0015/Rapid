"""Organization operating system API built on the governed task-run engine."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from infrastructure.people_ops_store import (
    DEPARTMENTS,
    FOUNDER_ROLES,
    PLAYBOOKS,
    PRIVILEGED_ROLES,
    PeopleOpsError,
    get_people_ops_store,
)
from routers.deps import get_current_user

router = APIRouter(prefix="/organization", tags=["organization"])


def _tenant(current_user: dict) -> str:
    return str(current_user.get("tenant_id") or "default")


def _raise(error: PeopleOpsError) -> None:
    status_code = 404 if "not found" in str(error).lower() or "unknown" in str(error).lower() else 400
    raise HTTPException(status_code=status_code, detail=str(error))


def _allowed_departments(current_user: dict) -> set[str]:
    if current_user.get("role") in {"admin", "ceo"}:
        return set(DEPARTMENTS)
    return set(current_user.get("depts") or []) & set(DEPARTMENTS)


def _require_department(current_user: dict, department: str) -> None:
    if department not in _allowed_departments(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this department")


def _require_operator(current_user: dict) -> None:
    if current_user.get("role") not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="Department operator role required")


class OrganizationRunRequest(BaseModel):
    playbook_key: str
    subject_name: str = Field(min_length=1, max_length=160)
    subject_email: str = Field(default="", max_length=254)
    due_date: Optional[str] = Field(default=None, max_length=32)
    details: dict[str, Any] = Field(default_factory=dict)


class EscalationDecision(BaseModel):
    decision: str
    note: str = Field(default="", max_length=1000)


class HandoffRequest(BaseModel):
    playbook_key: str
    subject_name: str = Field(min_length=1, max_length=160)
    subject_email: str = Field(default="", max_length=254)
    details: dict[str, Any] = Field(default_factory=dict)


def _department_for_playbook(playbook_key: str) -> str:
    playbook = PLAYBOOKS.get(playbook_key)
    if not playbook:
        raise HTTPException(status_code=404, detail="Unknown organization playbook")
    return playbook["department"]


def _run_with_access(run_id: str, current_user: dict) -> dict:
    try:
        run = get_people_ops_store().get_run(_tenant(current_user), run_id)
    except PeopleOpsError as error:
        _raise(error)
    _require_department(current_user, run["playbook"]["department"])
    return run


@router.get("/departments")
async def list_departments(current_user: dict = Depends(get_current_user)):
    allowed = _allowed_departments(current_user)
    return {
        "departments": [
            {"key": key, **definition}
            for key, definition in DEPARTMENTS.items()
            if key in allowed
        ]
    }


@router.get("/playbooks")
async def list_playbooks(department: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if department:
        _require_department(current_user, department)
    allowed = _allowed_departments(current_user)
    return {
        "playbooks": [
            playbook for playbook in get_people_ops_store().list_playbooks()
            if playbook["department"] in allowed and (department is None or playbook["department"] == department)
        ]
    }


@router.get("/dashboard")
async def dashboard(department: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if department:
        _require_department(current_user, department)
    allowed = _allowed_departments(current_user)
    all_data = get_people_ops_store().dashboard(_tenant(current_user))
    runs = [run for run in all_data["runs"] if run["playbook"]["department"] in allowed and (department is None or run["playbook"]["department"] == department)]
    statuses = {status: sum(run["status"] == status for run in runs) for status in ("planned", "executing", "verifying", "done", "escalated", "failed")}
    settled = [run for run in runs if run["status"] in {"done", "failed"}]
    return {
        "runs": runs,
        "stats": {"total": len(runs), **statuses, "autonomous_completion_rate": round((sum(run["status"] == "done" for run in settled) / len(settled)) * 100) if settled else 0},
        "escalations": [run for run in runs if run["status"] == "escalated"],
        "departments": [item for item in all_data["departments"] if item["key"] in allowed],
    }


@router.get("/runs")
async def list_runs(department: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if department:
        _require_department(current_user, department)
    allowed = _allowed_departments(current_user)
    runs = get_people_ops_store().list_runs(_tenant(current_user), status=status, department=department)
    return {"runs": [run for run in runs if run["playbook"]["department"] in allowed]}


@router.post("/runs", status_code=201)
async def create_run(body: OrganizationRunRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    department = _department_for_playbook(body.playbook_key)
    _require_department(current_user, department)
    try:
        run = get_people_ops_store().create_run(
            tenant_id=_tenant(current_user), created_by=current_user["sub"], playbook_key=body.playbook_key,
            subject_name=body.subject_name, subject_email=body.subject_email, due_date=body.due_date, details=body.details,
        )
        return {"run": run}
    except PeopleOpsError as error:
        _raise(error)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, current_user: dict = Depends(get_current_user)):
    return {"run": _run_with_access(run_id, current_user)}


@router.post("/runs/{run_id}/advance")
async def advance_run(run_id: str, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _run_with_access(run_id, current_user)
    try:
        return {"run": get_people_ops_store().advance_to_gate(_tenant(current_user), run_id, current_user["sub"])}
    except PeopleOpsError as error:
        _raise(error)


@router.post("/runs/{run_id}/verify")
async def verify_run(run_id: str, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _run_with_access(run_id, current_user)
    try:
        return {"run": get_people_ops_store().verify_run(_tenant(current_user), run_id)}
    except PeopleOpsError as error:
        _raise(error)


@router.post("/runs/{run_id}/handoff", status_code=201)
async def handoff_run(run_id: str, body: HandoffRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    source = _run_with_access(run_id, current_user)
    target_department = _department_for_playbook(body.playbook_key)
    _require_department(current_user, target_department)
    if source["playbook"]["department"] == target_department:
        raise HTTPException(status_code=400, detail="A handoff must target a different department")
    try:
        run = get_people_ops_store().handoff_run(
            tenant_id=_tenant(current_user),
            source_run_id=run_id,
            created_by=current_user["sub"],
            target_playbook_key=body.playbook_key,
            subject_name=body.subject_name,
            subject_email=body.subject_email,
            details=body.details,
        )
        return {"run": run}
    except PeopleOpsError as error:
        _raise(error)


@router.post("/runs/{run_id}/escalation")
async def resolve_escalation(run_id: str, body: EscalationDecision, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in FOUNDER_ROLES:
        raise HTTPException(status_code=403, detail="Founder role required to resolve an escalation")
    _run_with_access(run_id, current_user)
    try:
        run = get_people_ops_store().resolve_escalation(_tenant(current_user), run_id, current_user["sub"], body.decision, body.note)
        return {"run": run}
    except PeopleOpsError as error:
        _raise(error)


@router.get("/reports/{department}")
async def department_report(department: str, current_user: dict = Depends(get_current_user)):
    _require_department(current_user, department)
    try:
        return get_people_ops_store().department_report(_tenant(current_user), department)
    except PeopleOpsError as error:
        _raise(error)
