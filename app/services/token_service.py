import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.services.encryption_service import EncryptionService

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USER_DB_PATH = os.path.join(DB_DIR, "users.db")


class TokenService:
    """Organization token management (encrypted at rest)."""

    def __init__(self):
        self.encryption = EncryptionService()
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
            CREATE TABLE IF NOT EXISTS api_tokens (
                token_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                service_type TEXT NOT NULL,
                token_name TEXT NOT NULL,
                encrypted_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                expires_at TEXT,
                active INTEGER DEFAULT 1,
                FOREIGN KEY (org_id) REFERENCES organizations(org_id)
            )
        """)
        conn.commit()
        conn.close()

    def create_token(
        self,
        org_id: str,
        service_type: str,
        token_name: str,
        token_value: str,
        created_by: str,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not token_value:
            raise HTTPException(status_code=400, detail="Token value is required")
        token_id = f"token_{datetime.now(timezone.utc).timestamp():.0f}"
        now = datetime.now(timezone.utc).isoformat()
        encrypted = self.encryption.encrypt(token_value)
        if encrypted is None:
            raise HTTPException(status_code=500, detail="Failed to encrypt token")

        conn = self._get_db()
        try:
            conn.execute(
                "INSERT INTO api_tokens "
                "(token_id, org_id, service_type, token_name, encrypted_token, created_at, created_by, expires_at, active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (token_id, org_id, service_type, token_name, encrypted, now, created_by, expires_at),
            )
            conn.commit()
            return {
                "token_id": token_id,
                "org_id": org_id,
                "service_type": service_type,
                "token_name": token_name,
                "created_at": now,
                "expires_at": expires_at,
                "active": True,
            }
        finally:
            conn.close()

    def list_tokens(self, org_id: str) -> List[Dict[str, Any]]:
        conn = self._get_db()
        try:
            rows = conn.execute(
                "SELECT token_id, org_id, service_type, token_name, created_at, created_by, "
                "expires_at, active FROM api_tokens WHERE org_id = ? ORDER BY created_at DESC",
                (org_id,),
            ).fetchall()
            return [
                {
                    "token_id": r["token_id"],
                    "org_id": r["org_id"],
                    "service_type": r["service_type"],
                    "token_name": r["token_name"],
                    "created_at": r["created_at"],
                    "created_by": r["created_by"],
                    "expires_at": r["expires_at"],
                    "active": bool(r["active"]),
                }
                for r in rows
            ]
        finally:
            conn.close()

    def update_token(
        self,
        token_id: str,
        token_name: Optional[str] = None,
        token_value: Optional[str] = None,
        expires_at: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> Dict[str, Any]:
        fields = []
        values: List[Any] = []
        if token_name is not None:
            fields.append("token_name = ?")
            values.append(token_name)
        if token_value is not None:
            encrypted = self.encryption.encrypt(token_value)
            if encrypted is None:
                raise HTTPException(status_code=500, detail="Failed to encrypt token")
            fields.append("encrypted_token = ?")
            values.append(encrypted)
        if expires_at is not None:
            fields.append("expires_at = ?")
            values.append(expires_at)
        if active is not None:
            fields.append("active = ?")
            values.append(1 if active else 0)
        if not fields:
            raise HTTPException(status_code=400, detail="No updates provided")

        values.append(token_id)
        conn = self._get_db()
        try:
            cur = conn.execute(
                f"UPDATE api_tokens SET {', '.join(fields)} WHERE token_id = ?",
                tuple(values),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Token not found")
            conn.commit()
            return {"token_id": token_id, "message": "Token updated"}
        finally:
            conn.close()

    def delete_token(self, token_id: str) -> Dict[str, Any]:
        conn = self._get_db()
        try:
            cur = conn.execute("DELETE FROM api_tokens WHERE token_id = ?", (token_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Token not found")
            conn.commit()
            return {"token_id": token_id, "message": "Token deleted"}
        finally:
            conn.close()
