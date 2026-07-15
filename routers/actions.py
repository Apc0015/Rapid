"""
routers/actions.py — Human-in-the-Loop Action Queue & Notification API.

Part of RAPID Phase 5.

Endpoints
─────────
  # Action Queue
  GET    /actions                              — List pending/all agent actions (with filters)
  GET    /actions/{action_id}                 — Get a single action
  POST   /actions/{action_id}/approve         — Approve a pending action
  POST   /actions/{action_id}/reject          — Reject a pending action
  GET    /actions/stats                       — Counts by status and category

  # Notifications
  GET    /notifications                        — List user's unread notifications
  GET    /notifications/all                   — List all notifications (with filters)
  POST   /notifications/{notification_id}/read   — Mark notification as read
  POST   /notifications/{notification_id}/dismiss — Dismiss a notification
  GET    /notifications/count                  — Fast unread count

  # Per-project monitoring status
  GET    /projects/{project_id}/monitoring-status — Current monitor state for project
  GET    /projects/{project_id}/actions           — Actions for a specific project
  GET    /projects/{project_id}/notifications     — Notifications for a specific project
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import config
from routers.deps import get_current_user
from infrastructure.action_queue import get_action_queue, ActionStatus
from infrastructure.notification_engine import get_notification_engine
from infrastructure.project_provisioner import get_project_provisioner

router = APIRouter(tags=["actions"])
logger = logging.getLogger("rapid.actions")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_project_db(project_id: str) -> str:
    """Return the SQLite DB path for a project, or raise 404."""
    pp = get_project_provisioner()
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT db_path FROM project_registry WHERE project_id=?",
            (project_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return row["db_path"]


def _get_tenant_id(project_id: str) -> str:
    """Return tenant_id for a project."""
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT tenant_id FROM project_registry WHERE project_id=?",
            (project_id,),
        ).fetchone()
    finally:
        conn.close()
    return row["tenant_id"] if row else "default"


def _all_active_projects(tenant_id: str) -> list[dict]:
    """Return active projects for exactly one authenticated tenant."""
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT project_id, tenant_id, db_path FROM project_registry
               WHERE status != 'archived' AND tenant_id=?""",
            (tenant_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _current_tenant(current_user: dict) -> str:
    """Tokens issued before tenant claims remain single-org ``default`` tokens."""
    return str(current_user.get("tenant_id") or "default")


def _require_action_reviewer(current_user: dict) -> None:
    if current_user.get("role") not in {"admin", "ceo", "manager", "dept_head", "division_head", "c_suite"}:
        raise HTTPException(status_code=403, detail="Reviewer role required to decide an action")


# ── Request / Response models ─────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    notes: Optional[str] = None   # optional reviewer notes (ignored by queue, for audit)


class RejectRequest(BaseModel):
    reason: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# ACTION QUEUE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/actions/stats")
async def get_action_stats(
    current_user: dict = Depends(get_current_user),
):
    """
    Aggregate action queue statistics across all active projects.

    Returns total counts by status and category.
    """
    projects = _all_active_projects(_current_tenant(current_user))
    merged_by_status: dict[str, int] = {}
    merged_by_cat:    dict[str, int] = {}
    total = 0

    for proj in projects:
        try:
            aq = get_action_queue(proj["db_path"], proj["project_id"], proj["tenant_id"])
            s  = aq.stats()
            for k, v in s["by_status"].items():
                merged_by_status[k] = merged_by_status.get(k, 0) + v
            for k, v in s["by_category"].items():
                merged_by_cat[k] = merged_by_cat.get(k, 0) + v
            total += s["total"]
        except Exception as e:
            logger.debug(f"[Actions] stats skip project {proj['project_id']}: {e}")

    return {
        "by_status":   merged_by_status,
        "by_category": merged_by_cat,
        "total":       total,
        "project_count": len(projects),
    }


@router.get("/actions")
async def list_actions(
    status:   Optional[str] = Query(None, description="Filter by status: pending | approved | rejected | executed | expired | cancelled"),
    category: Optional[str] = Query(None, description="Filter by category: A_auto | B_approve | C_human"),
    dept:     Optional[str] = Query(None, description="Filter by agent department"),
    limit:    int           = Query(50,   ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """
    List agent actions across all active projects.

    Defaults to showing pending actions (status=pending) if no filter given.
    """
    effective_status = status if status is not None else ActionStatus.PENDING

    projects = _all_active_projects(_current_tenant(current_user))
    all_actions = []

    for proj in projects:
        try:
            aq = get_action_queue(proj["db_path"], proj["project_id"], proj["tenant_id"])
            actions = aq.list_all(
                status   = effective_status if effective_status else None,
                category = category,
                dept     = dept,
                limit    = limit,
            )
            all_actions.extend(a.to_dict() for a in actions)
        except Exception as e:
            logger.debug(f"[Actions] list skip project {proj['project_id']}: {e}")

    # Sort newest first, trim to limit
    all_actions.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return {
        "actions": all_actions[:limit],
        "count":   len(all_actions[:limit]),
        "filters": {"status": effective_status, "category": category, "dept": dept},
    }


@router.get("/actions/{action_id}")
async def get_action(
    action_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Fetch a single action by ID (searches across all active project DBs).
    """
    projects = _all_active_projects(_current_tenant(current_user))
    for proj in projects:
        try:
            aq = get_action_queue(proj["db_path"], proj["project_id"], proj["tenant_id"])
            action = aq.get(action_id)
            if action:
                return action.to_dict()
        except Exception as e:
            logger.debug(f"[Actions] get skip project {proj['project_id']}: {e}")

    raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found")


@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: str,
    req:       ApproveRequest = ApproveRequest(),
    current_user: dict = Depends(get_current_user),
):
    """
    Approve a pending action.

    The current authenticated user becomes the reviewer.
    """
    _require_action_reviewer(current_user)
    user_id  = current_user["sub"]
    projects = _all_active_projects(_current_tenant(current_user))

    for proj in projects:
        try:
            aq = get_action_queue(proj["db_path"], proj["project_id"], proj["tenant_id"])
            action = aq.get(action_id)
            if action:
                updated = aq.approve(action_id, reviewed_by=user_id)
                if not updated:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Action '{action_id}' cannot be approved (current status: {action.status})",
                    )
                logger.info(f"[Actions] {action_id[:8]} APPROVED by {user_id}")
                return {
                    "success": True,
                    "action":  updated.to_dict(),
                    "message": f"Action approved by {user_id}",
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.debug(f"[Actions] approve skip project {proj['project_id']}: {e}")

    raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found")


@router.post("/actions/{action_id}/reject")
async def reject_action(
    action_id: str,
    req:       RejectRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Reject a pending action.

    Provide a reason in the request body. The current user becomes the reviewer.
    """
    _require_action_reviewer(current_user)
    user_id  = current_user["sub"]
    projects = _all_active_projects(_current_tenant(current_user))

    for proj in projects:
        try:
            aq = get_action_queue(proj["db_path"], proj["project_id"], proj["tenant_id"])
            action = aq.get(action_id)
            if action:
                updated = aq.reject(action_id, reviewed_by=user_id, reason=req.reason)
                if not updated:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Action '{action_id}' cannot be rejected (current status: {action.status})",
                    )
                logger.info(f"[Actions] {action_id[:8]} REJECTED by {user_id}: {req.reason}")
                return {
                    "success": True,
                    "action":  updated.to_dict(),
                    "message": f"Action rejected by {user_id}",
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.debug(f"[Actions] reject skip project {proj['project_id']}: {e}")

    raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found")


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/notifications/count")
async def notification_count(
    current_user: dict = Depends(get_current_user),
):
    """Fast unread notification count across all projects."""
    projects = _all_active_projects(_current_tenant(current_user))
    total = 0
    for proj in projects:
        try:
            ne = get_notification_engine(proj["db_path"], proj["project_id"], proj["tenant_id"])
            total += ne.unread_count()
        except Exception as e:
            logger.debug(f"[Notifications] count skip project {proj['project_id']}: {e}")
    return {"unread_count": total}


@router.get("/notifications")
async def list_notifications(
    limit: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """List all unread (not dismissed) notifications across all active projects."""
    projects = _all_active_projects(_current_tenant(current_user))
    all_notifs = []

    for proj in projects:
        try:
            ne = get_notification_engine(proj["db_path"], proj["project_id"], proj["tenant_id"])
            notifs = ne.list_unread(limit=limit)
            all_notifs.extend(n.to_dict() for n in notifs)
        except Exception as e:
            logger.debug(f"[Notifications] list skip project {proj['project_id']}: {e}")

    all_notifs.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    return {
        "notifications": all_notifs[:limit],
        "count":         len(all_notifs[:limit]),
    }


@router.get("/notifications/all")
async def list_all_notifications(
    severity: Optional[str] = Query(None, description="Filter: info | medium | high | urgent"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit:    int           = Query(100, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """List all notifications (read + unread) with optional filters."""
    projects = _all_active_projects(_current_tenant(current_user))
    all_notifs = []

    for proj in projects:
        try:
            ne = get_notification_engine(proj["db_path"], proj["project_id"], proj["tenant_id"])
            notifs = ne.list_all(severity=severity, category=category, limit=limit)
            all_notifs.extend(n.to_dict() for n in notifs)
        except Exception as e:
            logger.debug(f"[Notifications] list_all skip project {proj['project_id']}: {e}")

    all_notifs.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    return {
        "notifications": all_notifs[:limit],
        "count":         len(all_notifs[:limit]),
        "filters":       {"severity": severity, "category": category},
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark a notification as read by the current user."""
    user_id  = current_user["sub"]
    projects = _all_active_projects(_current_tenant(current_user))

    for proj in projects:
        try:
            ne = get_notification_engine(proj["db_path"], proj["project_id"], proj["tenant_id"])
            # Check if this notification exists in this project's DB
            conn = sqlite3.connect(f"file:{proj['db_path']}?mode=ro", uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT notification_id FROM project_notifications WHERE notification_id=?",
                    (notification_id,),
                ).fetchone()
            finally:
                conn.close()

            if row:
                ok = ne.mark_read(notification_id, user_id=user_id)
                if not ok:
                    raise HTTPException(status_code=400, detail="Could not mark notification as read")
                return {"success": True, "notification_id": notification_id, "read_by": user_id}

        except HTTPException:
            raise
        except Exception as e:
            logger.debug(f"[Notifications] read skip project {proj['project_id']}: {e}")

    raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Dismiss a notification (hide from unread list)."""
    projects = _all_active_projects(_current_tenant(current_user))

    for proj in projects:
        try:
            ne = get_notification_engine(proj["db_path"], proj["project_id"], proj["tenant_id"])
            conn = sqlite3.connect(f"file:{proj['db_path']}?mode=ro", uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT notification_id FROM project_notifications WHERE notification_id=?",
                    (notification_id,),
                ).fetchone()
            finally:
                conn.close()

            if row:
                ok = ne.dismiss(notification_id)
                if not ok:
                    raise HTTPException(status_code=400, detail="Could not dismiss notification")
                return {"success": True, "notification_id": notification_id}

        except HTTPException:
            raise
        except Exception as e:
            logger.debug(f"[Notifications] dismiss skip project {proj['project_id']}: {e}")

    raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")


# ══════════════════════════════════════════════════════════════════════════════
# PER-PROJECT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/projects/{project_id}/monitoring-status")
async def project_monitoring_status(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Return the current BackgroundMonitor status plus project-specific
    unread notification and pending action counts.
    """
    db_path   = _get_project_db(project_id)
    tenant_id = _get_tenant_id(project_id)

    # Get monitor global status
    try:
        from infrastructure.monitoring_loop import get_background_monitor
        monitor = get_background_monitor()
        monitor_status = monitor.status
    except Exception as e:
        logger.warning(f"[Actions] Could not get monitor status: {e}")
        monitor_status = {"error": str(e)}

    # Per-project counts
    try:
        aq = get_action_queue(db_path, project_id, tenant_id)
        pending_actions = aq.pending_count()
        action_stats    = aq.stats()
    except Exception as e:
        pending_actions = 0
        action_stats    = {}

    try:
        ne = get_notification_engine(db_path, project_id, tenant_id)
        unread_notifications = ne.unread_count()
    except Exception as e:
        unread_notifications = 0

    return {
        "project_id":            project_id,
        "monitor":               monitor_status,
        "pending_actions":       pending_actions,
        "action_stats":          action_stats,
        "unread_notifications":  unread_notifications,
    }


@router.get("/projects/{project_id}/actions")
async def list_project_actions(
    project_id: str,
    status:     Optional[str] = Query(None),
    limit:      int           = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """List action queue entries for a specific project."""
    db_path   = _get_project_db(project_id)
    tenant_id = _get_tenant_id(project_id)

    aq      = get_action_queue(db_path, project_id, tenant_id)
    actions = aq.list_all(status=status, limit=limit)
    return {
        "project_id": project_id,
        "actions":    [a.to_dict() for a in actions],
        "count":      len(actions),
    }


@router.get("/projects/{project_id}/notifications")
async def list_project_notifications(
    project_id: str,
    unread_only: bool          = Query(True),
    severity:    Optional[str] = Query(None),
    limit:       int           = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """List notifications for a specific project."""
    db_path   = _get_project_db(project_id)
    tenant_id = _get_tenant_id(project_id)

    ne = get_notification_engine(db_path, project_id, tenant_id)

    if unread_only:
        notifs = ne.list_unread(limit=limit)
    else:
        notifs = ne.list_all(severity=severity, limit=limit)

    return {
        "project_id":    project_id,
        "notifications": [n.to_dict() for n in notifs],
        "count":         len(notifs),
    }
