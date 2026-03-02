import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USER_DB_PATH = os.path.join(DB_DIR, "users.db")


class RBACService:
    """Role-based access control and permissions."""

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
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                group_name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                FOREIGN KEY (org_id) REFERENCES organizations(org_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_permissions (
                permission_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                org_id TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                access_level TEXT DEFAULT 'private',
                allowed_users TEXT,
                allowed_groups TEXT,
                allowed_roles TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (org_id) REFERENCES organizations(org_id)
            )
        """)

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self._get_db()
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return None
            return {
                "username": row["username"],
                "role": row["role"],
                "org_id": row["org_id"] or "default",
                "department": row["department"],
                "groups": json.loads(row["groups"]) if row["groups"] else [],
                "active": bool(row["active"]),
            }
        finally:
            conn.close()

    def list_users(self, org_id: str) -> List[Dict[str, Any]]:
        conn = self._get_db()
        try:
            rows = conn.execute(
                "SELECT username, role, org_id, department, groups, active, created_at "
                "FROM users WHERE org_id = ? ORDER BY username",
                (org_id,),
            ).fetchall()
            return [
                {
                    "username": r["username"],
                    "role": r["role"],
                    "org_id": r["org_id"] or "default",
                    "department": r["department"],
                    "groups": json.loads(r["groups"]) if r["groups"] else [],
                    "active": bool(r["active"]),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def update_user(
        self,
        username: str,
        role: Optional[str] = None,
        groups: Optional[List[str]] = None,
        department: Optional[str] = None,
        active: Optional[bool] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if role and role not in ("admin", "manager", "user"):
            raise HTTPException(status_code=400, detail="Invalid role")

        fields = []
        values: List[Any] = []
        if role is not None:
            fields.append("role = ?")
            values.append(role)
        if department is not None:
            fields.append("department = ?")
            values.append(department)
        if groups is not None:
            fields.append("groups = ?")
            values.append(json.dumps(groups))
        if active is not None:
            fields.append("active = ?")
            values.append(1 if active else 0)
        if org_id is not None:
            fields.append("org_id = ?")
            values.append(org_id)

        if not fields:
            raise HTTPException(status_code=400, detail="No updates provided")

        values.append(username)

        conn = self._get_db()
        try:
            cur = conn.execute(
                f"UPDATE users SET {', '.join(fields)} WHERE username = ?",
                tuple(values),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="User not found")
            conn.commit()
            return {"username": username, "message": "User updated"}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def create_group(self, org_id: str, group_name: str, description: Optional[str], created_by: str) -> Dict[str, Any]:
        group_id = f"group_{datetime.now(timezone.utc).timestamp():.0f}"
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        try:
            conn.execute(
                "INSERT INTO groups (group_id, org_id, group_name, description, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (group_id, org_id, group_name, description, now, created_by),
            )
            conn.commit()
            return {
                "group_id": group_id,
                "org_id": org_id,
                "group_name": group_name,
                "description": description,
                "created_at": now,
            }
        finally:
            conn.close()

    def list_groups(self, org_id: str) -> List[Dict[str, Any]]:
        conn = self._get_db()
        try:
            rows = conn.execute(
                "SELECT group_id, org_id, group_name, description, created_at, created_by "
                "FROM groups WHERE org_id = ? ORDER BY group_name",
                (org_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_group(self, group_id: str, group_name: Optional[str], description: Optional[str]) -> Dict[str, Any]:
        fields = []
        values: List[Any] = []
        if group_name is not None:
            fields.append("group_name = ?")
            values.append(group_name)
        if description is not None:
            fields.append("description = ?")
            values.append(description)
        if not fields:
            raise HTTPException(status_code=400, detail="No updates provided")
        values.append(group_id)

        conn = self._get_db()
        try:
            cur = conn.execute(
                f"UPDATE groups SET {', '.join(fields)} WHERE group_id = ?",
                tuple(values),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Group not found")
            conn.commit()
            return {"group_id": group_id, "message": "Group updated"}
        finally:
            conn.close()

    def delete_group(self, group_id: str) -> Dict[str, Any]:
        conn = self._get_db()
        try:
            cur = conn.execute("DELETE FROM groups WHERE group_id = ?", (group_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Group not found")
            conn.commit()
            return {"group_id": group_id, "message": "Group deleted"}
        finally:
            conn.close()

    def add_user_to_group(self, group_id: str, username: str) -> Dict[str, Any]:
        user = self.get_user(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        groups = set(user.get("groups", []))
        groups.add(group_id)
        self.update_user(username, groups=sorted(groups))
        return {"username": username, "group_id": group_id, "message": "User added to group"}

    # ------------------------------------------------------------------
    # Document permissions
    # ------------------------------------------------------------------

    def set_document_permissions(
        self,
        document_id: str,
        org_id: str,
        owner_username: str,
        access_level: str = "private",
        allowed_users: Optional[List[str]] = None,
        allowed_groups: Optional[List[str]] = None,
        allowed_roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if access_level not in ("private", "group", "org", "public"):
            raise HTTPException(status_code=400, detail="Invalid access level")

        conn = self._get_db()
        try:
            row = conn.execute(
                "SELECT permission_id FROM document_permissions WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            now = datetime.now(timezone.utc).isoformat()

            if row:
                conn.execute(
                    "UPDATE document_permissions SET org_id = ?, owner_username = ?, access_level = ?, "
                    "allowed_users = ?, allowed_groups = ?, allowed_roles = ? WHERE document_id = ?",
                    (
                        org_id,
                        owner_username,
                        access_level,
                        json.dumps(allowed_users or []),
                        json.dumps(allowed_groups or []),
                        json.dumps(allowed_roles or []),
                        document_id,
                    ),
                )
            else:
                permission_id = f"perm_{datetime.now(timezone.utc).timestamp():.0f}"
                conn.execute(
                    "INSERT INTO document_permissions "
                    "(permission_id, document_id, org_id, owner_username, access_level, "
                    "allowed_users, allowed_groups, allowed_roles, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        permission_id,
                        document_id,
                        org_id,
                        owner_username,
                        access_level,
                        json.dumps(allowed_users or []),
                        json.dumps(allowed_groups or []),
                        json.dumps(allowed_roles or []),
                        now,
                    ),
                )
            conn.commit()
            return {"document_id": document_id, "message": "Permissions updated"}
        finally:
            conn.close()

    def get_document_permissions(self, document_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_db()
        try:
            row = conn.execute(
                "SELECT * FROM document_permissions WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "permission_id": row["permission_id"],
                "document_id": row["document_id"],
                "org_id": row["org_id"],
                "owner_username": row["owner_username"],
                "access_level": row["access_level"],
                "allowed_users": json.loads(row["allowed_users"] or "[]"),
                "allowed_groups": json.loads(row["allowed_groups"] or "[]"),
                "allowed_roles": json.loads(row["allowed_roles"] or "[]"),
                "created_at": row["created_at"],
            }
        finally:
            conn.close()

    def delete_document_permissions(self, document_id: str) -> None:
        conn = self._get_db()
        try:
            conn.execute("DELETE FROM document_permissions WHERE document_id = ?", (document_id,))
            conn.commit()
        finally:
            conn.close()

    def can_access_document(
        self,
        user: Dict[str, Any],
        document_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        perms: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not user:
            return False

        org_id = (metadata or {}).get("org_id") or "default"
        if user.get("org_id") != org_id:
            return False

        if user.get("role") == "admin":
            return True

        perms = perms or self.get_document_permissions(document_id)
        if not perms:
            return True  # Default to org access for legacy docs

        if perms["owner_username"] == user["username"]:
            return True

        if perms["access_level"] in ("public", "org"):
            return True

        if user["username"] in perms["allowed_users"]:
            return True

        if user["role"] in perms["allowed_roles"]:
            return True

        if set(user.get("groups", [])).intersection(set(perms["allowed_groups"])):
            return True

        return False

    def can_manage_document(self, user: Dict[str, Any], document_id: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if not user:
            return False
        if user.get("role") == "admin":
            return True
        perms = self.get_document_permissions(document_id)
        if perms and perms["owner_username"] == user["username"]:
            return True
        owner = (metadata or {}).get("owner")
        return owner == user["username"]

    def filter_results(self, results: List[Dict[str, Any]], user: Dict[str, Any]) -> List[Dict[str, Any]]:
        allowed: List[Dict[str, Any]] = []
        perms_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        for r in results:
            meta = r.get("metadata") or {}
            doc_id = meta.get("doc_id")
            if not doc_id:
                continue
            if doc_id not in perms_cache:
                perms_cache[doc_id] = self.get_document_permissions(doc_id)
            # Pass metadata; can_access_document will query again if perms_cache missing
            if self.can_access_document(user, doc_id, meta, perms_cache[doc_id]):
                allowed.append(r)
        return allowed

    def list_permissions_for_user(self, username: str) -> List[Dict[str, Any]]:
        user = self.get_user(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        conn = self._get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM document_permissions WHERE org_id = ?",
                (user["org_id"],),
            ).fetchall()
            results = []
            for row in rows:
                perms = {
                    "document_id": row["document_id"],
                    "owner_username": row["owner_username"],
                    "access_level": row["access_level"],
                    "allowed_users": json.loads(row["allowed_users"] or "[]"),
                    "allowed_groups": json.loads(row["allowed_groups"] or "[]"),
                    "allowed_roles": json.loads(row["allowed_roles"] or "[]"),
                }
                if self.can_access_document(user, row["document_id"], {"org_id": row["org_id"]}, perms):
                    results.append(perms)
            return results
        finally:
            conn.close()
