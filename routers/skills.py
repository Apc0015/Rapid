"""
routers/skills.py — Agent Skill Library API.

Endpoints
─────────
  GET  /projects/{project_id}/skills/available
      → List all skills available for this project's department

  POST /projects/{project_id}/skills/execute
      → Execute a skill by skill_id and return the output file

  GET  /projects/{project_id}/skills/detect?query=...
      → Auto-detect which skill best matches a natural-language query

  GET  /projects/{project_id}/documents
      → List all generated documents for this project

  GET  /skills/catalog
      → List all registered skills across all departments
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from routers.deps import get_current_user
from infrastructure.project_context import ProjectContext

router = APIRouter(tags=["skills"])
logger = logging.getLogger("rapid.skills")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_project_row(project_id: str) -> dict:
    """Fetch project row from registry, raise 404 if missing."""
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT project_id, tenant_id, dept_id, db_path, name, status "
            "FROM project_registry WHERE project_id=?",
            (project_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return dict(row)


def _build_context(proj_row: dict) -> ProjectContext:
    """Build a minimal ProjectContext from a project registry row."""
    ctx = ProjectContext(
        project_id = proj_row["project_id"],
        tenant_id  = proj_row["tenant_id"],
        dept_id    = proj_row.get("dept_id") or "all",
    )
    # Attach db_path so skills can query project data
    ctx.db_path = proj_row.get("db_path") or ""
    # Attach project name if available
    ctx.project_name = proj_row.get("name") or proj_row["project_id"][:12]
    return ctx


# ── Request models ────────────────────────────────────────────────────────────

class ExecuteSkillRequest(BaseModel):
    skill_id: str
    params:   dict = {}
    enqueue_action: bool = True   # whether to create a B_approve action for review


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/skills/catalog")
async def list_skill_catalog(
    dept_id: Optional[str] = Query(None, description="Filter by department"),
    current_user: dict = Depends(get_current_user),
):
    """List all registered skills across the platform."""
    from agents.skills.skill_registry import get_skill_registry
    registry = get_skill_registry()
    skills   = registry.list_available(dept_id=dept_id)
    return {
        "skills": skills,
        "count":  len(skills),
        "filter": {"dept_id": dept_id},
    }


@router.get("/projects/{project_id}/skills/available")
async def list_available_skills(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all skills available for this project's department (universal + dept-specific)."""
    proj_row = _get_project_row(project_id)
    dept_id  = proj_row.get("dept_id") or "all"

    from agents.skills.skill_registry import get_skill_registry
    registry = get_skill_registry()
    skills   = registry.list_available(dept_id=dept_id)

    return {
        "project_id": project_id,
        "dept_id":    dept_id,
        "skills":     skills,
        "count":      len(skills),
    }


@router.get("/projects/{project_id}/skills/detect")
async def detect_skill(
    project_id: str,
    query: str  = Query(..., description="Natural language query to detect skill from"),
    current_user: dict = Depends(get_current_user),
):
    """Auto-detect which skill best matches a query for this project's department."""
    proj_row = _get_project_row(project_id)
    dept_id  = proj_row.get("dept_id") or "all"

    from agents.skills.skill_registry import get_skill_registry
    registry = get_skill_registry()
    skill    = registry.detect(query, dept_id=dept_id)

    if not skill:
        return {
            "project_id":     project_id,
            "detected_skill": None,
            "message":        "No skill matched this query.",
        }

    return {
        "project_id":     project_id,
        "detected_skill": {
            "skill_id":      skill.skill_id,
            "dept_id":       skill.dept_id,
            "description":   skill.description,
            "output_format": skill.output_format,
        },
    }


