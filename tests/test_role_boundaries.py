from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

import config
from agents.system.audit_logger import AuditLogger
from infrastructure.custom_agent_store import create_custom_agent, get_custom_agent, list_custom_agents
from infrastructure.demo_workspace import get_demo_workspace_store
from routers.deps import require_admin, user_capabilities
from routers.deps import get_current_user
from routers.workspace import router as workspace_router


def _workspace_client(user: dict, monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db"))
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization_data.db"))

    class TenantProfile:
        def operating_profile(self, tenant_id):
            return {"departments": ["finance", "hr", "legal", "sales", "marketing", "ops", "it", "procurement", "rd", "customer_success"]}

    monkeypatch.setattr("routers.workspace.get_tenant_admin_store", lambda: TenantProfile())
    app = FastAPI()
    app.include_router(workspace_router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_capabilities_make_ceo_a_tenant_administrator_and_manager_a_department_operator():
    ceo = {"sub": "ceo", "role": "ceo"}
    manager = {"sub": "manager", "role": "manager"}

    assert require_admin(ceo) == ceo
    assert user_capabilities(ceo)["configure_tenant"] is True
    assert user_capabilities(manager)["manage_department"] is True
    assert user_capabilities(manager)["configure_tenant"] is False
    with pytest.raises(HTTPException):
        require_admin(manager)


def test_manager_cannot_create_company_meetings_or_update_other_department_actions(monkeypatch, tmp_path):
    manager = {"sub": "sales-manager", "role": "manager", "tenant_id": "acme", "depts": ["sales"]}
    client = _workspace_client(manager, monkeypatch, tmp_path)
    store = get_demo_workspace_store()
    other_department_action = next(
        action for action in store.list_actions("acme") if action["department"] != "sales"
    )

    company_meeting = client.post("/workspace/meetings", json={
        "title": "Company review", "starts_at": "2026-08-01T10:00:00+00:00",
        "facilitator": "Sales manager", "agenda": ["Review"],
    })
    cross_department_update = client.post(
        f"/workspace/actions/{other_department_action['id']}/status", json={"status": "done"}
    )

    assert company_meeting.status_code == 403
    assert cross_department_update.status_code == 404


def test_employee_cannot_update_a_department_action(monkeypatch, tmp_path):
    employee = {"sub": "sales-user", "role": "employee", "tenant_id": "acme", "depts": ["sales"]}
    client = _workspace_client(employee, monkeypatch, tmp_path)
    action = next(action for action in get_demo_workspace_store().list_actions("acme") if action["department"] == "sales")

    response = client.post(f"/workspace/actions/{action['id']}/status", json={"status": "done"})

    assert response.status_code == 403


def test_custom_agent_configuration_is_tenant_scoped(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "rapid.db"))
    first = create_custom_agent("tenant-a", "sales", "Renewal Specialist")
    second = create_custom_agent("tenant-b", "sales", "Renewal Specialist")

    assert [record["agent_id"] for record in list_custom_agents("tenant-a")] == [first["agent_id"]]
    assert [record["agent_id"] for record in list_custom_agents("tenant-b")] == [second["agent_id"]]
    assert get_custom_agent(first["agent_id"], "tenant-b") is None


def test_audit_events_and_agent_scores_are_tenant_scoped(tmp_path):
    audit = AuditLogger(str(tmp_path / "audit.db"))
    audit.log_query({"query_id": "a", "user_id": "founder", "tenant_id": "tenant-a", "raw_query": "Revenue"})
    audit.log_query({"query_id": "b", "user_id": "founder", "tenant_id": "tenant-b", "raw_query": "Payroll"})
    audit.write_agent_score("sales_agent", "a", 0.9, {}, tenant_id="tenant-a")
    audit.write_agent_score("sales_agent", "b", 0.2, {}, tenant_id="tenant-b")

    assert [event["query_id"] for event in audit.query_audit_trail(tenant_id="tenant-a")] == ["a"]
    assert audit.get_agent_stats("sales_agent", "tenant-a")["avg_score"] == 0.9
    assert audit.get_agent_stats("sales_agent", "tenant-b")["avg_score"] == 0.2
