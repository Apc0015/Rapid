from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.people_ops_store import DEPARTMENTS, PeopleOpsStore
from routers.deps import get_current_user
from routers.organization import router


def test_hr_and_marketing_have_no_duplicate_playbooks_here(tmp_path):
    """
    hr and marketing playbooks live entirely in orgos now (real per-step
    logic + independent verification) — this store deliberately has none for
    them, so there is exactly one place to create an hr or marketing run, not
    two competing ones. See the note atop PLAYBOOKS. Every department is
    still real and listed in DEPARTMENTS; the other 8 either have no orgos
    coverage yet (legal, sales, ops, procurement, rd, customer_success) or
    have playbooks here for scenarios orgos doesn't cover (it's access
    requests, finance's monthly close) alongside their orgos playbooks.
    """
    store = PeopleOpsStore(str(tmp_path / "organization.db"))
    playbooks = store.list_playbooks()

    orgos_departments = {"hr", "marketing"}
    people_ops_departments = {playbook["department"] for playbook in playbooks}

    assert len(DEPARTMENTS) == 10
    assert orgos_departments | people_ops_departments == set(DEPARTMENTS)
    assert not (orgos_departments & people_ops_departments)
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
        "sub": "legal_lead", "role": "dept_head", "tenant_id": "acme", "depts": ["legal"],
    }
    client = TestClient(app)

    assert client.get("/organization/departments").json()["departments"][0]["key"] == "legal"
    assert client.post("/organization/runs", json={"playbook_key": "financial-close", "subject_name": "July close"}).status_code == 403
    assert client.post("/organization/runs", json={"playbook_key": "contract-review", "subject_name": "Acme-Northwind MSA"}).status_code == 201
