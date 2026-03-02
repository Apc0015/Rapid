from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import os
import logging
import requests
import json

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers"""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured"""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Return the embedding dimension for the active model"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return a human-readable provider name"""
        pass


class SentenceTransformerProvider(EmbeddingProvider):
    """Local embeddings via sentence-transformers (runs entirely offline)"""

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    MODEL_DIMENSIONS = {
        "all-MiniLM-L6-v2": 384,
        "all-MiniLM-L12-v2": 384,
        "all-mpnet-base-v2": 768,
        "paraphrase-MiniLM-L6-v2": 384,
        "multi-qa-MiniLM-L6-cos-v1": 384,
        # Multilingual models
        "intfloat/multilingual-e5-base": 768,
        "intfloat/multilingual-e5-large": 1024,
        "sentence-transformers/LaBSE": 768,
    }

    def __init__(self, model_name: str = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model = None
        self._dimension = self.MODEL_DIMENSIONS.get(self.model_name)

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self._dimension = self._model.get_sentence_embedding_dimension()
            except ImportError:
                raise ImportError(
                    "sentence-transformers is not installed. "
                    "Run: pip install sentence-transformers"
                )
        return self._model

    def embed(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        embeddings = model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    def is_available(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
            return True
        except ImportError:
            return False

    def get_dimension(self) -> int:
        if self._dimension is None:
            self._load_model()
        return self._dimension

    def get_name(self) -> str:
        return f"sentence-transformers ({self.model_name})"

    @staticmethod
    def list_models() -> List[str]:
        return list(SentenceTransformerProvider.MODEL_DIMENSIONS.keys())


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embeddings via Ollama's local API"""

    DEFAULT_MODEL = "nomic-embed-text"
    MODEL_DIMENSIONS = {
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        "all-minilm": 384,
        "snowflake-arctic-embed": 1024,
    }

    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or self.DEFAULT_MODEL
        self._dimension = self.MODEL_DIMENSIONS.get(self.model)

    def embed(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama embedding failed ({response.status_code}): {response.text}"
                )
            data = response.json()
            embeddings.append(data["embedding"])

        if self._dimension is None and embeddings:
            self._dimension = len(embeddings[0])

        return embeddings

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code != 200:
                return False
            data = response.json()
            model_names = [m["name"] for m in data.get("models", [])]
            # Check if embedding model is pulled (match with or without :latest tag)
            return any(
                self.model in name or name.startswith(self.model)
                for name in model_names
            )
        except Exception:
            return False

    def get_dimension(self) -> int:
        if self._dimension is None:
            # Try to get dimension by embedding a short text
            try:
                result = self.embed(["test"])
                self._dimension = len(result[0])
            except Exception:
                return 768  # Fallback for nomic-embed-text
        return self._dimension

    def get_name(self) -> str:
        return f"ollama ({self.model})"

    def list_models(self) -> List[str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return list(self.MODEL_DIMENSIONS.keys())


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embeddings via OpenAI API"""

    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, api_key: str = None, model: str = "text-embedding-3-small"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self._client = None
        self._dimension = self.MODEL_DIMENSIONS.get(self.model, 1536)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        response = client.embeddings.create(input=texts, model=self.model)
        return [data.embedding for data in response.data]

    def is_available(self) -> bool:
        return self.api_key is not None

    def get_dimension(self) -> int:
        return self._dimension

    def get_name(self) -> str:
        return f"openai ({self.model})"

    @staticmethod
    def list_models() -> List[str]:
        return list(OpenAIEmbeddingProvider.MODEL_DIMENSIONS.keys())


class HuggingFaceAPIProvider(EmbeddingProvider):
    """Embeddings via HuggingFace Inference API"""

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    MODEL_DIMENSIONS = {
        "sentence-transformers/all-MiniLM-L6-v2": 384,
        "sentence-transformers/all-mpnet-base-v2": 768,
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-base-en-v1.5": 768,
    }

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("HUGGINGFACE_API_KEY")
        self.model = model or self.DEFAULT_MODEL
        self.api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.model}"
        self._dimension = self.MODEL_DIMENSIONS.get(self.model)

    def embed(self, texts: List[str]) -> List[List[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = requests.post(
            self.api_url,
            headers=headers,
            json={"inputs": texts, "options": {"wait_for_model": True}},
            timeout=60,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"HuggingFace API error ({response.status_code}): {response.text}"
            )
        embeddings = response.json()

        if self._dimension is None and embeddings:
            self._dimension = len(embeddings[0])

        return embeddings

    def is_available(self) -> bool:
        return self.api_key is not None

    def get_dimension(self) -> int:
        if self._dimension is None:
            return 384  # Fallback for default model
        return self._dimension

    def get_name(self) -> str:
        return f"huggingface ({self.model})"

    @staticmethod
    def list_models() -> List[str]:
        return list(HuggingFaceAPIProvider.MODEL_DIMENSIONS.keys())


class EmbeddingManager:
    """Central manager for all embedding providers (singleton)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.providers: Dict[str, EmbeddingProvider] = {}
        self.active_provider_name: Optional[str] = None
        self._load_providers()

    def _load_providers(self):
        """Load all embedding providers"""
        self.providers["sentence-transformers"] = SentenceTransformerProvider()
        self.providers["ollama"] = OllamaEmbeddingProvider()
        self.providers["openai"] = OpenAIEmbeddingProvider()
        self.providers["huggingface"] = HuggingFaceAPIProvider()

        # Auto-select: prefer local first, then cloud
        for name in ["sentence-transformers", "ollama", "openai", "huggingface"]:
            if self.providers[name].is_available():
                self.active_provider_name = name
                logger.info("Auto-selected embedding provider: %s", name)
                break

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names"""
        return [name for name, p in self.providers.items() if p.is_available()]

    def get_active_provider(self) -> EmbeddingProvider:
        """Get the currently active embedding provider"""
        if self.active_provider_name and self.active_provider_name in self.providers:
            return self.providers[self.active_provider_name]

        # Fallback: try to find any available provider
        available = self.get_available_providers()
        if available:
            self.active_provider_name = available[0]
            return self.providers[available[0]]

        raise ValueError(
            "No embedding provider available. Install sentence-transformers "
            "for local embeddings or set OPENAI_API_KEY for cloud embeddings."
        )

    def set_active(self, provider_name: str, model: str = None):
        """Set the active embedding provider, optionally with a specific model"""
        if provider_name not in self.providers:
            raise ValueError(f"Unknown embedding provider: {provider_name}")

        # Reinitialize provider with the new model if specified
        if model:
            self.update_provider(provider_name, model=model)

        self.active_provider_name = provider_name
        logger.info("Set active embedding provider: %s", provider_name)

    def update_provider(self, provider_name: str, **kwargs):
        """Update/reinitialize a provider with new configuration"""
        if provider_name == "sentence-transformers":
            model = kwargs.get("model", SentenceTransformerProvider.DEFAULT_MODEL)
            self.providers[provider_name] = SentenceTransformerProvider(model_name=model)
        elif provider_name == "ollama":
            base_url = kwargs.get("base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
            model = kwargs.get("model", OllamaEmbeddingProvider.DEFAULT_MODEL)
            self.providers[provider_name] = OllamaEmbeddingProvider(base_url=base_url, model=model)
        elif provider_name == "openai":
            api_key = kwargs.get("api_key", os.getenv("OPENAI_API_KEY"))
            model = kwargs.get("model", "text-embedding-3-small")
            self.providers[provider_name] = OpenAIEmbeddingProvider(api_key=api_key, model=model)
        elif provider_name == "huggingface":
            api_key = kwargs.get("api_key", os.getenv("HUGGINGFACE_API_KEY"))
            model = kwargs.get("model", HuggingFaceAPIProvider.DEFAULT_MODEL)
            self.providers[provider_name] = HuggingFaceAPIProvider(api_key=api_key, model=model)
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using the active provider"""
        provider = self.get_active_provider()
        return provider.embed(texts)

    def embed_with_model(self, texts: List[str], model_name: str) -> List[List[float]]:
        """Embed texts using a specific sentence-transformers model.

        Used when language detection requests a multilingual model (e.g.
        intfloat/multilingual-e5-base) instead of the default English model.
        Falls back to the active provider if the model cannot be loaded.
        """
        try:
            provider = SentenceTransformerProvider(model_name=model_name)
            return provider.embed(texts)
        except Exception as e:
            logger.warning(
                "embed_with_model failed for model '%s', falling back to default: %s",
                model_name, e,
            )
            return self.embed(texts)

    def get_dimension(self) -> int:
        """Get embedding dimension of the active provider"""
        provider = self.get_active_provider()
        return provider.get_dimension()

    def get_provider_info(self) -> Dict[str, Any]:
        """Get info about all providers and the active one"""
        info = {
            "active": self.active_provider_name,
            "providers": {},
        }
        for name, provider in self.providers.items():
            info["providers"][name] = {
                "available": provider.is_available(),
                "name": provider.get_name(),
            }
            if provider.is_available():
                try:
                    info["providers"][name]["dimension"] = provider.get_dimension()
                except Exception:
                    pass
        return info

    def get_provider_models(self, provider_name: str) -> List[str]:
        """Get available models for a provider"""
        if provider_name == "sentence-transformers":
            return SentenceTransformerProvider.list_models()
        elif provider_name == "openai":
            return OpenAIEmbeddingProvider.list_models()
        elif provider_name == "huggingface":
            return HuggingFaceAPIProvider.list_models()
        elif provider_name == "ollama":
            provider = self.providers.get("ollama")
            if provider and isinstance(provider, OllamaEmbeddingProvider):
                return provider.list_models()
        return []
