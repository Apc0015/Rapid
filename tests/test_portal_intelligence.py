from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.portal_intelligence import PortalIntelligenceService
from routers.deps import get_current_user
from routers.intelligence import router


def _client(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_portal_intelligence_rejects_department_outside_user_scope():
    response = _client({"sub": "user", "role": "employee", "tenant_id": "acme", "depts": ["sales"]}).post(
        "/intelligence/ask", json={"question": "Show payroll risk", "department": "hr", "workspace_view": "people"}
    )

    assert response.status_code == 403


def test_portal_intelligence_returns_scoped_fallback_when_agent_runtime_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db"))
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization.db"))

    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("No configured provider")

    monkeypatch.setattr(PortalIntelligenceService, "_run_original_engine", unavailable)
    response = _client({"sub": "ceo", "role": "ceo", "tenant_id": "acme", "depts": []}).post(
        "/intelligence/ask", json={"question": "What is the Atlas renewal risk?", "department": "customer_success", "workspace_view": "crm"}
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "scoped_evidence_fallback"
    assert response.json()["action"] == "scoped_evidence_fallback"


def test_portal_intelligence_passes_scoped_context_to_original_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db"))
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization.db"))
    captured: dict[str, str] = {}

    class Result:
        query_id = "query-1"
        answer = "Atlas needs an executive recovery plan."
        confidence = 0.84
        warning = None
        dept_tags = ["customer_success"]
        action_taken = "returned"
        provider_used = "ollama"

    async def execute(question, *_args, **_kwargs):
        captured["question"] = question
        return Result()

    monkeypatch.setattr(PortalIntelligenceService, "_run_original_engine", staticmethod(execute))
    response = _client({"sub": "ceo", "role": "ceo", "tenant_id": "acme", "depts": []}).post(
        "/intelligence/ask", json={"question": "What is the Atlas renewal risk?", "department": "customer_success", "workspace_view": "crm"}
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "agent_engine"
    assert "Portal context" in captured["question"]
    assert "customer success" in captured["question"].lower()


def test_portal_intelligence_falls_back_when_legacy_agent_returns_a_non_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db"))
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization.db"))

    class Result:
        query_id = "query-1"
        answer = "Unable to generate a valid query. No relevant documents were found in the SALES knowledge base."
        confidence = 0.2
        warning = None
        dept_tags = ["sales"]
        action_taken = "returned"
        provider_used = "ollama"

    async def execute(*_args, **_kwargs):
        return Result()

    monkeypatch.setattr(PortalIntelligenceService, "_run_original_engine", staticmethod(execute))
    response = _client({"sub": "ceo", "role": "ceo", "tenant_id": "acme", "depts": []}).post(
        "/intelligence/ask", json={"question": "What is the Atlas renewal risk?", "workspace_view": "crm"}
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "scoped_evidence_fallback"
    assert "atlas" in response.json()["answer"].lower()
