from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.beta_access_store import BetaAccessStore
from routers import beta
from routers.deps import get_current_user
from routers.onboarding import router as onboarding_router
from routers.auth import router as auth_router


def test_private_beta_application_requires_reviewer_approval_before_activation(monkeypatch, tmp_path):
    store = BetaAccessStore(str(tmp_path / "beta.db"))
    monkeypatch.setattr(beta, "get_beta_access_store", lambda: store)
    monkeypatch.setenv("RAPID_BETA_REVIEWER_IDS", "beta-admin")
    monkeypatch.setenv("RAPID_PORTAL_URL", "https://beta.rapid.test")
    provisioned = []
    passwords = []
    monkeypatch.setattr(beta, "provision_organization", lambda **kwargs: provisioned.append(kwargs) or {
        "tenant_id": "org-acme-123", "owner": {"login_key": "rapid_casey"},
    })
    monkeypatch.setattr(beta, "set_provisioned_password", lambda login_key, password: passwords.append((login_key, password)))
    monkeypatch.setattr(beta, "load_users", lambda: {
        "rapid_casey": {"name": "Casey", "permitted_departments": ["sales", "ops"]},
    })
    app = FastAPI()
    app.include_router(beta.router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "beta-admin", "role": "admin"}
    client = TestClient(app)

    application = client.post("/beta/applications", json={
        "company_name": "Acme", "owner_name": "Casey", "owner_email": "casey@acme.test",
        "industry": "Software", "website": "https://acme.test", "use_case": "Weekly delivery review",
    })

    assert application.status_code == 202
    assert provisioned == []
    application_id = application.json()["application_id"]
    reviewed = client.post(f"/beta/applications/{application_id}/approve", json={"notes": "Good fit"})
    assert reviewed.status_code == 200
    assert provisioned[0]["profile_key"] == "startup"
    assert reviewed.json()["activation_url"].startswith("https://beta.rapid.test/activate?token=")
    token = reviewed.json()["activation_url"].split("token=", 1)[1]

    activated = client.post("/beta/activate", json={"token": token, "password": "a-new-strong-password"})
    assert activated.status_code == 200
    assert activated.json()["tenant_id"] == "org-acme-123"
    assert passwords == [("rapid_casey", "a-new-strong-password")]
    assert client.post("/beta/activate", json={"token": token, "password": "another-password"}).status_code == 400


def test_production_beta_reviewer_requires_explicit_configuration(monkeypatch):
    monkeypatch.setenv("RAPID_ENV", "production")
    monkeypatch.delenv("RAPID_BETA_REVIEWER_IDS", raising=False)

    assert beta._is_reviewer({"sub": "tenant-ceo", "role": "ceo"}) is False


def test_private_beta_production_closes_legacy_public_registration_paths(monkeypatch):
    monkeypatch.setenv("RAPID_ENV", "production")
    monkeypatch.setenv("RAPID_ALLOW_SELF_SERVICE_PROVISIONING", "false")
    monkeypatch.setenv("RAPID_ALLOW_LEGACY_REGISTRATION", "false")
    app = FastAPI()
    app.include_router(onboarding_router)
    app.include_router(auth_router)
    client = TestClient(app)

    organization = client.post("/onboarding/organizations", json={
        "company_name": "Acme", "owner_name": "Casey", "owner_email": "casey@acme.test",
        "password": "a-new-strong-password", "profile_key": "startup", "deployment_mode": "cloud",
    })
    legacy = client.post("/auth/register", json={
        "employee_name": "Casey", "org_email": "casey@acme.test", "password": "a-new-strong-password",
        "employee_id": "1", "requested_depts": ["sales"], "justification": "Beta test",
    })

    assert organization.status_code == 404
    assert legacy.status_code == 404
