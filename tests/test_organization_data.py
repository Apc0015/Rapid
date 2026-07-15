from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import sys
import types
import importlib

from infrastructure.organization_data_store import OrganizationDataStore
from routers.deps import get_current_user
from routers.organization_data import router


def test_document_retrieval_is_tenant_and_department_isolated(tmp_path):
    store = OrganizationDataStore(str(tmp_path / "organization_data.db"))
    finance_source = store.register_source("acme", "finance", "Close policies", "unstructured", "manual", "confidential", "cfo")
    store.add_document("acme", finance_source["id"], "Close policy", "The July close requires a material variance review before approval.")
    other_source = store.register_source("other", "finance", "Other policy", "unstructured", "manual", "confidential", "other-cfo")
    store.add_document("other", other_source["id"], "Other close", "Other tenant finance policy must never be returned.")

    result = store.search("acme", "finance", "material variance review")
    assert result["count"] == 1
    assert result["citations"][0]["source_id"] == finance_source["id"]
    assert store.search("acme", "hr", "material variance review")["count"] == 0


def test_structured_source_accepts_records_but_not_documents(tmp_path):
    store = OrganizationDataStore(str(tmp_path / "organization_data.db"))
    source = store.register_source("acme", "sales", "CRM export", "structured", "csv", "internal", "revenue-lead")
    updated = store.add_structured_records("acme", source["id"], [{"account": "Acme", "stage": "qualified"}])

    assert updated["record_count"] == 1
    assert store.list_records("acme", source["id"])[0]["record"]["stage"] == "qualified"
    try:
        store.add_document("acme", source["id"], "Not allowed", "Documents do not belong here")
    except ValueError as error:
        assert "unstructured" in str(error)
    else:
        raise AssertionError("structured source accepted a document")


def test_data_api_denies_cross_department_source_access(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization_data.db"))
    monkeypatch.setenv("RAPID_JOB_DB_PATH", str(tmp_path / "jobs.db"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "hr_lead", "role": "dept_head", "tenant_id": "acme", "depts": ["hr"]}
    client = TestClient(app)

    forbidden = client.post("/organization/data/sources", json={"department": "finance", "name": "General ledger", "source_type": "structured"})
    allowed = client.post("/organization/data/sources", json={"department": "hr", "name": "People policies", "source_type": "unstructured"})

    assert forbidden.status_code == 403
    assert allowed.status_code == 201
    source_id = allowed.json()["source"]["id"]
    assert client.post(f"/organization/data/sources/{source_id}/documents", json={"name": "Leave policy", "content": "Employees may request paid leave."}).status_code == 201
    assert client.post("/organization/data/search", json={"department": "hr", "query": "paid leave"}).json()["count"] == 1


def test_document_ingestion_redacts_pii_before_chunk_storage(tmp_path):
    store = OrganizationDataStore(str(tmp_path / "organization_data.db"))
    source = store.register_source("acme", "hr", "Candidate files", "unstructured", "manual", "internal", "people-lead")
    document = store.add_document(
        "acme", source["id"], "Candidate note",
        "Contact alex@example.com at 212-555-0199. Government ID 123-45-6789.",
    )
    saved = store.get_document("acme", document["document_id"])
    chunk_text = saved["chunks"][0]["content"]

    assert document["pii_detected"] is True
    assert document["classification"] == "confidential"
    assert document["pii_summary"] == {"email": 1, "ssn": 1, "phone": 1}
    assert "alex@example.com" not in chunk_text
    assert "[EMAIL_REDACTED]" in chunk_text


def test_document_list_enforces_classification_and_exposes_index_status(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization_data.db"))
    app = FastAPI()
    app.include_router(router)
    principal = {"sub": "operator", "role": "admin", "tenant_id": "acme", "depts": ["hr"]}
    app.dependency_overrides[get_current_user] = lambda: principal
    client = TestClient(app)

    source = client.post("/organization/data/sources", json={
        "department": "hr", "name": "Compensation files", "source_type": "unstructured", "classification": "confidential",
    }).json()["source"]
    document = client.post(f"/organization/data/sources/{source['id']}/documents", json={
        "name": "Compensation policy", "content": "Compensation ranges require manager approval.",
    }).json()["document"]
    assert client.get("/organization/data/documents").json()["documents"][0]["index_status"] == "pending"

    principal.update({"sub": "employee", "role": "employee", "depts": ["hr"]})
    assert client.get("/organization/data/documents").json()["documents"] == []
    assert client.get(f"/organization/data/documents/{document['document_id']}").status_code == 403

    principal.update({"sub": "manager", "role": "manager"})
    visible = client.get("/organization/data/documents").json()["documents"]
    assert visible[0]["classification"] == "confidential"


def test_legacy_document_ingestion_checks_department_membership():
    from fastapi import HTTPException
    from routers.documents import _require_department_access

    _require_department_access({"role": "manager", "depts": ["hr"]}, "hr")
    with pytest.raises(HTTPException) as error:
        _require_department_access({"role": "manager", "depts": ["hr"]}, "finance")
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_faiss_namespace_and_rebuild_are_tenant_safe(tmp_path):
    # test_tenant_isolation intentionally replaces this optional dependency with
    # a MagicMock during full-suite collection. Run this regression where the
    # real FAISS module is available instead of asserting against that fixture.
    if "tests.test_tenant_isolation" in sys.modules:
        pytest.skip("tenant-isolation collection replaces optional vector dependencies")
    module = importlib.import_module("infrastructure.faiss_store")
    if not isinstance(module, types.ModuleType) or not isinstance(getattr(module, "get_dept_index", None), types.FunctionType):
        pytest.skip("FAISS is mocked by the tenant-isolation fixture")
    get_dept_index = module.get_dept_index

    acme = get_dept_index("hr", dim=3, base_dir=str(tmp_path), tenant_id="acme")
    other = get_dept_index("hr", dim=3, base_dir=str(tmp_path), tenant_id="other")
    await acme.add_batch([
        ("acme-policy", "Acme parental leave policy", "policy.txt", [1.0, 0.0, 0.0]),
        ("acme-benefits", "Acme health benefits", "benefits.txt", [0.0, 1.0, 0.0]),
    ])
    await other.add("other-policy", "Other tenant payroll policy", "other.txt", [1.0, 0.0, 0.0])

    assert [chunk.chunk_id for chunk, _ in await other.vector_search([1.0, 0.0, 0.0])] == ["other-policy"]
    assert await acme.delete_source("policy.txt") == 1
    remaining = [chunk.chunk_id for chunk, _ in await acme.vector_search([0.0, 1.0, 0.0])]
    assert remaining == ["acme-benefits"]
