"""
routers/people.py — People Directory API

Endpoints
─────────
  POST   /people                          → Create person
  GET    /people                          → List people (tenant-scoped)
  GET    /people/search?q=               → Search people by name/email/role
  GET    /people/org-chart               → Full org hierarchy
  GET    /people/headcount               → Dept headcount breakdown
  GET    /people/{person_id}             → Get person detail
  PATCH  /people/{person_id}             → Update person fields
  DELETE /people/{person_id}             → Deactivate person
  GET    /people/{person_id}/graph       → Person + relationships subgraph
  GET    /people/{person_id}/reports     → Direct reports
  GET    /people/{person_id}/collaborators → Department peers
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from routers.deps import get_current_user
from infrastructure.people_ops_store import DEPARTMENTS
from infrastructure.people_directory import get_people_directory

router = APIRouter(prefix="/people", tags=["people"])
logger = logging.getLogger("rapid.people_router")


# ── Request / Response models ─────────────────────────────────────────────────

class CreatePersonRequest(BaseModel):
    name:       str
    email:      str        = ""
    role:       str        = "employee"
    dept_id:    Optional[str] = None
    division:   Optional[str] = None
    reports_to: Optional[str] = None
    location:   Optional[str] = None
    bio:        Optional[str] = None
    person_id:  Optional[str] = None  # optional client-side ID


class UpdatePersonRequest(BaseModel):
    name:       Optional[str] = None
    email:      Optional[str] = None
    role:       Optional[str] = None
    dept_id:    Optional[str] = None
    division:   Optional[str] = None
    reports_to: Optional[str] = None
    location:   Optional[str] = None
    bio:        Optional[str] = None
    status:     Optional[str] = None


def _get_tenant(current_user: dict) -> str:
    tid = current_user.get("tenant_id") or current_user.get("sub", "default")
    return tid


def _allowed_departments(current_user: dict) -> set[str]:
    if current_user.get("role") in {"admin", "ceo"}:
        return set(DEPARTMENTS)
    return set(current_user.get("depts") or []) & set(DEPARTMENTS)


def _person_with_access(person_id: str, current_user: dict):
    person = get_people_directory().get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
    if person.tenant_id != _get_tenant(current_user):
        raise HTTPException(status_code=403, detail="Access denied")
    if person.dept_id and person.dept_id not in _allowed_departments(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this department")
    return person


def _visible_people(people, current_user: dict):
    allowed = _allowed_departments(current_user)
    return [person for person in people if not person.dept_id or person.dept_id in allowed]


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("", status_code=201)
async def create_person(
    req: CreatePersonRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a new person record (manager/admin only)."""
    if current_user.get("role") not in ("admin", "manager", "dept_head",
                                         "division_head", "c_suite", "ceo"):
        raise HTTPException(status_code=403, detail="Manager role required to create people")
    if req.dept_id and req.dept_id not in _allowed_departments(current_user):
        raise HTTPException(status_code=403, detail="You cannot create a person outside your department scope")

    tenant_id = _get_tenant(current_user)
    directory = get_people_directory()
    person = directory.create(
        tenant_id  = tenant_id,
        name       = req.name,
        email      = req.email,
        role       = req.role,
        dept_id    = req.dept_id,
        division   = req.division,
        reports_to = req.reports_to,
        location   = req.location,
        bio        = req.bio,
        person_id  = req.person_id,
    )
    return {"person": person.to_dict(), "message": "Person created"}


