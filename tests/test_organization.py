from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.people_ops_store import DEPARTMENTS, PeopleOpsStore
from routers.deps import get_current_user
from routers.organization import router


def test_all_ten_departments_have_a_governed_playbook(tmp_path):
    store = PeopleOpsStore(str(tmp_path / "organization.db"))
    playbooks = store.list_playbooks()

    assert len(DEPARTMENTS) == 10
    assert {playbook["department"] for playbook in playbooks} == set(DEPARTMENTS)
    assert all(playbook["step_count"] >= 4 for playbook in playbooks)


def test_finance_run_stops_at_consequential_close_approval(tmp_path):
    store = PeopleOpsStore(str(tmp_path / "organization.db"))
    run = store.create_run("acme", "cfo", "financial-close", "July 2026 close")

    escalated = store.advance_to_gate("acme", run["id"], "cfo")
    assert escalated["playbook"]["department"] == "finance"
    assert escalated["status"] == "escalated"
    assert escalated["progress"] == {"complete": 3, "total": 4}


def test_verified_run_can_handoff_to_another_department(tmp_path):
    store = PeopleOpsStore(str(tmp_path / "organization.db"))
    source = store.create_run("acme", "revenue_lead", "lead-qualification", "Northstar")
    source = store.advance_to_gate("acme", source["id"], "revenue_lead")
    source = store.verify_run("acme", source["id"])

    target = store.handoff_run(
        "acme", source["id"], "revenue_lead", "account-health-review", "Northstar", details={"owner": "cs-team"}
    )

    assert target["playbook"]["department"] == "customer_success"
    assert target["details"]["handoff"]["source_run_id"] == source["id"]
    assert any(event["event_type"] == "run.handed_off" for event in store.get_run("acme", source["id"])["events"])


def test_department_access_is_enforced_by_organization_api(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_PEOPLE_OPS_DB_PATH", str(tmp_path / "organization.db"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "people_lead", "role": "dept_head", "tenant_id": "acme", "depts": ["hr"],
    }
    client = TestClient(app)

    assert client.get("/organization/departments").json()["departments"][0]["key"] == "hr"
    assert client.post("/organization/runs", json={"playbook_key": "financial-close", "subject_name": "July close"}).status_code == 403
    assert client.post("/organization/runs", json={"playbook_key": "onboarding", "subject_name": "Priya Shah"}).status_code == 201
