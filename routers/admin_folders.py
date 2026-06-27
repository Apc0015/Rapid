"""
routers/admin_folders.py — Local folder watcher management (admin only).

Endpoints:
  POST   /admin/folders/watch          — Register + start a new folder watcher
  GET    /admin/folders/watchers       — List all active watchers
  GET    /admin/folders/watchers/{id}  — Get watcher details + stats
  POST   /admin/folders/watchers/{id}/scan  — Trigger an immediate scan
  DELETE /admin/folders/watchers/{id}  — Stop and remove a watcher
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.deps import require_admin

router = APIRouter(prefix="/admin/folders", tags=["admin-folders"])
logger = logging.getLogger("rapid.admin_folders")


# ── Request models ─────────────────────────────────────────────────────────────

class WatchFolderRequest(BaseModel):
    path:             str                       # absolute path on the server
    dept_tag:         Optional[str] = None      # company KB department tag
    project_id:       Optional[str] = None      # project-scoped KB
    interval_seconds: int = 60                  # how often to scan (min 10s)
    extensions:       Optional[list[str]] = None  # file types to watch


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/watch")
async def watch_folder(
    req: WatchFolderRequest,
    current_user: dict = Depends(require_admin),
):
    """
    Register a local folder for automatic ingestion.

    RAPID will poll this directory every `interval_seconds` seconds.
    New files and modified files are ingested automatically.

    - dept_tag   → file contents go into the company-wide department KB
    - project_id → file contents go into a specific project's KB

    The path must be accessible from the RAPID server process.
    In Docker, mount it as a volume first.
    """
    if not req.dept_tag and not req.project_id:
        raise HTTPException(status_code=400, detail="Provide dept_tag or project_id")

    from infrastructure.folder_watcher import get_folder_watcher
    manager = get_folder_watcher()

    try:
        cfg = manager.add_watcher(
            path=req.path,
            dept_tag=req.dept_tag,
            project_id=req.project_id,
            interval_seconds=req.interval_seconds,
            extensions=req.extensions,
            created_by=current_user["sub"],
        )
        manager.start_watcher(cfg.watcher_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        f"[admin/folders] Admin {current_user['sub']} started watcher "
        f"{cfg.watcher_id} → {req.path}"
    )
    return {
        "watcher_id":       cfg.watcher_id,
        "path":             cfg.path,
        "dept_tag":         cfg.dept_tag,
        "project_id":       cfg.project_id,
        "interval_seconds": cfg.interval_seconds,
        "status":           "running",
        "message":          f"Watching '{req.path}' — first scan starts immediately",
    }


@router.get("/watchers")
async def list_watchers(current_user: dict = Depends(require_admin)):
    """List all registered folder watchers with their stats."""
    from infrastructure.folder_watcher import get_folder_watcher
    watchers = get_folder_watcher().list_watchers()
    return {"count": len(watchers), "watchers": watchers}


@router.get("/watchers/{watcher_id}")
async def get_watcher(
    watcher_id: str,
    current_user: dict = Depends(require_admin),
):
    """Get details and stats for a specific watcher."""
    from infrastructure.folder_watcher import get_folder_watcher
    data = get_folder_watcher().get_watcher(watcher_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Watcher {watcher_id} not found")
    return data


@router.post("/watchers/{watcher_id}/scan")
async def trigger_scan(
    watcher_id: str,
    current_user: dict = Depends(require_admin),
):
    """Force an immediate scan of a watched folder (outside the regular interval)."""
    from infrastructure.folder_watcher import get_folder_watcher
    manager = get_folder_watcher()
    if not manager.get_watcher(watcher_id):
        raise HTTPException(status_code=404, detail=f"Watcher {watcher_id} not found")
    try:
        result = await manager.trigger_scan(watcher_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")

    logger.info(
        f"[admin/folders] Manual scan triggered by {current_user['sub']} "
        f"for watcher {watcher_id}: {result}"
    )
    return {"watcher_id": watcher_id, **result}


@router.delete("/watchers/{watcher_id}")
async def stop_watcher(
    watcher_id: str,
    current_user: dict = Depends(require_admin),
):
    """Stop and remove a folder watcher."""
    from infrastructure.folder_watcher import get_folder_watcher
    manager = get_folder_watcher()
    if not manager.get_watcher(watcher_id):
        raise HTTPException(status_code=404, detail=f"Watcher {watcher_id} not found")
    await manager.stop_watcher(watcher_id)
    logger.info(f"[admin/folders] Watcher {watcher_id} stopped by {current_user['sub']}")
    return {"watcher_id": watcher_id, "status": "stopped"}
