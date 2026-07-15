import pytest

from infrastructure.embedding_service import EmbeddingService
from infrastructure.tenant_admin_store import TenantAdminError, TenantAdminStore


def test_admin_configuration_defaults_to_ollama_and_sandbox(tmp_path):
    store = TenantAdminStore(str(tmp_path / "admin.db"))
    configuration = store.configuration("acme")

    ollama = next(model for model in configuration["models"] if model["provider"] == "ollama")
    sandbox = next(connection for connection in configuration["connections"] if connection["connection_key"] == "knowledge_storage")
    assert ollama["enabled"] is True
    assert sandbox["status"] == "sandbox_ready"


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
