from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.people_ops_store import PeopleOpsStore
from routers.deps import get_current_user
from routers.people_ops import router


def test_leave_run_requires_verification_and_records_evidence(tmp_path):
    store = PeopleOpsStore(str(tmp_path / "people_ops.db"))
    run = store.create_run("acme", "founder", "leave", "Priya Shah", details={"dates": "2026-08-13 to 2026-08-14"})

    gated = store.advance_to_gate("acme", run["id"], "founder")
    assert gated["status"] == "verifying"
    assert gated["progress"] == {"complete": 4, "total": 4}
    assert all(step["evidence"] for step in gated["steps"])

    verified = store.verify_run("acme", run["id"])
    assert verified["status"] == "done"
    assert verified["events"][-1]["event_type"] == "run.verified"


def test_consequential_onboarding_step_escalates_then_continues(tmp_path):
    store = PeopleOpsStore(str(tmp_path / "people_ops.db"))
    run = store.create_run("acme", "founder", "onboarding", "Priya Shah")

    escalated = store.advance_to_gate("acme", run["id"], "founder")
    assert escalated["status"] == "escalated"
    assert escalated["escalation"]["status"] == "open"

    resumed = store.resolve_escalation("acme", run["id"], "founder", "approve", "Terms reviewed")
    assert resumed["status"] == "verifying"
    assert resumed["progress"] == {"complete": 5, "total": 5}
    assert store.verify_run("acme", run["id"])["status"] == "done"


def test_tenant_cannot_read_another_tenants_run(tmp_path):
    store = PeopleOpsStore(str(tmp_path / "people_ops.db"))
    run = store.create_run("acme", "founder", "leave", "Priya Shah")

    try:
        store.get_run("other-co", run["id"])
    except ValueError as error:
        assert "not found" in str(error).lower()
    else:
        raise AssertionError("tenant boundary was not enforced")


def test_api_uses_authenticated_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_PEOPLE_OPS_DB_PATH", str(tmp_path / "people_ops.db"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "founder", "role": "ceo", "tenant_id": "acme"}
    client = TestClient(app)

    response = client.post("/people-ops/runs", json={"playbook_key": "leave", "subject_name": "Priya Shah"})
    assert response.status_code == 201
    run_id = response.json()["run"]["id"]
    assert client.post(f"/people-ops/runs/{run_id}/advance").json()["run"]["status"] == "verifying"
    assert client.post(f"/people-ops/runs/{run_id}/verify").json()["run"]["status"] == "done"
