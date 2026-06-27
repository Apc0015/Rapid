"""
routers/library.py — Document Library API

Endpoints
─────────
  GET  /library                     → List all tenant documents (access-filtered)
  GET  /library/stats               → Tenant library statistics
  GET  /library/search?q=           → Search documents by title/type
  POST /library/sync                → Sync docs from all project DBs into library
  GET  /library/{doc_id}            → Get document metadata
  DELETE /library/{doc_id}          → Soft-delete document
  POST /library/register            → Manually register an existing file
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from routers.deps import get_current_user
from infrastructure.document_library import get_document_library, ACCESS_PROJECT

router = APIRouter(prefix="/library", tags=["document-library"])
logger = logging.getLogger("rapid.library_router")


def _get_tenant(current_user: dict) -> str:
    return current_user.get("tenant_id") or current_user.get("sub", "default")


# ── Request models ────────────────────────────────────────────────────────────

class RegisterDocRequest(BaseModel):
    title:        str
    file_format:  str         = "docx"
    project_id:   Optional[str] = None
    file_path:    Optional[str] = None
    report_type:  Optional[str] = None
    produced_by:  Optional[str] = None
    dept_id:      Optional[str] = None
    access_level: str         = ACCESS_PROJECT
    page_count:   int         = 0


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_library(
    project_id:  Optional[str] = Query(None),
    dept_id:     Optional[str] = Query(None),
    file_format: Optional[str] = Query(None),
    report_type: Optional[str] = Query(None),
    produced_by: Optional[str] = Query(None),
    limit:       int           = Query(50, ge=1, le=200),
    offset:      int           = Query(0, ge=0),
    current_user: dict         = Depends(get_current_user),
):
    """
    List documents in the library.
    Access-controlled: non-admin users only see documents in their accessible projects.
    """
    tenant_id = _get_tenant(current_user)
    library   = get_document_library()

    docs = library.list(
        tenant_id   = tenant_id,
        project_id  = project_id,
        dept_id     = dept_id,
        file_format = file_format,
        report_type = report_type,
        produced_by = produced_by,
        limit       = limit,
        offset      = offset,
    )
    return {
        "documents": [d.to_dict() for d in docs],
        "count":     len(docs),
        "offset":    offset,
        "filters": {
            "project_id":  project_id,
            "dept_id":     dept_id,
            "file_format": file_format,
            "report_type": report_type,
        },
    }


@router.get("/stats")
async def library_stats(
    current_user: dict = Depends(get_current_user),
):
    """Return library statistics — total docs, by format, total size."""
    tenant_id = _get_tenant(current_user)
    library   = get_document_library()
    return {
        "tenant_id": tenant_id,
        **library.stats(tenant_id),
    }


@router.get("/search")
async def search_library(
    q:     str = Query(..., min_length=1, max_length=300),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Search library by title, report type, department, or format."""
    tenant_id = _get_tenant(current_user)
    library   = get_document_library()
    docs      = library.search(tenant_id=tenant_id, query=q, limit=limit)
    return {
        "query":     q,
        "documents": [d.to_dict() for d in docs],
        "count":     len(docs),
    }


@router.post("/sync")
async def sync_from_projects(
    current_user: dict = Depends(get_current_user),
):
    """
    Scan all active project DBs and pull their project_documents records
    into the central library. Admin/manager only.
    """
    if current_user.get("role") not in ("admin", "manager", "c_suite", "ceo"):
        raise HTTPException(status_code=403, detail="Admin role required")

    import sqlite3
    import config

    tenant_id = _get_tenant(current_user)
    library   = get_document_library()

    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    projects = conn.execute(
        "SELECT project_id, db_path FROM project_registry "
        "WHERE tenant_id=? AND status='active'",
        (tenant_id,),
    ).fetchall()
    conn.close()

    total_synced = 0
    for proj in projects:
        n = library.sync_from_project_db(
            db_path    = proj["db_path"],
            project_id = proj["project_id"],
            tenant_id  = tenant_id,
        )
        total_synced += n

    return {
        "message":        f"Synced {total_synced} documents from {len(projects)} projects",
        "projects_scanned": len(projects),
        "documents_synced": total_synced,
    }


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get document metadata by ID."""
    library = get_document_library()
    doc     = library.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    tenant_id = _get_tenant(current_user)
    if doc.tenant_id != tenant_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    return {"document": doc.to_dict()}


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Soft-delete a document from the library (admin/manager only)."""
    if current_user.get("role") not in ("admin", "manager", "dept_head",
                                         "c_suite", "ceo"):
        raise HTTPException(status_code=403, detail="Manager role required")

    library = get_document_library()
    success = library.delete(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    return {"message": "Document removed from library", "doc_id": doc_id}


@router.post("/register", status_code=201)
async def register_document(
    req: RegisterDocRequest,
    current_user: dict = Depends(get_current_user),
):
    """Manually register an existing file in the library (admin/manager only)."""
    if current_user.get("role") not in ("admin", "manager", "dept_head",
                                         "c_suite", "ceo"):
        raise HTTPException(status_code=403, detail="Manager role required")

    tenant_id = _get_tenant(current_user)
    library   = get_document_library()

    doc = library.register(
        tenant_id   = tenant_id,
        title       = req.title,
        file_format = req.file_format,
        project_id  = req.project_id,
        file_path   = req.file_path,
        report_type = req.report_type,
        produced_by = req.produced_by or current_user.get("sub"),
        dept_id     = req.dept_id,
        access_level= req.access_level,
        page_count  = req.page_count,
    )
    return {"document": doc.to_dict(), "message": "Document registered in library"}
