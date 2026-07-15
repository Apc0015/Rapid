from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.organization_structure import OrganizationStructureStore
from routers.deps import get_current_user
from routers.organization_structure import router


def test_default_structure_has_ten_departments_and_persists_team_members(tmp_path):
    store = OrganizationStructureStore(str(tmp_path / "structure.db"))
    units = store.list_units("acme")
    departments = [unit for unit in units if unit["unit_type"] == "department"]
    root = next(unit for unit in units if unit["unit_type"] == "organization")

    assert len(departments) == 10
    team = store.create_unit("acme", root["id"], "Revenue Operations", "team", "sales_lead")
    membership = store.assign_member("acme", team["id"], "sam", "Revenue Operations Manager", "ceo")
    assert membership["manager_user_id"] == "ceo"
    assert any(unit["id"] == team["id"] and unit["members"][0]["user_id"] == "sam" for unit in store.list_units("acme"))


def test_structure_api_requires_administrator(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_ORGANIZATION_STRUCTURE_DB_PATH", str(tmp_path / "structure.db"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "employee", "role": "employee", "tenant_id": "acme"}
    client = TestClient(app)

    root = next(unit for unit in client.get("/organization/structure").json()["units"] if unit["unit_type"] == "organization")
    response = client.post("/organization/structure/units", json={"parent_id": root["id"], "name": "Test team", "unit_type": "team"})
    assert response.status_code == 403
