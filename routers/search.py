"""
routers/search.py — Global Search API

Endpoints
─────────
  GET  /search?q=&limit=&sources=    → Cross-tenant universal search
  GET  /search/suggest?q=            → Autocomplete suggestions (people + projects)
  GET  /search/recent                → Recent search activity (tenant-wide)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from routers.deps import get_current_user
from infrastructure.global_search import get_global_search

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger("rapid.search_router")


def _get_tenant(current_user: dict) -> str:
    return current_user.get("tenant_id") or current_user.get("sub", "default")


def _project_scope_sql(current_user: dict, tenant_id: str, alias: str = "") -> tuple[str, list[str]]:
    if current_user.get("role") in {"admin", "ceo"}:
        return "", [tenant_id]
    return (
        f" AND {alias}project_id IN (SELECT project_id FROM project_members WHERE tenant_id=? AND user_id=? AND status='active')",
        [tenant_id, current_user["sub"]],
    )


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def global_search(
    q:       str            = Query(..., min_length=1, max_length=500, description="Search query"),
    limit:   int            = Query(20, ge=1, le=100),
    sources: Optional[str]  = Query(None, description="Comma-separated: bm25,vector,graph,people"),
    current_user: dict      = Depends(get_current_user),
):
    """
    Global search across all accessible projects, documents, people, and graph nodes.

    Results are access-controlled — users only see data from projects they belong to.
    Admins, CEOs, and C-suite see all tenant data.

    Sources:
      bm25   — keyword search in project KPIs, risks, milestones, docs
      vector — semantic/similarity search via FAISS embeddings
      graph  — knowledge graph node search
      people — people directory search
    """
    tenant_id  = _get_tenant(current_user)
    user_id    = current_user.get("sub", "")
    role       = current_user.get("role", "employee")

    source_list = (
        [s.strip() for s in sources.split(",") if s.strip()]
        if sources
        else ["bm25", "graph", "people", "vector"]
    )

    engine = get_global_search()
    results = await engine.search(
        query     = q,
        tenant_id = tenant_id,
        user_id   = user_id,
        role      = role,
        limit     = limit,
        sources   = source_list,
    )
    return results


@router.get("/suggest")
async def search_suggest(
    q:     str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=30),
    current_user: dict = Depends(get_current_user),
):
    """
    Fast autocomplete suggestions: people names + project names matching the prefix.
    """
    import sqlite3
    import config

    tenant_id = _get_tenant(current_user)
    suggestions: list[dict] = []
    pat = f"%{q}%"

    # People suggestions
    try:
        from infrastructure.people_directory import get_people_directory
        directory = get_people_directory()
        people = directory.search(tenant_id=tenant_id, query=q, limit=5)
        if current_user.get("role") not in {"admin", "ceo"}:
            allowed = set(current_user.get("depts") or [])
            people = [person for person in people if not person.dept_id or person.dept_id in allowed]
        for p in people:
            suggestions.append({
                "type":  "person",
                "label": p.name,
                "id":    p.person_id,
                "meta":  f"{p.role} · {p.dept_id or ''}",
            })
    except Exception:
        pass

    # Project suggestions
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        scope_sql, scope_params = _project_scope_sql(current_user, tenant_id)
        rows = conn.execute(
            "SELECT project_id, name FROM project_registry "
            f"WHERE tenant_id=? AND name LIKE ? AND status='active'{scope_sql} LIMIT ?",
            (tenant_id, pat, *scope_params[1:], limit - len(suggestions)),
        ).fetchall()
        conn.close()
        for r in rows:
            suggestions.append({
                "type":  "project",
                "label": r["name"],
                "id":    r["project_id"],
                "meta":  "Project",
            })
    except Exception:
        pass

    return {
        "query":       q,
        "suggestions": suggestions[:limit],
        "count":       len(suggestions[:limit]),
    }


@router.get("/recent")
async def recent_searches(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """
    Return recent action queue and notification activity as a search-history proxy.
    (Full search history logging is a future feature; this surfaces recent activity.)
    """
    import sqlite3
    import config

    tenant_id = _get_tenant(current_user)
    activity: list[dict] = []

    conn = sqlite3.connect(config.DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        # Use project names as recent activity (JOIN projects for name/updated_at)
        scope_sql, scope_params = _project_scope_sql(current_user, tenant_id, "pr.")
        rows = conn.execute(
            """
            SELECT COALESCE(p.name, pr.project_id) AS name,
                   pr.project_id,
                   COALESCE(p.updated_at, pr.last_accessed, pr.provisioned_at) AS updated_at
            FROM project_registry pr
            LEFT JOIN projects p ON pr.project_id = p.project_id
            WHERE pr.tenant_id=? AND pr.status != 'archived'
            """ + scope_sql + """
            ORDER BY updated_at DESC LIMIT ?
            """,
            (tenant_id, *scope_params[1:], limit),
        ).fetchall()
        for r in rows:
            activity.append({
                "type":       "project_activity",
                "label":      r["name"],
                "project_id": r["project_id"],
                "timestamp":  r["updated_at"],
            })
    except Exception:
        pass
    finally:
        conn.close()

    return {
        "tenant_id": tenant_id,
        "recent":    activity,
        "count":     len(activity),
    }
