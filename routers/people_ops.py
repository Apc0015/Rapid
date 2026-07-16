"""People Ops API: deterministic playbook runs, verifier gate, and founder escalations."""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from infrastructure.jwt_manager import get_jwt_manager
from infrastructure.people_ops_store import DEPARTMENTS, FOUNDER_ROLES, PLAYBOOKS, PRIVILEGED_ROLES, PeopleOpsError, get_people_ops_store
from routers.deps import get_current_user

router = APIRouter(prefix="/people-ops", tags=["people-ops"])


def _tenant(current_user: dict) -> str:
    return str(current_user.get("tenant_id") or "default")


def _raise(error: PeopleOpsError) -> None:
    raise HTTPException(status_code=400 if "not found" not in str(error).lower() else 404, detail=str(error))


def _require_role(current_user: dict, roles: set[str]) -> None:
    if current_user.get("role") not in roles:
        raise HTTPException(status_code=403, detail="Your role cannot perform this People Ops action")


def _allowed_departments(current_user: dict) -> set[str]:
    if current_user.get("role") in FOUNDER_ROLES:
        return set(DEPARTMENTS)
    return set(current_user.get("depts") or []) & set(DEPARTMENTS)


def _require_department(current_user: dict, department: str) -> None:
    if department not in _allowed_departments(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this department")


def _run_with_access(run_id: str, current_user: dict) -> dict:
    try:
        run = get_people_ops_store().get_run(_tenant(current_user), run_id)
    except PeopleOpsError as error:
        _raise(error)
    _require_department(current_user, run["playbook"]["department"])
    return run


class CreateRunRequest(BaseModel):
    playbook_key: str
    subject_name: str = Field(min_length=1, max_length=160)
    subject_email: str = Field(default="", max_length=254)
    due_date: Optional[str] = Field(default=None, max_length=32)
    details: dict[str, Any] = Field(default_factory=dict)


class EscalationDecision(BaseModel):
    decision: str
    note: str = Field(default="", max_length=1000)


@router.get("/playbooks")
async def list_playbooks(current_user: dict = Depends(get_current_user)):
    allowed = _allowed_departments(current_user)
    return {"playbooks": [item for item in get_people_ops_store().list_playbooks() if item["department"] in allowed]}


@router.get("/dashboard")
async def dashboard(current_user: dict = Depends(get_current_user)):
    allowed = _allowed_departments(current_user)
    data = get_people_ops_store().dashboard(_tenant(current_user))
    data["runs"] = [item for item in data["runs"] if item["playbook"]["department"] in allowed]
    data["departments"] = [item for item in data["departments"] if item["key"] in allowed]
    return data


@router.get("/runs")
async def list_runs(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    allowed = _allowed_departments(current_user)
    runs = get_people_ops_store().list_runs(_tenant(current_user), status=status)
    return {"runs": [item for item in runs if item["playbook"]["department"] in allowed]}


@router.post("/runs", status_code=201)
async def create_run(body: CreateRunRequest, current_user: dict = Depends(get_current_user)):
    playbook = PLAYBOOKS.get(body.playbook_key)
    if not playbook:
        raise HTTPException(status_code=404, detail="Unknown People Ops playbook")
    _require_department(current_user, playbook["department"])
    _require_role(current_user, PRIVILEGED_ROLES)
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
    _require_role(current_user, PRIVILEGED_ROLES)
    _run_with_access(run_id, current_user)
    try:
        return {"run": get_people_ops_store().advance_to_gate(_tenant(current_user), run_id, current_user["sub"])}
    except PeopleOpsError as error:
        _raise(error)


@router.post("/runs/{run_id}/verify")
async def verify_run(run_id: str, current_user: dict = Depends(get_current_user)):
    _require_role(current_user, PRIVILEGED_ROLES)
    _run_with_access(run_id, current_user)
    try:
        return {"run": get_people_ops_store().verify_run(_tenant(current_user), run_id)}
    except PeopleOpsError as error:
        _raise(error)


@router.post("/runs/{run_id}/escalation")
async def resolve_escalation(run_id: str, body: EscalationDecision, current_user: dict = Depends(get_current_user)):
    _require_role(current_user, FOUNDER_ROLES)
    _run_with_access(run_id, current_user)
    try:
        run = get_people_ops_store().resolve_escalation(_tenant(current_user), run_id, current_user["sub"], body.decision, body.note)
        return {"run": run}
    except PeopleOpsError as error:
        _raise(error)


@router.post("/demo-session")
async def demo_session():
    """Issue a synthetic-workspace token when a deployment explicitly enables demos."""
    enabled = os.getenv("RAPID_ENABLE_DEMO", "false").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        raise HTTPException(status_code=404, detail="Not found")
    token = get_jwt_manager().create_access_token("demo_founder", "ceo", ["hr"], extra={"tenant_id": "demo"})
    return {"access_token": token, "token_type": "bearer", "profile": {"name": "Demo Founder", "role": "ceo", "tenant_id": "demo"}}