@router.get("")
async def list_people(
    dept_id: Optional[str] = Query(None),
    role:    Optional[str] = Query(None),
    status:  str           = Query("active"),
    limit:   int           = Query(100, ge=1, le=500),
    current_user: dict     = Depends(get_current_user),
):
    """List people in the tenant, with optional dept/role/status filters."""
    tenant_id = _get_tenant(current_user)
    directory = get_people_directory()
    if dept_id and dept_id not in _allowed_departments(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this department")
    people = directory.list(
        tenant_id=tenant_id, dept_id=dept_id, role=role,
        status=status, limit=limit,
    )
    visible = _visible_people(people, current_user)
    return {
        "people":  [p.to_dict() for p in visible],
        "count":   len(visible),
        "filters": {"dept_id": dept_id, "role": role, "status": status},
    }


@router.get("/search")
async def search_people(
    q:     str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Search people by name, email, role, or department."""
    tenant_id = _get_tenant(current_user)
    directory = get_people_directory()
    results = directory.search(tenant_id=tenant_id, query=q, limit=limit)
    results = _visible_people(results, current_user)
    return {
        "query":   q,
        "results": [p.to_dict() for p in results],
        "count":   len(results),
    }


@router.get("/org-chart")
async def org_chart(
    current_user: dict = Depends(get_current_user),
):
    """Return full org hierarchy for this tenant."""
    tenant_id = _get_tenant(current_user)
    directory = get_people_directory()
    chart = directory.org_chart(tenant_id)
    allowed = _allowed_departments(current_user)
    if current_user.get("role") not in {"admin", "ceo"}:
        chart["by_dept"] = {
            department: people
            for department, people in chart.get("by_dept", {}).items()
            if department in allowed
        }
        chart["root_leaders"] = [
            person for person in chart.get("root_leaders", [])
            if not person.get("dept_id") or person.get("dept_id") in allowed
        ]
        chart["total"] = sum(len(people) for people in chart["by_dept"].values())
        chart["dept_count"] = len(chart["by_dept"])
    return chart


@router.get("/headcount")
async def headcount(
    current_user: dict = Depends(get_current_user),
):
    """Return department headcount breakdown."""
    tenant_id = _get_tenant(current_user)
    directory = get_people_directory()
    counts = directory.dept_headcount(tenant_id)
    allowed = _allowed_departments(current_user)
    counts = {department: count for department, count in counts.items() if department in allowed}
    return {
        "tenant_id": tenant_id,
        "headcount": counts,
        "total":     sum(counts.values()),
    }


@router.get("/{person_id}")
async def get_person(
    person_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a person's full profile."""
    person = _person_with_access(person_id, current_user)
    return {"person": person.to_dict()}


@router.patch("/{person_id}")
async def update_person(
    person_id: str,
    req: UpdatePersonRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update person fields (manager/admin only)."""
    if current_user.get("role") not in ("admin", "manager", "dept_head",
                                         "division_head", "c_suite", "ceo"):
        raise HTTPException(status_code=403, detail="Manager role required")

    _person_with_access(person_id, current_user)
    directory = get_people_directory()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates.get("dept_id") and updates["dept_id"] not in _allowed_departments(current_user):
        raise HTTPException(status_code=403, detail="You cannot move a person outside your department scope")
    person = directory.update(person_id, **updates)
    if not person:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
    return {"person": person.to_dict(), "message": "Person updated"}


@router.delete("/{person_id}")
async def deactivate_person(
    person_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Deactivate a person (sets status=inactive). Admin/manager only."""
    if current_user.get("role") not in ("admin", "manager", "c_suite", "ceo"):
        raise HTTPException(status_code=403, detail="Admin role required")

    _person_with_access(person_id, current_user)
    directory = get_people_directory()
    person = directory.deactivate(person_id)
    if not person:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
    return {"message": "Person deactivated", "person_id": person_id}


@router.get("/{person_id}/graph")
async def person_graph(
    person_id: str,
    depth: int = Query(2, ge=1, le=3),
    current_user: dict = Depends(get_current_user),
):
    """Return the person's org graph — manager, direct reports, collaborators."""
    _person_with_access(person_id, current_user)
    directory = get_people_directory()
    graph = directory.get_graph(person_id, depth=depth)
    if "error" in graph:
        raise HTTPException(status_code=404, detail=graph["error"])
    allowed = _allowed_departments(current_user)
    manager = graph.get("manager")
    if manager and manager.get("dept_id") and manager["dept_id"] not in allowed:
        graph["manager"] = None
    graph["direct_reports"] = [
        person for person in graph.get("direct_reports", [])
        if not person.get("dept_id") or person.get("dept_id") in allowed
    ]
    graph["collaborators"] = [
        person for person in graph.get("collaborators", [])
        if not person.get("dept_id") or person.get("dept_id") in allowed
    ]
    visible_ids = {person_id}
    visible_ids.update(person["person_id"] for person in graph["direct_reports"])
    visible_ids.update(person["person_id"] for person in graph["collaborators"])
    if graph.get("manager"):
        visible_ids.add(graph["manager"]["person_id"])
    graph["edges"] = [edge for edge in graph.get("edges", []) if edge.get("target") in visible_ids]
    return graph


@router.get("/{person_id}/reports")
async def direct_reports(
    person_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all direct reports for this person."""
    _person_with_access(person_id, current_user)
    directory = get_people_directory()
    reports = _visible_people(directory.get_direct_reports(person_id), current_user)
    return {
        "person_id": person_id,
        "reports":   [p.to_dict() for p in reports],
        "count":     len(reports),
    }


@router.get("/{person_id}/collaborators")
async def collaborators(
    person_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """List department peers (collaborators) for this person."""
    _person_with_access(person_id, current_user)
    directory = get_people_directory()
    collabs = _visible_people(directory.get_collaborators(person_id, limit=limit), current_user)
    return {
        "person_id":     person_id,
        "collaborators": [p.to_dict() for p in collabs],
        "count":         len(collabs),
    }
