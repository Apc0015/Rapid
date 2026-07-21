"""
tests/test_orgos_tenant_isolation.py — multi-tenant isolation for the orgos work
engine (the SaaS "isolation done right" gate, decision D2).

Two customers run the SAME playbook with the SAME subject. Each must see ONLY its
own runs and records — never the other's — and must not be able to fetch the
other's run even by guessing its id. These are written to FAIL if isolation is
ever bypassed: a shared store would surface one tenant's run/record for the
other, or the same-subject record would overwrite. CI runs every test under
tests/, so this blocks any regression into main.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """A factory that builds an orgos API client acting as a given tenant, all
    backed by one fresh temp store (so a leak between tenants is observable)."""
    import orgos.store as store_mod
    import orgos.engine as engine_mod
    from orgos.store import OrgStore
    from orgos.engine import Engine

    store = OrgStore(str(tmp_path / "orgos_test.db"))
    monkeypatch.setattr(store_mod, "_store", store)
    monkeypatch.setattr(engine_mod, "_engine", Engine(store=store))

    from orgos.api import build_department_router, org_router
    from routers.deps import get_current_user

    def _client(tenant: str, role: str = "admin"):
        app = FastAPI()
        app.include_router(build_department_router("marketing"))
        app.include_router(org_router)
        app.dependency_overrides[get_current_user] = lambda: {
            "sub": f"{tenant}-user", "role": role, "tenant_id": tenant, "depts": ["marketing"],
        }
        return TestClient(app)

    return _client


def _run_ids(board: dict) -> set:
    return {r["run_id"] for col in board["columns"].values() for r in col}


def test_two_tenants_never_see_each_others_runs(make_client):
    a = make_client("tenant-a")
    b = make_client("tenant-b")

    # Both customers run the same playbook, same subject, different numbers.
    ra = a.post("/marketing/runs", json={"playbook": "weekly_digest", "subject": "Week 1",
                                         "inputs": {"spend": 100, "conversions": 5}})
    rb = b.post("/marketing/runs", json={"playbook": "weekly_digest", "subject": "Week 1",
                                         "inputs": {"spend": 999, "conversions": 1}})
    assert ra.status_code == 200 and rb.status_code == 200
    run_a, run_b = ra.json()["run_id"], rb.json()["run_id"]
    assert run_a != run_b

    # Each board shows exactly its own single run — never the other tenant's.
    ids_a = _run_ids(a.get("/marketing/board").json())
    ids_b = _run_ids(b.get("/marketing/board").json())
    assert ids_a == {run_a}
    assert ids_b == {run_b}

    # The leak guard: fetching the other tenant's run by id is a 404, not a peek.
    assert a.get(f"/marketing/runs/{run_b}").status_code == 404
    assert b.get(f"/marketing/runs/{run_a}").status_code == 404


def test_same_subject_records_do_not_collide_across_tenants(make_client):
    a = make_client("tenant-a")
    b = make_client("tenant-b")
    a.post("/marketing/runs", json={"playbook": "weekly_digest", "subject": "Week 1",
                                    "inputs": {"spend": 100, "conversions": 5}})
    b.post("/marketing/runs", json={"playbook": "weekly_digest", "subject": "Week 1",
                                    "inputs": {"spend": 999, "conversions": 1}})

    # Read each tenant's recorded metrics back through its own store view.
    import orgos.store as store_mod
    rec_a = store_mod._store.find_record("marketing", "weekly_metrics", "Week 1", tenant_id="tenant-a")
    rec_b = store_mod._store.find_record("marketing", "weekly_metrics", "Week 1", tenant_id="tenant-b")
    # If records were shared by subject, the second write would overwrite the first.
    assert rec_a["data"]["spend"] == 100
    assert rec_b["data"]["spend"] == 999


def test_org_overview_counts_only_the_callers_tenant(make_client):
    a = make_client("tenant-a")
    b = make_client("tenant-b")
    a.post("/marketing/runs", json={"playbook": "weekly_digest", "subject": "W",
                                    "inputs": {"spend": 1, "conversions": 1}})
    b.post("/marketing/runs", json={"playbook": "weekly_digest", "subject": "W",
                                    "inputs": {"spend": 2, "conversions": 2}})
    overview_a = a.get("/org/overview").json()
    assert overview_a["departments"]["marketing"]["total"] == 1  # tenant-a's run only
