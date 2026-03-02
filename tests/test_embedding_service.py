import pytest
from unittest.mock import patch, MagicMock
from app.services.embedding_service import (
    SentenceTransformerProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    HuggingFaceAPIProvider,
    EmbeddingManager,
)


class TestSentenceTransformerProvider:
    """Tests for local Sentence Transformer embeddings"""

    def test_list_models_returns_known_models(self):
        models = SentenceTransformerProvider.list_models()
        assert "all-MiniLM-L6-v2" in models
        assert "all-mpnet-base-v2" in models
        assert len(models) > 0

    def test_default_model(self):
        provider = SentenceTransformerProvider()
        assert provider.model_name == "all-MiniLM-L6-v2"

    def test_custom_model(self):
        provider = SentenceTransformerProvider(model_name="all-mpnet-base-v2")
        assert provider.model_name == "all-mpnet-base-v2"

    def test_get_name(self):
        provider = SentenceTransformerProvider()
        assert "sentence-transformers" in provider.get_name()
        assert "all-MiniLM-L6-v2" in provider.get_name()

    def test_known_dimension(self):
        provider = SentenceTransformerProvider(model_name="all-MiniLM-L6-v2")
        assert provider.get_dimension() == 384

    def test_known_dimension_mpnet(self):
        provider = SentenceTransformerProvider(model_name="all-mpnet-base-v2")
        assert provider.get_dimension() == 768

    @pytest.mark.skipif(
        not SentenceTransformerProvider().is_available(),
        reason="sentence-transformers not installed",
    )
    def test_embed_produces_correct_dimension(self):
        provider = SentenceTransformerProvider()
        embeddings = provider.embed(["hello world", "test sentence"])
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 384
        assert len(embeddings[1]) == 384
        assert all(isinstance(v, float) for v in embeddings[0])


class TestOpenAIEmbeddingProvider:
    """Tests for OpenAI embedding provider"""

    def test_list_models(self):
        models = OpenAIEmbeddingProvider.list_models()
        assert "text-embedding-3-small" in models
        assert "text-embedding-3-large" in models

    def test_default_model_and_dimension(self):
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        assert provider.model == "text-embedding-3-small"
        assert provider.get_dimension() == 1536

    def test_is_available_with_key(self):
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        assert provider.is_available() is True

    def test_is_not_available_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = OpenAIEmbeddingProvider(api_key=None)
            assert provider.is_available() is False

    def test_get_name(self):
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        assert "openai" in provider.get_name()

    def test_embed_calls_api(self):
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        mock_response = MagicMock()
        mock_data = MagicMock()
        mock_data.embedding = [0.1] * 1536
        mock_response.data = [mock_data, mock_data]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response
        provider._client = mock_client

        result = provider.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 1536
        mock_client.embeddings.create.assert_called_once_with(
            input=["hello", "world"], model="text-embedding-3-small"
        )


class TestHuggingFaceAPIProvider:
    """Tests for HuggingFace API embedding provider"""

    def test_list_models(self):
        models = HuggingFaceAPIProvider.list_models()
        assert "sentence-transformers/all-MiniLM-L6-v2" in models

    def test_default_model(self):
        provider = HuggingFaceAPIProvider(api_key="test-key")
        assert provider.model == "sentence-transformers/all-MiniLM-L6-v2"
        assert provider.get_dimension() == 384

    def test_is_available_with_key(self):
        provider = HuggingFaceAPIProvider(api_key="test-key")
        assert provider.is_available() is True

    def test_get_name(self):
        provider = HuggingFaceAPIProvider(api_key="test-key")
        assert "huggingface" in provider.get_name()


class TestOllamaEmbeddingProvider:
    """Tests for Ollama embedding provider"""

    def test_default_model(self):
        provider = OllamaEmbeddingProvider()
        assert provider.model == "nomic-embed-text"

    def test_custom_base_url(self):
        provider = OllamaEmbeddingProvider(base_url="http://myhost:11434")
        assert provider.base_url == "http://myhost:11434"

    def test_get_name(self):
        provider = OllamaEmbeddingProvider()
        assert "ollama" in provider.get_name()


class TestEmbeddingManager:
    """Tests for the EmbeddingManager singleton"""

    def setup_method(self):
        # Reset singleton for each test
        EmbeddingManager._instance = None

    def test_initialization(self):
        manager = EmbeddingManager()
        assert "sentence-transformers" in manager.providers
        assert "ollama" in manager.providers
        assert "openai" in manager.providers
        assert "huggingface" in manager.providers

    def test_get_available_providers(self):
        manager = EmbeddingManager()
        available = manager.get_available_providers()
        assert isinstance(available, list)

    def test_set_active(self):
        manager = EmbeddingManager()
        manager.set_active("openai")
        assert manager.active_provider_name == "openai"

    def test_set_active_unknown_provider(self):
        manager = EmbeddingManager()
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            manager.set_active("nonexistent_provider")

    def test_get_provider_models(self):
        manager = EmbeddingManager()
        models = manager.get_provider_models("sentence-transformers")
        assert "all-MiniLM-L6-v2" in models

    def test_get_provider_models_openai(self):
        manager = EmbeddingManager()
        models = manager.get_provider_models("openai")
        assert "text-embedding-3-small" in models

    def test_get_provider_info(self):
        manager = EmbeddingManager()
        info = manager.get_provider_info()
        assert "active" in info
        assert "providers" in info
        assert "sentence-transformers" in info["providers"]
        assert "available" in info["providers"]["sentence-transformers"]

    def test_update_provider_sentence_transformers(self):
        manager = EmbeddingManager()
        manager.update_provider("sentence-transformers", model="all-mpnet-base-v2")
        provider = manager.providers["sentence-transformers"]
        assert provider.model_name == "all-mpnet-base-v2"

    def test_update_provider_openai(self):
        manager = EmbeddingManager()
        manager.update_provider("openai", api_key="new-key", model="text-embedding-3-large")
        provider = manager.providers["openai"]
        assert provider.api_key == "new-key"
        assert provider.model == "text-embedding-3-large"

    def test_update_provider_unknown(self):
        manager = EmbeddingManager()
        with pytest.raises(ValueError, match="Unknown provider"):
            manager.update_provider("nonexistent")

    @pytest.mark.skipif(
        not SentenceTransformerProvider().is_available(),
        reason="sentence-transformers not installed",
    )
    def test_embed_with_local_provider(self):
        manager = EmbeddingManager()
        manager.set_active("sentence-transformers")
        result = manager.embed(["test"])
        assert len(result) == 1
        assert len(result[0]) == 384

    def test_get_dimension(self):
        manager = EmbeddingManager()
        manager.update_provider("openai", api_key="test")
        manager.set_active("openai")
        dim = manager.get_dimension()
        assert dim == 1536


class TestEmbeddingAPIEndpoints:
    """Tests for the FastAPI embedding endpoints"""

    def setup_method(self):
        EmbeddingManager._instance = None

    def test_configure_embedding_without_auth(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.post(
            "/configure-embedding",
            json={"provider": "sentence-transformers", "model": "all-MiniLM-L6-v2"},
        )
        assert response.status_code == 403

    def test_embedding_providers_without_auth(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/embedding-providers")
        assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
