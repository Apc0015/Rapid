"""
orgos/api.py — the HTTP surface every department shares.

The task board is the front door for any department. This factory builds one
FastAPI router bound to a single department; nothing in it is department-
specific except the binding itself, so adding a new department to the org
never means writing new endpoints — only new playbooks/handlers/verifies
(orgos/departments/<dept>/) and one line in routers/ wiring this factory up.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.deps import get_current_user
from orgos.engine import get_engine
from orgos.store import get_store
from orgos.registry import get_registry
from orgos.models import RunStatus, EscalationStatus
from orgos.access import (
    require_department_view, require_department_write, visible_departments,
)


def _tenant(user: dict) -> str:
    """The customer this request belongs to — the isolation key on every query."""
    return str(user.get("tenant_id") or "default")


# Which run statuses land in which board column.
BOARD_COLUMNS = {
    "executing": [RunStatus.TRIGGERED.value, RunStatus.PLANNED.value,
                  RunStatus.EXECUTING.value],
    "verifying": [RunStatus.VERIFYING.value],
    "escalated": [RunStatus.ESCALATED.value],
    "done":      [RunStatus.DONE.value],
    "failed":    [RunStatus.FAILED.value],
}


class CreateRunRequest(BaseModel):
    playbook: str
    subject: str
    inputs: dict = {}
    trigger_type: str = "message"
    auto_run: bool = True          # run to the first gate / completion immediately


class AdvanceRequest(BaseModel):
    single_step: bool = False


class DecideRequest(BaseModel):
    approved: bool
    note: str = ""


def build_department_router(dept: str) -> APIRouter:
    """Build the full HTTP surface for one department, bound by `dept`."""
    router = APIRouter(prefix=f"/{dept}", tags=[dept])

    @router.get("/playbooks")
    async def list_playbooks(user: dict = Depends(require_department_view(dept))):
        reg = get_registry()
        return {
            "playbooks": [
                {
                    "key": pb.key,
                    "title": pb.title,
                    "description": pb.description,
                    "required_inputs": pb.required_inputs,
                    "steps": [
                        {"title": s.title, "owner": s.owner, "autonomy": s.autonomy.value}
                        for s in pb.steps
                    ],
                }
                for pb in reg.list_playbooks(dept)
            ]
        }

    @router.get("/board")
    async def board(user: dict = Depends(require_department_view(dept))):
        store = get_store()
        t = _tenant(user)
        runs = store.list_runs(department=dept, tenant_id=t)
        columns: dict[str, list] = {k: [] for k in BOARD_COLUMNS}
        for run in runs:
            for col, statuses in BOARD_COLUMNS.items():
                if run.status in statuses:
                    columns[col].append(run.to_dict(include_steps=False))
                    break

        escalations = [e.to_dict() for e in
                       store.list_escalations(dept, EscalationStatus.PENDING.value, tenant_id=t)]
        digest = [
            {"run_id": r.run_id, "line": r.digest_line, "status": r.status}
            for r in runs
            if r.digest_line and r.status in (RunStatus.DONE.value,
                                              RunStatus.ESCALATED.value,
                                              RunStatus.FAILED.value)
        ][:12]

        return {
            "department": dept,
            "columns": columns,
            "counts": {k: len(v) for k, v in columns.items()},
            "escalations": escalations,
            "digest": digest,
        }

    @router.post("/runs")
    async def create_run(body: CreateRunRequest, user: dict = Depends(require_department_write(dept))):
        eng = get_engine()
        try:
            run = eng.create_run(
                department=dept,
                playbook_key=body.playbook,
                subject=body.subject.strip(),
                trigger_type=body.trigger_type,
                payload=body.inputs or {},
                created_by=user.get("sub", "unknown"),
                tenant_id=_tenant(user),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if body.auto_run:
            run = eng.advance(run.run_id)
        return run.to_dict()

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str, user: dict = Depends(require_department_view(dept))):
        run = get_store().get_run(run_id, tenant_id=_tenant(user))
        if not run or run.department != dept:
            raise HTTPException(status_code=404, detail="Run not found")
        return run.to_dict()

    @router.post("/runs/{run_id}/advance")
    async def advance_run(run_id: str, body: AdvanceRequest,
                          user: dict = Depends(require_department_write(dept))):
        run = get_store().get_run(run_id, tenant_id=_tenant(user))
        if not run or run.department != dept:
            raise HTTPException(status_code=404, detail="Run not found")
        run = get_engine().advance(run_id, single_step=body.single_step)
        return run.to_dict()

    @router.get("/escalations")
    async def list_escalations(status: Optional[str] = None,
                               user: dict = Depends(require_department_view(dept))):
        return {"escalations": [e.to_dict() for e in
                                get_store().list_escalations(dept, status, tenant_id=_tenant(user))]}

    @router.post("/escalations/{escalation_id}/decide")
    async def decide_escalation(escalation_id: str, body: DecideRequest,
                                user: dict = Depends(require_department_write(dept))):
        esc = get_store().get_escalation(escalation_id, tenant_id=_tenant(user))
        if not esc or esc.department != dept:
            raise HTTPException(status_code=404, detail="Escalation not found")
        if esc.status != EscalationStatus.PENDING.value:
            raise HTTPException(status_code=409, detail=f"Already {esc.status}")
        try:
            run = get_engine().decide_escalation(
                escalation_id, approved=body.approved,
                decided_by=user.get("sub", "unknown"), note=body.note,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return run.to_dict()

    @router.get("/audit/{run_id}")
    async def audit(run_id: str, user: dict = Depends(require_department_view(dept))):
        return {"run_id": run_id, "entries": get_store().list_audit(run_id=run_id, tenant_id=_tenant(user))}

    return router


# ── Org-wide endpoint (all departments' boards in one call) ────────────────────

org_router = APIRouter(prefix="/org", tags=["org"])

DEPARTMENTS = ["hr", "it", "finance", "marketing"]

# C-suite oversight: which exec owns which departments. Real grouping, not
# decoration — it's how /org/overview labels ownership and how a future
# exec-scoped role (see how-ap-wants-me-to-work memory: role-based access is
# still open) would restrict what someone sees.
EXEC_OWNERSHIP = {
    "chro": {"title": "Chief HR Officer", "departments": ["hr"]},
    "cfo":  {"title": "Chief Financial Officer", "departments": ["finance"]},
    "coo":  {"title": "Chief Operating Officer", "departments": ["it"]},
    "cmo":  {"title": "Chief Marketing Officer", "departments": ["marketing"]},
}


def _dept_to_exec(dept: str) -> Optional[str]:
    for exec_key, info in EXEC_OWNERSHIP.items():
        if dept in info["departments"]:
            return exec_key
    return None


@org_router.get("/departments")
async def list_departments(user: dict = Depends(get_current_user)):
    reg = get_registry()
    visible = visible_departments(user, DEPARTMENTS)
    return {
        "departments": [
            {
                "key": d,
                "playbook_count": len(reg.list_playbooks(d)),
                "exec": _dept_to_exec(d),
            }
            for d in DEPARTMENTS if d in visible
        ],
        "exec_ownership": EXEC_OWNERSHIP,
    }


def _build_overview(departments: list[str], tenant_id: str = "default") -> dict:
    """Shared by /org/overview and /org/exec/{key} — same shape, different scope."""
    store = get_store()
    all_escalations, all_digest = [], []
    counts_by_dept = {}
    for dept in departments:
        runs = store.list_runs(department=dept, tenant_id=tenant_id)
        counts_by_dept[dept] = {
            "total": len(runs),
            "escalated": len([r for r in runs if r.status == RunStatus.ESCALATED.value]),
            "exec": _dept_to_exec(dept),
        }
        all_escalations.extend(e.to_dict() for e in
                               store.list_escalations(dept, EscalationStatus.PENDING.value, tenant_id=tenant_id))
        all_digest.extend(
            {"department": dept, "run_id": r.run_id, "line": r.digest_line, "status": r.status}
            for r in runs
            if r.digest_line and r.status in (RunStatus.DONE.value,
                                              RunStatus.ESCALATED.value,
                                              RunStatus.FAILED.value)
        )
    all_digest.sort(key=lambda d: d["run_id"], reverse=True)
    return {
        "departments": counts_by_dept,
        "escalations": all_escalations,
        "digest": all_digest[:20],
    }


@org_router.get("/overview")
async def overview(user: dict = Depends(get_current_user)):
    """One digest + one escalation queue across every department this user can see."""
    return _build_overview(visible_departments(user, DEPARTMENTS), _tenant(user))


@org_router.get("/exec/{exec_key}")
async def exec_overview(exec_key: str, user: dict = Depends(get_current_user)):
    """The same overview, scoped to just the departments one exec owns."""
    info = EXEC_OWNERSHIP.get(exec_key)
    if not info:
        raise HTTPException(status_code=404, detail=f"Unknown exec role '{exec_key}'")
    visible = visible_departments(user, info["departments"])
    if not visible:
        raise HTTPException(status_code=403, detail=f"You don't have access to the {info['title']} view.")
    result = _build_overview(visible, _tenant(user))
    result["exec"] = {"key": exec_key, "title": info["title"], "departments": visible}
    return result


@org_router.get("/mesh/{mesh_group_id}")
async def mesh_group(mesh_group_id: str, user: dict = Depends(get_current_user)):
    """Every run across every department that belongs to one cross-department task."""
    runs = get_store().list_runs_by_mesh_group(mesh_group_id, tenant_id=_tenant(user))
    if not runs:
        raise HTTPException(status_code=404, detail="No runs found for this mesh group")
    allowed = set(visible_departments(user, DEPARTMENTS))
    runs = [r for r in runs if r.department in allowed]
    if not runs:
        raise HTTPException(status_code=403, detail="You don't have access to any department in this mesh group.")
    return {"mesh_group_id": mesh_group_id, "runs": [r.to_dict() for r in runs]}
