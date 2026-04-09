"""
routers/database.py — External database connection management (admin only).

  POST /db/connect      — Register and test a new DB connection
  GET  /db/connections  — List all registered connections
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import config
from .deps import require_admin

router = APIRouter(prefix="/db", tags=["database"])
logger = logging.getLogger("rapid.database")

# In-process connection registry (lives as long as the server process)
_db_connections: dict = {}


class DBConnectRequest(BaseModel):
    db_type:  str                  # "sqlite" | "postgresql" | "mysql"
    db_path:  Optional[str] = None # SQLite
    host:     Optional[str] = None # PostgreSQL / MySQL
    port:     Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    label:    Optional[str] = "default"


@router.post("/connect")
async def db_connect(req: DBConnectRequest, current_user: dict = Depends(require_admin)):
    """Admin-only. Test and register a database connection."""
    user_id = current_user["sub"]
    conn_id = req.label or f"{req.db_type}_{len(_db_connections) + 1}"

    try:
        if req.db_type == "sqlite":
            if not req.db_path:
                raise ValueError("db_path is required for SQLite")
            import sqlite3
            conn = sqlite3.connect(req.db_path)
            conn.execute("SELECT 1")
            conn.close()
            _db_connections[conn_id] = {
                "type": "sqlite", "path": req.db_path,
                "label": conn_id, "status": "connected",
            }

        elif req.db_type in ("postgresql", "mysql"):
            _db_connections[conn_id] = {
                "type": req.db_type, "host": req.host, "port": req.port,
                "database": req.database, "username": req.username,
                "label": conn_id, "status": "configured",
            }
        else:
            raise ValueError(f"Unsupported db_type: {req.db_type}. Use: sqlite, postgresql, mysql")

        logger.info(f"[db/connect] Admin {user_id} registered connection '{conn_id}' ({req.db_type})")
        return {
            "connection_id": conn_id,
            "status":        _db_connections[conn_id]["status"],
            "message":       f"Connection '{conn_id}' registered successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")


@router.get("/connections")
async def db_connections(current_user: dict = Depends(require_admin)):
    """Admin-only. List all registered database connections."""
    safe = {k: {kk: vv for kk, vv in v.items() if kk != "password"}
            for k, v in _db_connections.items()}
    safe["rapid_default"] = {
        "type": "sqlite", "path": config.DB_PATH,
        "label": "RAPID Default DB", "status": "connected",
    }
    return safe
