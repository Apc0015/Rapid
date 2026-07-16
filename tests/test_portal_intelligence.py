from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from infrastructure.intelligence_gateway import IntelligenceRequest, get_intelligence_gateway
from infrastructure.organization_data_store import OrganizationDataStore
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
    assert response.json()["mode"] == "organization_agent"
    assert "Governed RAPID evidence" in captured["question"]
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


def test_portal_intelligence_does_not_pass_restricted_knowledge_to_an_employee(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db"))
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization.db"))
    store = OrganizationDataStore(str(tmp_path / "organization.db"))
    source = store.register_source("acme", "hr", "People policies", "unstructured", "manual", "restricted", "admin")
    store.add_document("acme", source["id"], "Restricted compensation", "Executive compensation strategy is restricted.")
    captured: dict[str, str] = {}

    class Result:
        query_id = "query-1"
        answer = "A permitted answer."
        confidence = 0.8
        warning = None
        dept_tags = ["hr"]
        action_taken = "returned"
        provider_used = "ollama"

    async def execute(question, *_args, **_kwargs):
        captured["question"] = question
        return Result()

    monkeypatch.setattr(PortalIntelligenceService, "_run_original_engine", staticmethod(execute))
    response = _client({"sub": "employee", "role": "employee", "tenant_id": "acme", "depts": ["hr"]}).post(
        "/intelligence/ask", json={"question": "What is the compensation strategy?", "department": "hr"}
    )

    assert response.status_code == 200
    assert "Restricted compensation" not in captured["question"]


@pytest.mark.asyncio
async def test_gateway_dispatches_project_questions_through_the_shared_contract(monkeypatch):
    gateway = get_intelligence_gateway()
    captured: dict[str, str] = {}

    class ContextManager:
        def load(self, **_kwargs):
            return SimpleNamespace(project_id="project-1", dept_id="sales")

    class Coordinator:
        async def run(self, **kwargs):
            captured["question"] = kwargs["query"]
            return SimpleNamespace(
                answer="Project delivery is on track.", confidence=0.91, sources=["project_milestones"],
                data_gaps=[], dept_agent_used="SalesIntelligenceAgent", duration_ms=12,
            )

    async def no_evidence(*_args, **_kwargs):
        return []

    monkeypatch.setattr("infrastructure.project_context.get_project_context_manager", lambda: ContextManager())
    monkeypatch.setattr("agents.intelligence.project_coordinator_agent.get_project_coordinator", lambda: Coordinator())
    monkeypatch.setattr(gateway, "_collect_organization_evidence", no_evidence)
    monkeypatch.setattr(gateway, "_audit_specialist", lambda *_args: None)

    response = await gateway.ask(
        IntelligenceRequest(question="Is this project on track?", project_id="project-1"),
        {"sub": "seller", "role": "manager", "tenant_id": "acme", "depts": ["sales"]},
        BackgroundTasks(),
    )

    assert captured["question"] == "Is this project on track?"
    assert response.mode == "project_agent"
    assert response.scope == "project:project-1"
    assert response.sources == ["project_milestones"]


@pytest.mark.asyncio
async def test_gateway_returns_evidence_when_organization_analysis_exceeds_latency_budget(monkeypatch):
    gateway = get_intelligence_gateway()
    monkeypatch.setenv("RAPID_ORGANIZATION_AI_TIMEOUT_SECONDS", "0.1")

    async def evidence(*_args, **_kwargs):
        return []

    async def slow_executor(*_args, **_kwargs):
        import asyncio
        await asyncio.sleep(0.2)

    monkeypatch.setattr(gateway, "_collect_organization_evidence", evidence)
    response = await gateway.ask(
        IntelligenceRequest(question="What is the Atlas renewal risk?", department="sales"),
        {"sub": "ceo", "role": "ceo", "tenant_id": "acme", "depts": []},
        BackgroundTasks(),
        legacy_executor=slow_executor,
    )

    assert response.mode == "scoped_evidence_fallback"
    assert "live-query budget" in (response.warning or "")


@pytest.mark.asyncio
async def test_gateway_dispatches_portfolio_questions_through_the_shared_contract(monkeypatch):
    gateway = get_intelligence_gateway()

    class PortfolioAgent:
        async def run(self, **_kwargs):
            return SimpleNamespace(
                answer="The portfolio needs attention in Sales.", confidence=0.78,
                data_gaps=["No current delivery forecast"], projects_used=["project-1"], duration_ms=18,
            )

    contexts = [SimpleNamespace(project_id="project-1", dept_id="sales", project_name="Atlas")]

    async def load_contexts(**_kwargs):
        return contexts, []

    monkeypatch.setattr(
        "agents.intelligence.portfolio_agent.load_portfolio_contexts", load_contexts,
    )
    monkeypatch.setattr("agents.intelligence.portfolio_agent.get_portfolio_agent", lambda: PortfolioAgent())
    monkeypatch.setattr(gateway, "_audit_specialist", lambda *_args: None)

    response = await gateway.ask_portfolio(
        "Which projects need attention?",
        ["project-1"],
        {"sub": "seller", "role": "manager", "tenant_id": "acme", "depts": ["sales"]},
    )

    assert response.mode == "portfolio_agent"
    assert response.scope == "portfolio"
    assert response.sources == ["project-1"]
    assert response.data_gaps == ["No current delivery forecast"]
