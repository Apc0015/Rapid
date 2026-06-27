"""
infrastructure/people_directory.py — People Directory

Stores person records per tenant in a shared SQLite table and automatically
wires each person into the knowledge graph as a PERSON node.

Schema
──────
  people (person_id PK, tenant_id, name, email, role, dept_id,
          division, reports_to, location, bio, status, created_at, updated_at)

Graph integration
─────────────────
  Every person → GraphNode(node_type=PERSON)
  Org relationships:
    reports_to   → ASSIGNED_TO edge (person → manager)
    dept member  → MEMBER_OF  edge (person → dept node)

API surface (used by routers/people.py)
────────────────────────────────────────
  PeopleDirectory.create(person)   → Person
  PeopleDirectory.get(person_id)   → Optional[Person]
  PeopleDirectory.list(tenant_id, dept_id?, role?, status?) → list[Person]
  PeopleDirectory.update(person_id, **fields) → Person
  PeopleDirectory.deactivate(person_id) → Person
  PeopleDirectory.search(tenant_id, query) → list[Person]
  PeopleDirectory.get_graph(person_id, depth) → dict
  PeopleDirectory.get_collaborators(person_id) → list[Person]
  PeopleDirectory.org_chart(tenant_id) → dict
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

import config

logger = logging.getLogger("rapid.people_directory")


# ── Schema DDL ────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS people (
    person_id   TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    name        TEXT NOT NULL,
    email       TEXT,
    role        TEXT NOT NULL DEFAULT 'employee',
    dept_id     TEXT,
    division    TEXT,
    reports_to  TEXT,
    location    TEXT,
    bio         TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (reports_to) REFERENCES people(person_id)
);
CREATE INDEX IF NOT EXISTS idx_people_tenant  ON people(tenant_id);
CREATE INDEX IF NOT EXISTS idx_people_dept    ON people(tenant_id, dept_id);
CREATE INDEX IF NOT EXISTS idx_people_role    ON people(tenant_id, role);
CREATE INDEX IF NOT EXISTS idx_people_mgr     ON people(reports_to);
CREATE INDEX IF NOT EXISTS idx_people_email   ON people(email);
"""


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Person:
    person_id:  str
    tenant_id:  str
    name:       str
    email:      str              = ""
    role:       str              = "employee"
    dept_id:    Optional[str]    = None
    division:   Optional[str]    = None
    reports_to: Optional[str]    = None
    location:   Optional[str]    = None
    bio:        Optional[str]    = None
    status:     str              = "active"
    created_at: str              = ""
    updated_at: str              = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Person":
        d = dict(row)
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})  # type: ignore[attr-defined]


# ── PeopleDirectory ───────────────────────────────────────────────────────────

