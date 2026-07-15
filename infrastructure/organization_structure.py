"""Tenant-scoped organization structure, teams, and reporting-line store."""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infrastructure.people_ops_store import DEPARTMENTS


class OrganizationStructureError(ValueError):
    pass


class OrganizationStructureStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or os.getenv("RAPID_ORGANIZATION_STRUCTURE_DB_PATH", "data/db/organization_structure.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS organization_units (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    parent_id TEXT,
                    unit_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    department_key TEXT,
                    owner_user_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(tenant_id, parent_id, name)
                );
                CREATE INDEX IF NOT EXISTS idx_org_units_scope ON organization_units(tenant_id, parent_id);
                CREATE TABLE IF NOT EXISTS organization_memberships (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    manager_user_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(tenant_id, unit_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_org_members_scope ON organization_memberships(tenant_id, unit_id);
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def ensure_default_structure(self, tenant_id: str) -> list[dict]:
        conn = self._connect()
        try:
            root = conn.execute("SELECT * FROM organization_units WHERE tenant_id=? AND unit_type='organization'", (tenant_id,)).fetchone()
            if not root:
                root_id = f"unit_{uuid.uuid4().hex[:12]}"
                conn.execute("INSERT INTO organization_units (id, tenant_id, parent_id, unit_type, name, owner_user_id, created_at) VALUES (?,?,?,?,?,?,?)", (root_id, tenant_id, None, "organization", "Organization", "", self._now()))
            else:
                root_id = root["id"]
            for key, definition in DEPARTMENTS.items():
                existing = conn.execute("SELECT id FROM organization_units WHERE tenant_id=? AND department_key=?", (tenant_id, key)).fetchone()
                if not existing:
                    conn.execute("INSERT INTO organization_units (id, tenant_id, parent_id, unit_type, name, department_key, owner_user_id, created_at) VALUES (?,?,?,?,?,?,?,?)", (f"unit_{uuid.uuid4().hex[:12]}", tenant_id, root_id, "department", definition["name"], key, "", self._now()))
            conn.commit()
            return self._list_with_conn(conn, tenant_id)
        finally:
            conn.close()

    def _list_with_conn(self, conn: sqlite3.Connection, tenant_id: str) -> list[dict]:
        rows = conn.execute("SELECT * FROM organization_units WHERE tenant_id=? ORDER BY unit_type, name", (tenant_id,)).fetchall()
        result = []
        for row in rows:
            unit = dict(row)
            unit["members"] = [dict(member) for member in conn.execute("SELECT user_id, title, manager_user_id FROM organization_memberships WHERE tenant_id=? AND unit_id=? ORDER BY user_id", (tenant_id, row["id"])).fetchall()]
            result.append(unit)
        return result

    def list_units(self, tenant_id: str) -> list[dict]:
        self.ensure_default_structure(tenant_id)
        conn = self._connect()
        try:
            return self._list_with_conn(conn, tenant_id)
        finally:
            conn.close()

    def create_unit(self, tenant_id: str, parent_id: str, name: str, unit_type: str, owner_user_id: str = "") -> dict:
        if unit_type not in {"division", "team"}:
            raise OrganizationStructureError("Only division and team units can be added")
        if not name.strip() or len(name) > 160:
            raise OrganizationStructureError("A unit name between 1 and 160 characters is required")
        conn = self._connect()
        try:
            parent = conn.execute("SELECT id FROM organization_units WHERE id=? AND tenant_id=?", (parent_id, tenant_id)).fetchone()
            if not parent:
                raise OrganizationStructureError("Parent organization unit not found")
            unit_id = f"unit_{uuid.uuid4().hex[:12]}"
            conn.execute("INSERT INTO organization_units (id, tenant_id, parent_id, unit_type, name, owner_user_id, created_at) VALUES (?,?,?,?,?,?,?)", (unit_id, tenant_id, parent_id, unit_type, name.strip(), owner_user_id, self._now()))
            conn.commit()
            return dict(conn.execute("SELECT * FROM organization_units WHERE id=?", (unit_id,)).fetchone())
        except sqlite3.IntegrityError as error:
            raise OrganizationStructureError("A unit with this name already exists under the selected parent") from error
        finally:
            conn.close()

    def assign_member(self, tenant_id: str, unit_id: str, user_id: str, title: str = "", manager_user_id: str = "") -> dict:
        conn = self._connect()
        try:
            if not conn.execute("SELECT id FROM organization_units WHERE id=? AND tenant_id=?", (unit_id, tenant_id)).fetchone():
                raise OrganizationStructureError("Organization unit not found")
            membership_id = f"mem_{uuid.uuid4().hex[:12]}"
            conn.execute("INSERT OR REPLACE INTO organization_memberships (id, tenant_id, unit_id, user_id, title, manager_user_id, created_at) VALUES (?,?,?,?,?,?,?)", (membership_id, tenant_id, unit_id, user_id, title, manager_user_id, self._now()))
            conn.commit()
            return dict(conn.execute("SELECT * FROM organization_memberships WHERE id=?", (membership_id,)).fetchone())
        finally:
            conn.close()


def get_organization_structure_store() -> OrganizationStructureStore:
    return OrganizationStructureStore()
