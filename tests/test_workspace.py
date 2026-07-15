from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.demo_workspace import DemoWorkspaceStore
from infrastructure.organization_data_store import OrganizationDataStore
from routers.deps import get_current_user
from routers.workspace import router


def test_synthetic_workspace_contains_all_departments_and_meetings(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization_data.db"))
    store = DemoWorkspaceStore(str(tmp_path / "workspace.db"))
    overview = store.overview("demo")

    assert overview["is_synthetic_demo"] is True
    assert len(overview["departments"]) == 10
    assert len(overview["meetings"]) == 4
    assert overview["metrics"]["open_actions"] >= 1
    assert len(OrganizationDataStore().list_sources("demo")) == 10
    assert {item["type"] for item in overview["record_catalog"]} >= {"customer", "employee", "project", "ticket"}


def test_workspace_api_is_tenant_scoped_and_actions_can_advance(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db"))
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization_data.db"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "demo_ceo", "role": "ceo", "tenant_id": "acme"}
    client = TestClient(app)

    overview = client.get("/workspace/overview").json()
    action_id = overview["actions"][0]["id"]
    changed = client.post(f"/workspace/actions/{action_id}/status", json={"status": "done"})

    assert changed.status_code == 200
    assert changed.json()["action"]["status"] == "done"


def test_workspace_api_creates_a_scheduled_meeting(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db"))
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization_data.db"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "demo_ceo", "role": "ceo", "tenant_id": "acme"}
    response = TestClient(app).post("/workspace/meetings", json={
        "title": "Account plan review", "meeting_type": "Operating review", "department": "customer_success",
        "starts_at": "2026-07-20T14:00:00+00:00", "duration_minutes": 45, "facilitator": "Maya Chen",
        "attendees": ["Maya Chen", "Hannah Kim"], "agenda": ["Review renewal risk"],
    })

    assert response.status_code == 201
    assert response.json()["meeting"]["status"] == "scheduled"


def test_meeting_notes_decisions_and_actions_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db")); monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization_data.db"))
    store = DemoWorkspaceStore(str(tmp_path / "workspace.db")); meeting_id = store.list_meetings("acme")[0]["id"]
    saved = store.update_meeting_record("acme", meeting_id, "Reviewed renewal risk.", ["Escalate Atlas Group"])
    action = store.create_meeting_action("acme", meeting_id, "Prepare Atlas recovery plan", "Hannah Kim", "customer_success", "2026-07-21", "high")
    assert saved["decisions"] == ["Escalate Atlas Group"]
    assert action["meeting_id"] == meeting_id


def test_reset_restores_the_synthetic_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization_data.db"))
    store = DemoWorkspaceStore(str(tmp_path / "workspace.db")); store.ensure_workspace("acme")
    meeting_id = store.list_meetings("acme")[0]["id"]
    store.update_meeting_record("acme", meeting_id, "Temporary note", [])
    reset = store.reset_workspace("acme")
    assert reset["organization"]["name"] == "Northstar Labs"
    assert len(reset["meetings"]) == 4