@router.post("/projects/{project_id}/skills/execute")
async def execute_skill(
    project_id: str,
    req:        ExecuteSkillRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Execute a skill for a project.

    Returns the SkillOutput metadata and (if a file was generated)
    a download_url pointing to GET /projects/{id}/skills/download/{filename}.

    If enqueue_action=true (default), a Category B action is created
    awaiting human review before the file is considered approved.
    """
    proj_row  = _get_project_row(project_id)
    context   = _build_context(proj_row)

    from agents.skills.skill_registry import get_skill_registry
    registry = get_skill_registry()

    logger.info(
        f"[Skills] execute skill='{req.skill_id}' project={project_id[:8]} "
        f"user={current_user['sub']}"
    )

    output = await registry.execute(req.skill_id, context, req.params)

    result = output.to_dict()

    # Attach download URL if a file was produced
    if output.file_path and os.path.exists(output.file_path):
        filename = os.path.basename(output.file_path)
        result["download_url"] = f"/projects/{project_id}/skills/download/{filename}"

    # Enqueue a B_approve action so human must review before file is distributed
    if req.enqueue_action and output.success:
        try:
            from infrastructure.action_queue import get_action_queue, ActionCategory
            aq = get_action_queue(proj_row["db_path"], project_id, proj_row["tenant_id"])
            action = aq.enqueue(
                agent_dept   = output.dept_id,
                action_type  = f"skill_output_{output.skill_id}",
                category     = ActionCategory.B_APPROVE,
                title        = f"Review & approve: {output.title}",
                description  = f"Agent generated {output.file_format.upper()} document via skill '{output.skill_id}'. Review before distributing.",
                reasoning    = output.preview,
                evidence     = {
                    "skill_id":    output.skill_id,
                    "file_format": output.file_format,
                    "file_path":   output.file_path or "",
                    "pages":       output.pages,
                },
                output_file_path = output.file_path,
                priority     = "medium",
            )
            result["action_id"] = action.action_id
            result["message"]   = "Skill executed. Document queued for human review."
        except Exception as e:
            logger.warning(f"[Skills] Could not enqueue action: {e}")
            result["message"] = "Skill executed. Document ready (action queue unavailable)."
    else:
        result["message"] = "Skill executed." if output.success else f"Skill failed: {output.error}"

    return result


@router.get("/projects/{project_id}/skills/download/{filename}")
async def download_skill_output(
    project_id: str,
    filename:   str,
    current_user: dict = Depends(get_current_user),
):
    """Download a generated skill output file."""
    proj_row = _get_project_row(project_id)
    tenant_id = proj_row["tenant_id"]

    # Validate filename (no path traversal)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    doc_dir  = os.path.join("data", "documents", "projects", tenant_id, project_id)
    file_path = os.path.join(doc_dir, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

    # Determine media type
    ext_map = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".html": "text/html",
        ".pdf":  "application/pdf",
    }
    ext        = os.path.splitext(filename)[1].lower()
    media_type = ext_map.get(ext, "application/octet-stream")

    return FileResponse(
        path         = file_path,
        filename     = filename,
        media_type   = media_type,
    )


@router.get("/projects/{project_id}/documents")
async def list_project_documents(
    project_id: str,
    limit:      int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """
    List all generated documents for a project.
    Reads from project_documents table + filesystem scan.
    """
    proj_row  = _get_project_row(project_id)
    db_path   = proj_row.get("db_path") or ""
    tenant_id = proj_row["tenant_id"]

    documents = []

    # Try project_documents table first
    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT doc_id, title, file_path, file_format, report_type, "
                "pages, produced_by, created_at "
                "FROM project_documents ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            for r in rows:
                d = dict(r)
                if d.get("file_path") and os.path.exists(d["file_path"]):
                    filename = os.path.basename(d["file_path"])
                    d["download_url"] = f"/projects/{project_id}/skills/download/{filename}"
                documents.append(d)
        except Exception as e:
            logger.debug(f"[Skills] project_documents table unavailable: {e}")

    # Fallback: scan filesystem if table is empty
    if not documents:
        doc_dir = os.path.join("data", "documents", "projects", tenant_id, project_id)
        if os.path.isdir(doc_dir):
            import glob as _glob
            from datetime import datetime as _dt
            files = _glob.glob(os.path.join(doc_dir, "*"))
            files.sort(key=os.path.getmtime, reverse=True)
            for fp in files[:limit]:
                filename = os.path.basename(fp)
                ext = os.path.splitext(filename)[1].lower().lstrip(".")
                documents.append({
                    "title":        filename,
                    "file_path":    fp,
                    "file_format":  ext,
                    "created_at":   _dt.utcfromtimestamp(os.path.getmtime(fp)).isoformat(),
                    "download_url": f"/projects/{project_id}/skills/download/{filename}",
                })

    return {
        "project_id": project_id,
        "documents":  documents,
        "count":      len(documents),
    }
