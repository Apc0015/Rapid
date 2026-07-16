from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from infrastructure.demo_workspace import DemoWorkspaceStore
from infrastructure.tenant_admin_store import TenantAdminError, TenantAdminStore
from infrastructure.tenant_policy import TenantPolicy, TenantPolicyError
from infrastructure.integration_hub import IntegrationHub, IntegrationHubError
from routers.onboarding import router


def test_regulated_profile_blocks_cloud_provider_and_scopes_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(TenantAdminStore, "_sync_llm_runtime", staticmethod(lambda *args: None))
    store = TenantAdminStore(str(tmp_path / "tenant-admin.db"))

    profile = store.apply_operating_profile(
        "health-org", profile_key="regulated", deployment_mode="private",
    )

    assert profile["deployment_policy"]["cloud_egress"] == "blocked"
    assert profile["deployment_policy"]["allowed_providers"] == ["ollama"]
    assert "sales" not in profile["departments"]
    assert next(item for item in store.feature_manifest("health-org") if item["key"] == "crm")["enabled"] is False
    try:
        store.update_model("health-org", "openrouter", True, "openai/gpt-4.1-mini", "https://openrouter.ai/api/v1", "vault://abc")
    except TenantAdminError as error:
        assert "blocked" in str(error)
    else:
        raise AssertionError("Expected private policy to block OpenRouter")


def test_provisioned_workspace_uses_customer_name_and_department_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_ORGANIZATION_DATA_DB_PATH", str(tmp_path / "organization-data.db"))
    store = DemoWorkspaceStore(str(tmp_path / "workspace.db"))
    store.provision_workspace(
        tenant_id="studio", company_name="Acme Studio", industry="Creative services",
        department_keys=["sales", "marketing", "ops"],
    )

    overview = store.overview("studio", {"sales", "marketing", "ops"})

    assert overview["organization"]["name"] == "Acme Studio"
    assert overview["metrics"]["departments"] == 3
    assert {item["key"] for item in overview["departments"]} == {"sales", "marketing", "ops"}
    assert all(item["department"] in {"sales", "marketing", "ops"} for item in store.list_entities("studio", departments={"sales", "marketing", "ops"}))


def test_onboarding_catalog_and_start_response(monkeypatch):
    import routers.onboarding as onboarding

    monkeypatch.setattr(onboarding, "provision_organization", lambda **_: {
        "tenant_id": "org-acme-123",
        "owner": {"login_key": "rapid_casey", "name": "Casey", "permitted_departments": ["sales", "ops"]},
        "operating_profile": {"profile_key": "startup"},
    })
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    catalog = client.get("/onboarding/catalog")
    response = client.post("/onboarding/organizations", json={
        "company_name": "Acme", "owner_name": "Casey", "owner_email": "casey@acme.test",
        "password": "strong-pass", "profile_key": "startup", "deployment_mode": "cloud",
    })

    assert catalog.status_code == 200
    assert any(item["key"] == "regulated" for item in catalog.json()["profiles"])
    assert response.status_code == 201
    assert response.json()["tenant_id"] == "org-acme-123"
    assert response.json()["role"] == "ceo"


def test_private_policy_denies_cloud_runtime_and_legacy_connectors():
    policy = TenantPolicy("health-org", "private", frozenset({"ollama"}), "blocked")
    policy.require_provider("ollama")
    for operation in (lambda: policy.require_provider("openrouter"), lambda: policy.require_legacy_connector("Google Drive")):
        try:
            operation()
        except TenantPolicyError:
            pass
        else:
            raise AssertionError("Expected private policy to deny cloud egress")


def test_private_policy_blocks_live_integration_but_allows_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_TENANT_ADMIN_DB_PATH", str(tmp_path / "tenant-admin.db"))
    monkeypatch.setattr(TenantAdminStore, "_sync_llm_runtime", staticmethod(lambda *args: None))
    admin = TenantAdminStore(str(tmp_path / "tenant-admin.db"))
    admin.apply_operating_profile("health-org", profile_key="regulated", deployment_mode="private")
    hub = IntegrationHub(str(tmp_path / "integrations.db"))

    sandbox = hub.register_connection("health-org", "it", "github", "Engineering sandbox", "sandbox", "", {}, "ceo")
    assert sandbox["status"] == "sandbox_ready"
    with pytest.raises(IntegrationHubError, match="cloud egress is blocked"):
        hub.register_connection("health-org", "it", "github", "Engineering production", "oauth", "vault://github/client", {
            "client_id": "client", "client_secret_ref": "vault://github/client",
        }, "ceo")
