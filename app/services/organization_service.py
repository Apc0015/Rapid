import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USER_DB_PATH = os.path.join(DB_DIR, "users.db")


class OrganizationService:
    """Organization CRUD service."""

    def __init__(self):
        self._init_db()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(USER_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(USER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                org_id TEXT PRIMARY KEY,
                org_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                settings TEXT,
                active INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

    def create_org(self, org_name: str, org_id: Optional[str] = None, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not org_name:
            raise HTTPException(status_code=400, detail="Organization name is required")
        org_id = org_id or f"org_{datetime.now(timezone.utc).timestamp():.0f}"
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        try:
            existing = conn.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Organization already exists")
            conn.execute(
                "INSERT INTO organizations (org_id, org_name, created_at, settings, active) VALUES (?, ?, ?, ?, 1)",
                (org_id, org_name, now, json.dumps(settings) if settings else None),
            )
            conn.commit()
            return {"org_id": org_id, "org_name": org_name, "created_at": now}
        finally:
            conn.close()

    def get_org(self, org_id: str) -> Dict[str, Any]:
        conn = self._get_db()
        try:
            row = conn.execute("SELECT * FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Organization not found")
            return {
                "org_id": row["org_id"],
                "org_name": row["org_name"],
                "created_at": row["created_at"],
                "settings": json.loads(row["settings"]) if row["settings"] else {},
                "active": bool(row["active"]),
            }
        finally:
            conn.close()

    def update_org(
        self,
        org_id: str,
        org_name: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        active: Optional[bool] = None,
    ) -> Dict[str, Any]:
        fields = []
        values = []
        if org_name is not None:
            fields.append("org_name = ?")
            values.append(org_name)
        if settings is not None:
            fields.append("settings = ?")
            values.append(json.dumps(settings))
        if active is not None:
            fields.append("active = ?")
            values.append(1 if active else 0)
        if not fields:
            raise HTTPException(status_code=400, detail="No updates provided")

        values.append(org_id)
        conn = self._get_db()
        try:
            cur = conn.execute(
                f"UPDATE organizations SET {', '.join(fields)} WHERE org_id = ?",
                tuple(values),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Organization not found")
            conn.commit()
            return {"org_id": org_id, "message": "Organization updated"}
        finally:
            conn.close()