class PeopleDirectory:
    """
    Tenant-scoped people directory backed by the shared platform DB.
    Thread-safe (each operation opens/closes its own connection).
    """

    def __init__(self, db_path: str = None):
        self._db_path = db_path or config.DB_PATH
        self._ensure_schema()

    # ── internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _connect_ro(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            f"file:{self._db_path}?mode=ro", uri=True, timeout=10
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(
        self,
        tenant_id:  str,
        name:       str,
        email:      str        = "",
        role:       str        = "employee",
        dept_id:    str | None = None,
        division:   str | None = None,
        reports_to: str | None = None,
        location:   str | None = None,
        bio:        str | None = None,
        person_id:  str | None = None,
    ) -> Person:
        now = self._now()
        pid = person_id or str(uuid.uuid4())
        person = Person(
            person_id=pid, tenant_id=tenant_id, name=name,
            email=email, role=role, dept_id=dept_id,
            division=division, reports_to=reports_to,
            location=location, bio=bio,
            status="active", created_at=now, updated_at=now,
        )
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO people
                    (person_id, tenant_id, name, email, role, dept_id,
                     division, reports_to, location, bio, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (pid, tenant_id, name, email, role, dept_id,
                 division, reports_to, location, bio, "active", now, now),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(f"[People] Created {pid} '{name}' ({role}) tenant={tenant_id[:8]}")
        self._sync_to_graph(person)
        return person

    def get(self, person_id: str) -> Optional[Person]:
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT * FROM people WHERE person_id=?", (person_id,)
            ).fetchone()
            return Person.from_row(row) if row else None
        finally:
            conn.close()

    def list(
        self,
        tenant_id: str,
        dept_id:   str | None = None,
        role:      str | None = None,
        status:    str        = "active",
        limit:     int        = 100,
    ) -> list[Person]:
        conditions = ["tenant_id=?"]
        params: list[Any] = [tenant_id]
        if dept_id:
            conditions.append("dept_id=?")
            params.append(dept_id)
        if role:
            conditions.append("role=?")
            params.append(role)
        if status:
            conditions.append("status=?")
            params.append(status)
        params.append(limit)

        sql = (
            f"SELECT * FROM people WHERE {' AND '.join(conditions)} "
            f"ORDER BY name ASC LIMIT ?"
        )
        conn = self._connect_ro()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [Person.from_row(r) for r in rows]
        finally:
            conn.close()

    def update(self, person_id: str, **fields) -> Optional[Person]:
        allowed = {"name","email","role","dept_id","division","reports_to",
                   "location","bio","status"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get(person_id)
        updates["updated_at"] = self._now()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        params = list(updates.values()) + [person_id]
        conn = self._connect()
        try:
            conn.execute(
                f"UPDATE people SET {set_clause} WHERE person_id=?", params
            )
            conn.commit()
        finally:
            conn.close()
        person = self.get(person_id)
        if person:
            self._sync_to_graph(person)
        return person

    def deactivate(self, person_id: str) -> Optional[Person]:
        return self.update(person_id, status="inactive")

    def search(self, tenant_id: str, query: str, limit: int = 20) -> list[Person]:
        """Full-text search across name, email, role, dept_id, bio."""
        q = f"%{query}%"
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                """
                SELECT * FROM people
                WHERE tenant_id=?
                  AND status='active'
                  AND (name LIKE ? OR email LIKE ? OR role LIKE ?
                       OR dept_id LIKE ? OR bio LIKE ?)
                ORDER BY name ASC LIMIT ?
                """,
                (tenant_id, q, q, q, q, q, limit),
            ).fetchall()
            return [Person.from_row(r) for r in rows]
        finally:
            conn.close()

    # ── Org chart & relationships ──────────────────────────────────────────────

    def get_direct_reports(self, person_id: str) -> list[Person]:
        """All people who report to this person."""
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                "SELECT * FROM people WHERE reports_to=? AND status='active' ORDER BY name",
                (person_id,),
            ).fetchall()
            return [Person.from_row(r) for r in rows]
        finally:
            conn.close()

    def get_manager(self, person_id: str) -> Optional[Person]:
        person = self.get(person_id)
        if person and person.reports_to:
            return self.get(person.reports_to)
        return None

    def get_collaborators(self, person_id: str, limit: int = 20) -> list[Person]:
        """People in the same department (proxy for collaborators)."""
        person = self.get(person_id)
        if not person or not person.dept_id:
            return []
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                """
                SELECT * FROM people
                WHERE tenant_id=? AND dept_id=? AND person_id != ? AND status='active'
                ORDER BY name LIMIT ?
                """,
                (person.tenant_id, person.dept_id, person_id, limit),
            ).fetchall()
            return [Person.from_row(r) for r in rows]
        finally:
            conn.close()

    def org_chart(self, tenant_id: str) -> dict:
        """
        Build a hierarchical org chart dict.
        Returns {root_people: [...], by_dept: {dept_id: [...]}, total: N}
        """
        all_people = self.list(tenant_id, status="active", limit=500)
        by_dept: dict[str, list[dict]] = {}
        roots: list[dict] = []  # people with no manager
        by_id = {p.person_id: p for p in all_people}

        for person in all_people:
            dept = person.dept_id or "unassigned"
            by_dept.setdefault(dept, []).append(person.to_dict())
            if not person.reports_to or person.reports_to not in by_id:
                roots.append(person.to_dict())

        return {
            "tenant_id":    tenant_id,
            "total":        len(all_people),
            "root_leaders": roots,
            "by_dept":      by_dept,
            "dept_count":   len(by_dept),
        }

    def get_graph(self, person_id: str, depth: int = 2) -> dict:
        """
        Return the person + their immediate relationships as a graph dict.
        Does not require GraphStore — built from people table.
        """
        person = self.get(person_id)
        if not person:
            return {"error": f"Person '{person_id}' not found"}

        manager      = self.get_manager(person_id)
        direct_reports = self.get_direct_reports(person_id)
        collaborators  = self.get_collaborators(person_id)

        return {
            "person":         person.to_dict(),
            "manager":        manager.to_dict() if manager else None,
            "direct_reports": [p.to_dict() for p in direct_reports],
            "collaborators":  [p.to_dict() for p in collaborators],
            "edges": (
                ([{"type": "reports_to", "target": manager.person_id}] if manager else [])
                + [{"type": "manages", "target": r.person_id} for r in direct_reports]
                + [{"type": "collaborates_with", "target": c.person_id} for c in collaborators]
            ),
        }

    def dept_headcount(self, tenant_id: str) -> dict[str, int]:
        """Return {dept_id: headcount} for the tenant."""
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                """
                SELECT COALESCE(dept_id, 'unassigned') dept, COUNT(*) cnt
                FROM people
                WHERE tenant_id=? AND status='active'
                GROUP BY dept
                ORDER BY cnt DESC
                """,
                (tenant_id,),
            ).fetchall()
            return {r["dept"]: r["cnt"] for r in rows}
        finally:
            conn.close()

    # ── Graph sync ────────────────────────────────────────────────────────────

    def _sync_to_graph(self, person: Person) -> None:
        """
        Upsert this person as a PERSON node in the knowledge graph.
        Silently skips if no project DB is available (graph is per-project).
        """
        try:
            from infrastructure.graph_store import get_graph_store
            from infrastructure.graph_schema import GraphNode, NodeType, EdgeType, GraphEdge

            # Find the person's project DB — use the first project in the tenant
            conn = sqlite3.connect(config.DB_PATH, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT project_id, db_path FROM project_registry "
                "WHERE tenant_id=? AND status='active' LIMIT 5",
                (person.tenant_id,),
            ).fetchall()
            conn.close()

            for row in rows:
                db_path = row["db_path"]
                project_id = row["project_id"]
                if not db_path or not os.path.exists(db_path):
                    continue
                try:
                    store = get_graph_store(db_path, project_id, person.tenant_id)
                    node = GraphNode(
                        node_id     = f"person:{person.person_id}",
                        node_type   = NodeType.PERSON,
                        source_table= "people",
                        source_id   = person.person_id,
                        project_id  = project_id,
                        tenant_id   = person.tenant_id,
                        label       = person.name,
                        properties  = {
                            "role":     person.role,
                            "dept_id":  person.dept_id or "",
                            "email":    person.email,
                            "status":   person.status,
                        },
                    )
                    store.add_node(node)
                    logger.debug(f"[People] Graph node synced: {person.person_id}")
                except Exception as e:
                    logger.debug(f"[People] Graph sync skipped for project {project_id}: {e}")
        except Exception as e:
            logger.debug(f"[People] Graph sync unavailable: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────

_directory: Optional[PeopleDirectory] = None


def get_people_directory() -> PeopleDirectory:
    global _directory
    if _directory is None:
        _directory = PeopleDirectory()
    return _directory
