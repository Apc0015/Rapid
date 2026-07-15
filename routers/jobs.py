"""Administrative visibility and control for durable background jobs."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from infrastructure.job_queue import JobQueueError, get_job_queue
from routers.deps import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _tenant(user: dict) -> str:
    return str(user.get("tenant_id") or "default")


def _require_admin(user: dict) -> None:
    if user.get("role") not in {"admin", "ceo"}:
        raise HTTPException(status_code=403, detail="Organization administrator role required")


@router.get("")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    queue = get_job_queue()
    return {
        "jobs": queue.list(_tenant(current_user), status, limit),
        "stats": queue.stats(_tenant(current_user)),
        "workers": queue.worker_status(),
    }


@router.get("/{job_id}")
async def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        return {"job": get_job_queue().get(_tenant(current_user), job_id)}
    except JobQueueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{job_id}/retry")
async def retry_job(job_id: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        return {"job": get_job_queue().retry_dead_letter(_tenant(current_user), job_id)}
    except JobQueueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
