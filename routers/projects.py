"""
routers/projects.py — Project management API endpoints.

Endpoints:
  POST   /projects                          — Create a new project
  GET    /projects                          — List projects the user can access
  GET    /projects/{project_id}             — Get project details
  PATCH  /projects/{project_id}             — Update project
  DELETE /projects/{project_id}             — Archive project
  POST   /projects/{project_id}/members     — Add member
  DELETE /projects/{project_id}/members/{user_id} — Remove member
  GET    /projects/{project_id}/status      — Get project health summary
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import config
from routers.deps import get_current_user
from infrastructure.tenant_manager import get_tenant_manager, DEFAULT_TENANT_ID
from infrastructure.project_provisioner import get_project_provisioner

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger("rapid.projects")


# ── Request / Response models ─────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name:              str
    description:       Optional[str] = None
    dept_id:           str
    project_type:      str = "single_dept"      # 'single_dept' | 'cross_dept'
    priority:          str = "medium"
    start_date:        Optional[str] = None
    target_end_date:   Optional[str] = None
    budget_total:      Optional[float] = None
    tags:              list[str] = []


class UpdateProjectRequest(BaseModel):
    name:              Optional[str] = None
    description:       Optional[str] = None
    status:            Optional[str] = None
    priority:          Optional[str] = None
    target_end_date:   Optional[str] = None
    budget_total:      Optional[float] = None
    tags:              Optional[list[str]] = None


class AddMemberRequest(BaseModel):
    user_id:      str
    dept_id:      str
    role:         str = "member"       # 'owner' | 'manager' | 'member' | 'viewer'
    access_level: str = "standard"     # 'full' | 'manager' | 'standard' | 'readonly'


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_platform_conn() -> sqlite3.Connection:
    db_path = config.DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=config.DB_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    return conn


def _get_tenant_id(current_user: dict) -> str:
    """Extract tenant_id from JWT payload, default to DEFAULT_TENANT_ID."""
    return current_user.get("tenant_id", DEFAULT_TENANT_ID)


def _check_project_access(project_id: str, tenant_id: str, user_id: str) -> dict:
    """
    Verify the user has access to the project.
    Returns the member record if access is granted.
    Raises HTTP 403 if not a member, 404 if project doesn't exist.
    """
    conn = _get_platform_conn()
    try:
        # Check project exists
        project = conn.execute(
            "SELECT * FROM projects WHERE project_id = ? AND tenant_id = ?",
            (project_id, tenant_id),
        ).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Admin bypasses membership check
        # Check membership
        member = conn.execute(
            """
            SELECT * FROM project_members
            WHERE project_id = ? AND tenant_id = ? AND user_id = ? AND status = 'active'
            """,
            (project_id, tenant_id, user_id),
        ).fetchone()

        if not member:
            raise HTTPException(
                status_code=403,
                detail="You are not a member of this project",
            )
        return dict(member)
    finally:
        conn.close()


def _get_project_health(project_id: str, tenant_id: str) -> dict:
    """Fetch health summary from the project's own database."""
    provisioner = get_project_provisioner()
    db_path = provisioner.get_project_db_path(project_id, tenant_id)
    if not db_path or not Path(db_path).exists():
        return {"status": "no_data", "message": "Project database not yet populated"}

    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row

        meta = conn.execute("SELECT * FROM project_metadata LIMIT 1").fetchone()
        kpis = conn.execute(
            "SELECT kpi_name, current_value, target_value, status, unit FROM project_kpis"
        ).fetchall()
        milestones = conn.execute(
            """
            SELECT name, due_date, status
            FROM project_milestones
            WHERE status NOT IN ('completed', 'cancelled')
            ORDER BY due_date
            LIMIT 5
            """
        ).fetchall()
        risks = conn.execute(
            "SELECT title, probability, impact, status FROM project_risks WHERE status = 'open'"
        ).fetchall()

        conn.close()

        return {
            "metadata":   dict(meta) if meta else {},
            "kpis":       [dict(k) for k in kpis],
            "upcoming_milestones": [dict(m) for m in milestones],
            "open_risks": [dict(r) for r in risks],
        }
    except Exception as e:
        logger.warning(f"[projects] Could not read project health for {project_id}: {e}")
        return {"status": "error", "message": str(e)}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_project(
    req: CreateProjectRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new project. Automatically provisions the project database,
    FAISS index directory, and all registry entries.
    The creating user is automatically added as project owner.
    """
    tenant_id = _get_tenant_id(current_user)
    user_id   = current_user["sub"]
    project_id = str(uuid.uuid4())

    provisioner = get_project_provisioner()

    try:
        registry_entry = provisioner.provision(
            project_id=project_id,
            tenant_id=tenant_id,
            name=req.name,
            dept_id=req.dept_id,
            owner_user_id=user_id,
            description=req.description,
            project_type=req.project_type,
            priority=req.priority,
            start_date=req.start_date,
            target_end_date=req.target_end_date,
            budget_total=req.budget_total,
            tags=req.tags or [],
        )
    except Exception as e:
        logger.error(f"[projects] Provisioning failed for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Project provisioning failed: {e}")

    # Add the creating user as project owner
    conn = _get_platform_conn()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO project_members
                (project_id, tenant_id, user_id, dept_id, role, access_level, joined_at)
            VALUES (?, ?, ?, ?, 'owner', 'full', ?)
            """,
            (project_id, tenant_id, user_id, req.dept_id, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"[projects] Created project '{req.name}' ({project_id}) by user {user_id}")

    # Return the full project record
    return await get_project(project_id, current_user)


@router.get("")
async def list_projects(
    dept_id:  Optional[str] = None,
    status:   Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    List all projects the current user is a member of.
    Optionally filter by department or status.
    """
    tenant_id = _get_tenant_id(current_user)
    user_id   = current_user["sub"]
    role      = current_user.get("role", "employee")

    conn = _get_platform_conn()
    try:
        # Build query — admins see all projects, others see only their memberships
        if role == "admin":
            base_sql = """
                SELECT p.*, pm.role as member_role, pm.access_level
                FROM projects p
                LEFT JOIN project_members pm
                    ON p.project_id = pm.project_id AND p.tenant_id = pm.tenant_id
                    AND pm.user_id = ?
                WHERE p.tenant_id = ?
            """
            params = [user_id, tenant_id]
        else:
            base_sql = """
                SELECT p.*, pm.role as member_role, pm.access_level
                FROM projects p
                JOIN project_members pm
                    ON p.project_id = pm.project_id AND p.tenant_id = pm.tenant_id
                WHERE p.tenant_id = ? AND pm.user_id = ? AND pm.status = 'active'
            """
            params = [tenant_id, user_id]

        if dept_id:
            base_sql += " AND p.primary_dept_id = ?"
            params.append(dept_id)
        if status:
            base_sql += " AND p.status = ?"
            params.append(status)
        else:
            base_sql += " AND p.status != 'archived'"

        base_sql += " ORDER BY p.created_at DESC"

        rows = conn.execute(base_sql, params).fetchall()
        return {"projects": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()


@router.get("/{project_id}")
async def get_project(
    project_id:   str,
    current_user: dict = Depends(get_current_user),
):
    """Get full project details including members and registry info."""
    tenant_id = _get_tenant_id(current_user)
    user_id   = current_user["sub"]

    # Access check (raises 403/404 if not authorized)
    member_info = _check_project_access(project_id, tenant_id, user_id)

    conn = _get_platform_conn()
    try:
        project = conn.execute(
            "SELECT * FROM projects WHERE project_id = ? AND tenant_id = ?",
            (project_id, tenant_id),
        ).fetchone()

        members = conn.execute(
            """
            SELECT user_id, dept_id, role, access_level, joined_at
            FROM project_members
            WHERE project_id = ? AND tenant_id = ? AND status = 'active'
            """,
            (project_id, tenant_id),
        ).fetchall()

        registry = conn.execute(
            "SELECT db_path, faiss_index_path, status, provisioned_at, last_accessed FROM project_registry WHERE project_id = ? AND tenant_id = ?",
            (project_id, tenant_id),
        ).fetchone()

        return {
            "project":      dict(project),
            "member_info":  member_info,
            "members":      [dict(m) for m in members],
            "registry":     dict(registry) if registry else None,
        }
    finally:
        conn.close()


@router.patch("/{project_id}")
async def update_project(
    project_id:   str,
    req:          UpdateProjectRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update project fields. Requires owner or manager role."""
    tenant_id = _get_tenant_id(current_user)
    user_id   = current_user["sub"]

    member = _check_project_access(project_id, tenant_id, user_id)
    if member["role"] not in ("owner", "manager") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only project owners and managers can update a project")

    updates = {}
    if req.name is not None:            updates["name"] = req.name
    if req.description is not None:     updates["description"] = req.description
    if req.status is not None:          updates["status"] = req.status
    if req.priority is not None:        updates["priority"] = req.priority
    if req.target_end_date is not None: updates["target_end_date"] = req.target_end_date
    if req.budget_total is not None:    updates["budget_total"] = req.budget_total
    if req.tags is not None:
        import json
        updates["tags"] = json.dumps(req.tags)
    updates["updated_at"] = datetime.utcnow().isoformat()

    if not updates:
        return await get_project(project_id, current_user)

    cols = ", ".join(f"{k} = ?" for k in updates)
    conn = _get_platform_conn()
    try:
        conn.execute(
            f"UPDATE projects SET {cols} WHERE project_id = ? AND tenant_id = ?",
            (*updates.values(), project_id, tenant_id),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"[projects] Project {project_id} updated by {user_id}: {list(updates.keys())}")
    return await get_project(project_id, current_user)


@router.delete("/{project_id}", status_code=200)
async def archive_project(
    project_id:   str,
    current_user: dict = Depends(get_current_user),
):
    """Archive a project (soft delete). Requires owner role."""
    tenant_id = _get_tenant_id(current_user)
    user_id   = current_user["sub"]

    member = _check_project_access(project_id, tenant_id, user_id)
    if member["role"] != "owner" and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only project owners can archive a project")

    conn = _get_platform_conn()
    try:
        conn.execute(
            "UPDATE projects SET status = 'archived', updated_at = ? WHERE project_id = ? AND tenant_id = ?",
            (datetime.utcnow().isoformat(), project_id, tenant_id),
        )
        conn.execute(
            "UPDATE project_registry SET status = 'archived', archived_at = ? WHERE project_id = ? AND tenant_id = ?",
            (datetime.utcnow().isoformat(), project_id, tenant_id),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"[projects] Project {project_id} archived by {user_id}")
    return {"message": "Project archived successfully", "project_id": project_id}


@router.post("/{project_id}/members", status_code=201)
async def add_member(
    project_id:   str,
    req:          AddMemberRequest,
    current_user: dict = Depends(get_current_user),
):
    """Add a member to a project. Requires owner or manager role."""
    tenant_id = _get_tenant_id(current_user)
    user_id   = current_user["sub"]

    member = _check_project_access(project_id, tenant_id, user_id)
    if member["role"] not in ("owner", "manager") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only owners and managers can add members")

    conn = _get_platform_conn()
    try:
        conn.execute(
            """
            INSERT INTO project_members
                (project_id, tenant_id, user_id, dept_id, role, access_level, invited_by, joined_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, user_id, tenant_id) DO UPDATE SET
                role = excluded.role,
                access_level = excluded.access_level,
                status = 'active'
            """,
            (
                project_id, tenant_id, req.user_id, req.dept_id,
                req.role, req.access_level, user_id,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"[projects] Added member {req.user_id} to project {project_id} as {req.role}")
    return {
        "message":    "Member added successfully",
        "project_id": project_id,
        "user_id":    req.user_id,
        "role":       req.role,
    }


@router.delete("/{project_id}/members/{target_user_id}", status_code=200)
async def remove_member(
    project_id:      str,
    target_user_id:  str,
    current_user:    dict = Depends(get_current_user),
):
    """Remove a member from a project. Owners can remove anyone; managers can remove members."""
    tenant_id = _get_tenant_id(current_user)
    user_id   = current_user["sub"]

    member = _check_project_access(project_id, tenant_id, user_id)
    if member["role"] not in ("owner", "manager") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only owners and managers can remove members")

    conn = _get_platform_conn()
    try:
        conn.execute(
            """
            UPDATE project_members SET status = 'inactive'
            WHERE project_id = ? AND tenant_id = ? AND user_id = ?
            """,
            (project_id, tenant_id, target_user_id),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"[projects] Removed member {target_user_id} from project {project_id}")
    return {"message": "Member removed", "user_id": target_user_id}


@router.get("/{project_id}/status")
async def get_project_status(
    project_id:   str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get the live health summary of a project — KPIs, upcoming milestones, open risks.
    Reads directly from the project's own database.
    """
    tenant_id = _get_tenant_id(current_user)
    user_id   = current_user["sub"]

    _check_project_access(project_id, tenant_id, user_id)

    # Touch last accessed
    get_project_provisioner().touch_last_accessed(project_id, tenant_id)

    health = _get_project_health(project_id, tenant_id)
    return {"project_id": project_id, "health": health}
