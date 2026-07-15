"""
routers/cloud_gdrive.py — Google Drive integration endpoints.

Endpoints:
  GET  /cloud/gdrive/connect          — Get OAuth2 authorization URL
  GET  /cloud/gdrive/callback         — OAuth2 callback (receives code from Google)
  GET  /cloud/gdrive/status           — Connection status + connected email
  DELETE /cloud/gdrive/disconnect     — Revoke token
  GET  /cloud/gdrive/files            — List files in a folder
  GET  /cloud/gdrive/search           — Search files by text
  POST /cloud/gdrive/import/folder    — Ingest a whole folder into KB
  POST /cloud/gdrive/import/file      — Ingest a single file into KB
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from routers.deps import get_current_user
from infrastructure.cloud_tokens import is_connected, delete_token

router = APIRouter(prefix="/cloud/gdrive", tags=["cloud-gdrive"])
logger = logging.getLogger("rapid.gdrive_router")


# ── Request models ─────────────────────────────────────────────────────────────

class ImportFolderRequest(BaseModel):
    folder_id:  str = "root"
    dept_tag:   Optional[str] = None
    project_id: Optional[str] = None
    recursive:  bool = False


class ImportFileRequest(BaseModel):
    file_id:    str
    file_name:  str
    mime_type:  str
    dept_tag:   Optional[str] = None
    project_id: Optional[str] = None


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@router.get("/connect")
async def connect(current_user: dict = Depends(get_current_user)):
    """Return the Google OAuth2 URL for Drive access."""
    from infrastructure.gdrive_connector import get_auth_url
    try:
        url = get_auth_url(current_user["sub"])
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"auth_url": url}


@router.get("/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    """Google redirects here after the user grants Drive access."""
    frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost")
    if error:
        return RedirectResponse(f"{frontend_base}/workspace/settings?cloud_error=gdrive&detail={error}")
    if not code or not state:
        return RedirectResponse(f"{frontend_base}/workspace/settings?cloud_error=gdrive&detail=missing_params")
    try:
        from infrastructure.gdrive_connector import exchange_code
        await exchange_code(code, state)
    except Exception as e:
        return RedirectResponse(f"{frontend_base}/workspace/settings?cloud_error=gdrive&detail={str(e)[:80]}")
    return RedirectResponse(f"{frontend_base}/workspace/settings?cloud_connected=gdrive")


@router.get("/status")
async def status(current_user: dict = Depends(get_current_user)):
    """Check if Google Drive is connected for this user."""
    user_id = current_user["sub"]
    connected = is_connected("gdrive", user_id)
    email = ""
    if connected:
        from infrastructure.gdrive_connector import get_connected_email
        email = await get_connected_email(user_id)
    return {"connected": connected, "email": email}


@router.delete("/disconnect")
async def disconnect(current_user: dict = Depends(get_current_user)):
    """Revoke Google Drive token."""
    delete_token("gdrive", current_user["sub"])
    return {"disconnected": True}


# ── File listing ───────────────────────────────────────────────────────────────

@router.get("/files")
async def list_files(
    folder_id: str  = Query("root", description="Drive folder ID or 'root'"),
    page_size: int  = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """List files in a Google Drive folder."""
    from infrastructure.gdrive_connector import list_folder
    try:
        files = await list_folder(current_user["sub"], folder_id, page_size)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"folder_id": folder_id, "count": len(files), "files": files}


@router.get("/search")
async def search_files(
    q:         str = Query(..., description="Search query"),
    page_size: int = Query(30, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Full-text search across the user's Google Drive."""
    from infrastructure.gdrive_connector import search_files as _search
    try:
        files = await _search(current_user["sub"], q, page_size)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"query": q, "count": len(files), "files": files}


# ── Ingestion ──────────────────────────────────────────────────────────────────

@router.post("/import/folder")
async def import_folder(
    req: ImportFolderRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Download all supported files from a Drive folder and ingest into KB.

    - dept_tag   → company knowledge base (admin only)
    - project_id → project-scoped knowledge base (any project member)
    """
    role = current_user.get("role", "")
    if req.dept_tag and role not in ("admin",):
        raise HTTPException(status_code=403, detail="Only admins can ingest into the company knowledge base")
    if not req.dept_tag and not req.project_id:
        raise HTTPException(status_code=400, detail="Provide dept_tag or project_id")

    from infrastructure.gdrive_connector import ingest_folder
    try:
        result = await ingest_folder(
            user_id=current_user["sub"],
            folder_id=req.folder_id,
            dept_tag=req.dept_tag,
            project_id=req.project_id,
            recursive=req.recursive,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Google Drive folder import failed")
        raise HTTPException(status_code=502, detail=f"Import failed: {str(e)}")

    logger.info(
        f"[gdrive/import/folder] user={current_user['sub']} folder={req.folder_id} "
        f"ingested={result['files_ingested']} chunks={result['chunks_created']}"
    )
    return result


@router.post("/import/file")
async def import_file(
    req: ImportFileRequest,
    current_user: dict = Depends(get_current_user),
):
    """Ingest a single Google Drive file by its file ID."""
    role = current_user.get("role", "")
    if req.dept_tag and role not in ("admin",):
        raise HTTPException(status_code=403, detail="Only admins can ingest into the company knowledge base")
    if not req.dept_tag and not req.project_id:
        raise HTTPException(status_code=400, detail="Provide dept_tag or project_id")

    from infrastructure.gdrive_connector import ingest_file
    try:
        result = await ingest_file(
            user_id=current_user["sub"],
            file_id=req.file_id,
            file_name=req.file_name,
            mime_type=req.mime_type,
            dept_tag=req.dept_tag,
            project_id=req.project_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Google Drive file import failed")
        raise HTTPException(status_code=502, detail=f"Import failed: {str(e)}")

    logger.info(
        f"[gdrive/import/file] user={current_user['sub']} file={req.file_id} "
        f"chunks={result['chunks_created']}"
    )
    return result
