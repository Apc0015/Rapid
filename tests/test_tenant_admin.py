import pytest

from infrastructure.embedding_service import EmbeddingService
from infrastructure.llm_adapter import TenantLLMAdapter
from infrastructure.llm_registry import get_provider
from infrastructure.tenant_admin_store import TenantAdminError, TenantAdminStore


def test_admin_configuration_defaults_to_ollama_and_sandbox(tmp_path):
    store = TenantAdminStore(str(tmp_path / "admin.db"))
    configuration = store.configuration("acme")

    ollama = next(model for model in configuration["models"] if model["provider"] == "ollama")
    sandbox = next(connection for connection in configuration["connections"] if connection["connection_key"] == "knowledge_storage")
    assert ollama["enabled"] is True
    assert sandbox["status"] == "sandbox_ready"
    assert configuration["trust_summary"]["connections"]["status"] == "sandbox"
    assert configuration["trust_summary"]["boundary"]["status"] == "controlled"


def test_feature_manifest_is_tenant_scoped_and_exposes_no_configuration_secrets(tmp_path):
    store = TenantAdminStore(str(tmp_path / "admin.db"))
    store.update_feature("northstar", "crm", False)

    manifest = store.feature_manifest("northstar")
    other_manifest = store.feature_manifest("other")

    assert next(item for item in manifest if item["key"] == "crm") == {"key": "crm", "enabled": False}
    assert next(item for item in other_manifest if item["key"] == "crm") == {"key": "crm", "enabled": True}
    assert all(set(item) == {"key", "enabled"} for item in manifest)


def test_openrouter_requires_a_credential_reference_when_enabled(tmp_path):
    store = TenantAdminStore(str(tmp_path / "admin.db"))
    try:
        store.update_model("acme", "openrouter", True, "openai/gpt-4.1-mini", "https://openrouter.ai/api/v1", "")
    except TenantAdminError as error:
        assert "credential reference" in str(error)
    else:
        raise AssertionError("Expected OpenRouter configuration to require a credential reference")


def test_enabling_openrouter_makes_it_the_only_active_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(TenantAdminStore, "_sync_llm_runtime", staticmethod(lambda *args: None))
    store = TenantAdminStore(str(tmp_path / "admin.db"))
    store.update_model("acme", "openrouter", True, "openai/gpt-4.1-mini", "https://openrouter.ai/api/v1", "env://OPENROUTER_API_KEY")

    models = store.configuration("acme")["models"]
    assert next(model for model in models if model["provider"] == "openrouter")["enabled"] is True
    assert next(model for model in models if model["provider"] == "ollama")["enabled"] is False
    assert store.active_model_runtime("acme")["provider"] == "openrouter"


def test_ollama_model_configuration_is_saved_for_the_tenant(tmp_path, monkeypatch):
    synced = []
    monkeypatch.setattr(TenantAdminStore, "_sync_llm_runtime", staticmethod(lambda *args: synced.append(args)))
    store = TenantAdminStore(str(tmp_path / "admin.db"))
    model = store.update_model("localdemo", "ollama", True, "llama3.1:8b", "http://localhost:11434/v1", "")

    assert model["enabled"] is True
    assert model["model_name"] == "llama3.1:8b"
    assert model["endpoint"] == "http://localhost:11434/v1"
    assert synced[0][1] == "ollama"


def test_tenant_admin_invites_users_without_cross_tenant_visibility(tmp_path):
    store = TenantAdminStore(str(tmp_path / "admin.db"))
    invitation = store.invite_user("acme", "priya@example.com", "Priya Shah", "manager", ["sales"])
    assert invitation["status"] == "pending"
    assert len(store.list_invitations("acme")) == 1
    assert store.list_invitations("other") == []


@pytest.mark.asyncio
async def test_embeddings_use_the_tenant_admin_ollama_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_TENANT_ADMIN_DB_PATH", str(tmp_path / "admin.db"))
    service = EmbeddingService()
    calls = []

    async def fake_ollama(text, model, endpoint):
        calls.append((text, model, endpoint))
        return [1.0, 0.0, 0.0]

    monkeypatch.setattr(service, "_ollama_embed_at", fake_ollama)
    embeddings, backend = await service.embed_batch_for_tenant(["first", "second"], "acme", model="nomic-embed-text")

    assert backend == "tenant_ollama"
    assert embeddings == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    assert calls[0][2] == "http://localhost:11434"


def test_tenant_llm_adapter_resolves_credential_reference(monkeypatch):
    import infrastructure.secret_vault as secret_vault

    class Vault:
        def resolve(self, reference, tenant_id):
            assert reference == "vault://provider-key"
            assert tenant_id == "acme"
            return "resolved-key"

    monkeypatch.setattr(secret_vault, "get_secret_vault", lambda: Vault())
    provider = get_provider("openrouter")
    adapter = TenantLLMAdapter(
        tenant_id="acme", provider_id="openrouter", model_id="openai/gpt-4.1-mini",
        cfg={"base_url": "https://openrouter.ai/api/v1", "credential_ref": "vault://provider-key"},
        api_style=provider.api_style,
    )

    assert adapter._api_key == "resolved-key"
