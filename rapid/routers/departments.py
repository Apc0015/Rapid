from __future__ import annotations
"""
routers/departments.py — Per-department RAG and DB configuration endpoints.

Admin-only. Lets the admin panel read and update each department's
RAG pipeline settings and database connection settings.

Routes:
  GET  /departments                           → list all depts with their config summaries
  GET  /departments/{dept}/rag-config         → get dept RAG config
  PUT  /departments/{dept}/rag-config         → update dept RAG config fields
  GET  /departments/{dept}/db-config          → get dept DB config (password redacted)
  PUT  /departments/{dept}/db-config          → update dept DB config fields
  POST /departments/{dept}/db-test            → test DB connection (returns ok/error)
  GET  /departments/{dept}/rag-stats          → doc count + source list for dept index
"""

import logging
from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from routers.deps import require_admin
from infrastructure.dept_config import get_dept_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/departments", tags=["departments"])

ALL_DEPTS = [
    "finance", "hr", "legal", "sales", "marketing",
    "ops", "it", "procurement", "rd", "customer_success",
]


# ── Request / Response models ─────────────────────────────────────────────────

class RagConfigUpdate(BaseModel):
    embedding_model:     Optional[str]   = None
    chunk_size:          Optional[int]   = None
    chunk_overlap:       Optional[int]   = None
    top_k:               Optional[int]   = None
    similarity_threshold: Optional[float] = None
    rrf_alpha:           Optional[float] = None
    bm25_alpha:          Optional[float] = None
    hyde_enabled:        Optional[bool]  = None


class DbConfigUpdate(BaseModel):
    enabled:  Optional[bool]  = None
    type:     Optional[str]   = None   # "sqlite" | "postgresql" | "mysql"
    path:     Optional[str]   = None   # sqlite only
    host:     Optional[str]   = None
    port:     Optional[int]   = None
    name:     Optional[str]   = None   # database name
    user:     Optional[str]   = None
    password: Optional[str]   = None   # stored only; never returned


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_departments(current_user: dict = Depends(require_admin)):
    cfg = get_dept_config()
    result = []
    for dept in ALL_DEPTS:
        rag = cfg.get_rag(dept)
        db  = cfg.get_db(dept)
        result.append({
            "dept": dept,
            "rag": {
                "embedding_model": rag.get("embedding_model"),
                "top_k":           rag.get("top_k"),
                "hyde_enabled":    rag.get("hyde_enabled"),
            },
            "db": {
                "enabled": db.get("enabled", False),
                "type":    db.get("type", "sqlite"),
            },
        })
    return result


@router.get("/{dept}/rag-config")
async def get_rag_config(dept: str, current_user: dict = Depends(require_admin)):
    _validate_dept(dept)
    return get_dept_config().get_rag(dept)


@router.put("/{dept}/rag-config")
async def update_rag_config(dept: str, body: RagConfigUpdate,
                            current_user: dict = Depends(require_admin)):
    _validate_dept(dept)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updated = get_dept_config().set_rag(dept, updates)
    logger.info(f"[departments] RAG config updated for dept={dept}: {list(updates.keys())}")
    return {"dept": dept, "rag_config": updated}


@router.get("/{dept}/db-config")
async def get_db_config(dept: str, current_user: dict = Depends(require_admin)):
    _validate_dept(dept)
    cfg = get_dept_config().get_db(dept)
    # Never return the password
    safe = {k: v for k, v in cfg.items() if k != "password"}
    return safe


@router.put("/{dept}/db-config")
async def update_db_config(dept: str, body: DbConfigUpdate,
                           current_user: dict = Depends(require_admin)):
    _validate_dept(dept)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    get_dept_config().set_db(dept, updates)
    logger.info(f"[departments] DB config updated for dept={dept}: {list(updates.keys())}")
    # Return safe view (no password)
    safe = {k: v for k, v in get_dept_config().get_db(dept).items() if k != "password"}
    return {"dept": dept, "db_config": safe}


@router.post("/{dept}/db-test")
async def test_db_connection(dept: str, current_user: dict = Depends(require_admin)):
    _validate_dept(dept)
    cfg = get_dept_config().get_db(dept)
    if not cfg.get("enabled"):
        return {"ok": False, "error": "DB not enabled for this department"}

    db_type = cfg.get("type", "sqlite")
    try:
        if db_type == "sqlite":
            import sqlite3
            from pathlib import Path
            db_path = cfg.get("path") or f"data/db/{dept}.db"
            if not Path(db_path).exists():
                return {"ok": False, "error": f"SQLite file not found: {db_path}"}
            conn = sqlite3.connect(db_path)
            conn.execute("SELECT 1")
            conn.close()
            return {"ok": True, "type": "sqlite", "path": db_path}

        elif db_type == "postgresql":
            import psycopg2  # type: ignore
            conn = psycopg2.connect(
                host=cfg.get("host", "localhost"),
                port=cfg.get("port", 5432),
                dbname=cfg.get("name", ""),
                user=cfg.get("user", ""),
                password=cfg.get("password", ""),
                connect_timeout=5,
            )
            conn.close()
            return {"ok": True, "type": "postgresql"}

        elif db_type == "mysql":
            import pymysql  # type: ignore
            conn = pymysql.connect(
                host=cfg.get("host", "localhost"),
                port=cfg.get("port", 3306),
                database=cfg.get("name", ""),
                user=cfg.get("user", ""),
                password=cfg.get("password", ""),
                connect_timeout=5,
            )
            conn.close()
            return {"ok": True, "type": "mysql"}

        else:
            return {"ok": False, "error": f"Unknown DB type: {db_type}"}

    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/{dept}/rag-stats")
async def get_rag_stats(dept: str, current_user: dict = Depends(require_admin)):
    _validate_dept(dept)
    try:
        from infrastructure.faiss_store import get_dept_index
        from infrastructure.dept_config import get_dept_config as _get_cfg
        from infrastructure.embedding_service import get_embedder

        rag_cfg = _get_cfg().get_rag(dept)
        dim     = get_embedder().dim_for_model(rag_cfg.get("embedding_model"))
        index   = get_dept_index(dept, dim=dim)
        sources = index.list_sources()
        return {
            "dept":       dept,
            "doc_count":  index.doc_count,
            "sources":    sources,
            "index_dim":  dim,
        }
    except Exception as e:
        logger.warning(f"[departments] RAG stats failed for dept={dept}: {e}")
        return {"dept": dept, "doc_count": 0, "sources": [], "error": str(e)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_dept(dept: str):
    if dept not in ALL_DEPTS:
        raise HTTPException(status_code=404, detail=f"Unknown department: '{dept}'. "
                            f"Valid: {ALL_DEPTS}")
