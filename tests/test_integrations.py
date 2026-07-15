from fastapi import FastAPI
from fastapi.testclient import TestClient

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import httpx
import respx
from urllib.parse import parse_qs, urlparse

from infrastructure.integration_hub import IntegrationHub
from routers.deps import get_current_user
from routers.organization_integrations import router
from infrastructure.secret_vault import get_secret_vault


def test_sandbox_event_triggers_idempotent_governed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_PEOPLE_OPS_DB_PATH", str(tmp_path / "runs.db"))
    hub = IntegrationHub(str(tmp_path / "integrations.db"))
    connection = hub.register_connection("acme", "it", "jira", "IT service desk", "sandbox", "", {}, "it_lead")

    first = hub.trigger_event("acme", connection["id"], "ticket-1001", "issue_change", "access-request", "Priya production access", "", {"ticket": "IT-1001"}, "it_lead")
    duplicate = hub.trigger_event("acme", connection["id"], "ticket-1001", "issue_change", "access-request", "Priya production access", "", {"ticket": "IT-1001"}, "it_lead")

    assert first["run"]["status"] == "escalated"
    assert first["run"]["playbook"]["department"] == "it"
    assert duplicate["duplicate"] is True
    assert duplicate["run"]["id"] == first["run"]["id"]


def test_integration_api_enforces_department_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_INTEGRATIONS_DB_PATH", str(tmp_path / "integrations.db"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "finance_lead", "role": "dept_head", "tenant_id": "acme", "depts": ["finance"]}
    client = TestClient(app)

    forbidden = client.post("/organization/integrations/connections", json={"department": "sales", "provider": "hubspot", "label": "Revenue CRM", "auth_mode": "sandbox"})
    allowed = client.post("/organization/integrations/connections", json={"department": "finance", "provider": "quickbooks", "label": "Finance sandbox", "auth_mode": "sandbox"})

    assert forbidden.status_code == 403
    assert allowed.status_code == 201
    connection_id = allowed.json()["connection"]["id"]
    assert client.post(f"/organization/integrations/connections/{connection_id}/test").json()["connection"]["status"] == "sandbox_ready"


def test_due_schedule_dispatches_once_and_records_result(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_PEOPLE_OPS_DB_PATH", str(tmp_path / "runs.db"))
    hub = IntegrationHub(str(tmp_path / "integrations.db"))
    connection = hub.register_connection("acme", "sales", "hubspot", "Sales sandbox", "sandbox", "", {}, "sales_lead")
    schedule = hub.create_schedule(
        "acme", connection["id"], "lead-qualification", "Northstar inbound", "", {"source": "daily sync"}, 60, "sales_lead"
    )

    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    dispatched = hub.dispatch_due_schedules("acme", now=now)
    repeated = hub.dispatch_due_schedules("acme", now=now)
    saved = hub.get_schedule("acme", schedule["id"])

    assert dispatched[0]["status"] == "dispatched"
    assert dispatched[0]["duplicate"] is False
    assert repeated == []
    assert saved["last_status"] == "dispatched"


def test_signed_webhook_is_replay_protected_and_enqueued_once(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_INTEGRATIONS_DB_PATH", str(tmp_path / "integrations.db"))
    monkeypatch.setenv("RAPID_JOB_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("RAPID_SECRETS_DB_PATH", str(tmp_path / "secrets.db"))
    monkeypatch.setenv("RAPID_LOCAL_VAULT_KEY_PATH", str(tmp_path / "vault.key"))
    monkeypatch.setenv("WEBHOOK_SECRET", "test-signing-secret")
    hub = IntegrationHub(str(tmp_path / "integrations.db"))
    connection = hub.register_connection(
        "acme", "it", "jira", "Signed service desk", "sandbox", "",
        {"webhook_secret_ref": "env://WEBHOOK_SECRET", "playbook_key": "access-request"}, "it-lead",
    )
    timestamp = str(datetime.now(timezone.utc).timestamp())
    body = json.dumps({"event_type": "issue_change", "subject_name": "Production access"}).encode()
    signature = "sha256=" + hmac.new(b"test-signing-secret", f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()

    accepted = hub.receive_webhook(connection["id"], body, signature, timestamp, "jira-100")
    duplicate = hub.receive_webhook(connection["id"], body, signature, timestamp, "jira-100")

    assert accepted["accepted"] is True
    assert duplicate["duplicate"] is True
    assert accepted["job_id"] == duplicate["job_id"]


def test_oauth_start_uses_pkce_and_one_time_state(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_ENV", "development")
    hub = IntegrationHub(str(tmp_path / "integrations.db"))
    connection = hub.register_connection(
        "acme", "sales", "hubspot", "Revenue OAuth", "oauth", "env://HUBSPOT_CLIENT_SECRET",
        {"authorize_url": "https://example.com/oauth/authorize", "token_url": "https://example.com/oauth/token",
         "client_id": "client-123", "redirect_uri": "https://app.example.com/api/organization/integrations/oauth/callback",
         "scopes": ["crm.objects.contacts.read"]}, "revenue-lead",
    )
    started = hub.create_oauth_authorization("acme", connection["id"])

    assert "code_challenge_method=S256" in started["authorization_url"]
    state = started["authorization_url"].split("state=", 1)[1].split("&", 1)[0]
    consumed = hub.consume_oauth_state(state)
    assert consumed["connection_id"] == connection["id"]
    try:
        hub.consume_oauth_state(state)
    except ValueError as error:
        assert "already used" in str(error)
    else:
        raise AssertionError("OAuth state was reusable")


@respx.mock
def test_oauth_callback_exchanges_and_encrypts_provider_token(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_INTEGRATIONS_DB_PATH", str(tmp_path / "integrations.db"))
    monkeypatch.setenv("RAPID_SECRETS_DB_PATH", str(tmp_path / "secrets.db"))
    monkeypatch.setenv("RAPID_LOCAL_VAULT_KEY_PATH", str(tmp_path / "vault.key"))
    monkeypatch.setenv("PROVIDER_CLIENT_SECRET", "client-secret")
    hub = IntegrationHub(str(tmp_path / "integrations.db"))
    connection = hub.register_connection(
        "acme", "sales", "hubspot", "Revenue OAuth callback", "oauth", "",
        {"authorize_url": "https://provider.test/authorize", "token_url": "https://provider.test/token",
         "client_id": "client-123", "client_secret_ref": "env://PROVIDER_CLIENT_SECRET",
         "redirect_uri": "https://app.example.com/api/organization/integrations/oauth/callback"}, "revenue-lead",
    )
    state = parse_qs(urlparse(hub.create_oauth_authorization("acme", connection["id"])["authorization_url"]).query)["state"][0]
    respx.post("https://provider.test/token").mock(return_value=httpx.Response(200, json={"access_token": "access-123", "refresh_token": "refresh-123", "expires_in": 3600}))
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/organization/integrations/oauth/callback", params={"state": state, "code": "code-123"})

    assert response.status_code == 200
    assert response.json()["connection"]["status"] == "connected"
    raw = hub._raw_connection(connection["id"])
    stored = json.loads(get_secret_vault().resolve(raw["credential_ref"], "acme"))
    assert stored["refresh_token"] == "refresh-123"
