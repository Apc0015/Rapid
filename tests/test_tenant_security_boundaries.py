import sqlite3

import pytest
from fastapi import HTTPException

import config
from infrastructure.project_provisioner import PLATFORM_TABLES_SQL
from routers import actions
from routers.llm import _require_tenant_scope


def _seed_project(db_path, project_id: str, tenant_id: str, member_id: str | None = None) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(PLATFORM_TABLES_SQL)
        conn.execute(
            """INSERT INTO project_registry (project_id, tenant_id, db_path, faiss_index_path)
               VALUES (?, ?, ?, ?)""",
            (project_id, tenant_id, f"/tmp/{project_id}.db", f"/tmp/{project_id}-faiss"),
        )
        if member_id:
            conn.execute(
                """INSERT INTO project_members (project_id, tenant_id, user_id, dept_id)
                   VALUES (?, ?, ?, 'sales')""",
                (project_id, tenant_id, member_id),
            )
        conn.commit()
    finally:
        conn.close()


def test_project_action_helpers_enforce_tenant_and_membership_scope(tmp_path, monkeypatch):
    db_path = tmp_path / "rapid.db"
    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    _seed_project(str(db_path), "project-a", "tenant-a", member_id="member-a")
    _seed_project(str(db_path), "project-b", "tenant-b", member_id="member-b")

    member = {"sub": "member-a", "tenant_id": "tenant-a", "role": "manager"}
    assert [item["project_id"] for item in actions._all_active_projects(member)] == ["project-a"]
    assert actions._get_accessible_project("project-a", member)["tenant_id"] == "tenant-a"

    with pytest.raises(HTTPException, match="Project not found"):
        actions._get_accessible_project("project-b", member)

    with pytest.raises(HTTPException, match="not a member"):
        actions._get_accessible_project("project-a", {"sub": "other", "tenant_id": "tenant-a", "role": "manager"})


def test_tenant_llm_routes_reject_cross_tenant_administration():
    with pytest.raises(HTTPException, match="Tenant not found"):
        _require_tenant_scope("tenant-b", {"sub": "admin-a", "tenant_id": "tenant-a", "role": "admin"})
