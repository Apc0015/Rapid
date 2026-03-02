from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import os
import logging
import requests
import json
from openai import OpenAI
import anthropic
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_community.llms import Ollama

logger = logging.getLogger(__name__)

class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    def __init__(self, config: Dict[str, Any]):
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured"""
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        """List available models for this provider"""
        pass

    @abstractmethod
    def test_connection(self, model: str) -> bool:
        """Test connection to a specific model"""
        pass

    @abstractmethod
    def get_langchain_llm(self, model: str, **kwargs) -> Any:
        """Get LangChain LLM instance"""
        pass

    @abstractmethod
    def get_embeddings_client(self, model: str = None) -> Any:
        """Get embeddings client (if supported)"""
        pass

class OpenAIProvider(LLMProvider):
    """OpenAI cloud provider"""

    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key", os.getenv("OPENAI_API_KEY"))
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)

    def is_available(self) -> bool:
        return self.api_key is not None and self.client is not None

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            models = self.client.models.list()
            # Filter for chat models
            chat_models = [m.id for m in models.data if m.id.startswith(('gpt-', 'chatgpt-'))]
            return sorted(chat_models)
        except Exception:
            return ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]  # Fallback

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            return len(response.choices) > 0
        except Exception:
            return False

    def get_langchain_llm(self, model: str, **kwargs) -> ChatOpenAI:
        return ChatOpenAI(
            model=model,
            openai_api_key=self.api_key,
            temperature=kwargs.get('temperature', 0),
            max_tokens=kwargs.get('max_tokens', 500)
        )

    def get_embeddings_client(self, model: str = "text-embedding-3-small") -> OpenAI:
        return self.client

class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider"""

    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key", os.getenv("ANTHROPIC_API_KEY"))
        self.client = None
        if self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)

    def is_available(self) -> bool:
        return self.api_key is not None and self.client is not None

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            models = self.client.models.list()
            return [m.id for m in models.data]
        except Exception:
            return ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"]  # Fallback

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hello"}]
            )
            return len(response.content) > 0
        except Exception:
            return False

    def get_langchain_llm(self, model: str, **kwargs) -> ChatAnthropic:
        return ChatAnthropic(
            model=model,
            anthropic_api_key=self.api_key,
            temperature=kwargs.get('temperature', 0),
            max_tokens=kwargs.get('max_tokens', 500)
        )

    def get_embeddings_client(self, model: str = None) -> None:
        return None  # Anthropic doesn't provide embeddings

class OpenRouterProvider(LLMProvider):
    """OpenRouter provider for multiple models"""

    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key", os.getenv("OPENROUTER_API_KEY"))
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = None
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

    def is_available(self) -> bool:
        return self.api_key is not None and self.client is not None

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            # OpenRouter provides a models endpoint
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("data", [])]
            else:
                return []  # Fallback to empty list
        except Exception:
            return ["anthropic/claude-3-opus", "openai/gpt-4", "meta-llama/llama-2-70b-chat"]  # Fallback

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            return len(response.choices) > 0
        except Exception:
            return False

    def get_langchain_llm(self, model: str, **kwargs) -> ChatOpenAI:
        return ChatOpenAI(
            model=model,
            openai_api_key=self.api_key,
            base_url=self.base_url,
            temperature=kwargs.get('temperature', 0),
            max_tokens=kwargs.get('max_tokens', 500)
        )

    def get_embeddings_client(self, model: str = None) -> OpenAI:
        return self.client

class OllamaProvider(LLMProvider):
    """Ollama local provider"""

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.client = None

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
            return []
        except Exception:
            return []

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": "Hello", "stream": False},
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_langchain_llm(self, model: str, **kwargs) -> Ollama:
        return Ollama(
            model=model,
            base_url=self.base_url,
            temperature=kwargs.get('temperature', 0)
        )

    def get_embeddings_client(self, model: str = None) -> None:
        return None  # Ollama doesn't provide direct embeddings API

class LMStudioProvider(LLMProvider):
    """LM Studio local provider"""

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get("base_url", "http://localhost:1234")
        self.client = None

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("data", [])]
            return []
        except Exception:
            return ["local-model"]  # Fallback

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            # Use OpenAI-compatible API
            client = OpenAI(base_url=self.base_url, api_key="lm-studio")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            return len(response.choices) > 0
        except Exception:
            return False

    def get_langchain_llm(self, model: str, **kwargs) -> ChatOpenAI:
        return ChatOpenAI(
            model=model,
            base_url=self.base_url,
            api_key="lm-studio",  # LM Studio doesn't require real API key
            temperature=kwargs.get('temperature', 0),
            max_tokens=kwargs.get('max_tokens', 500)
        )

    def get_embeddings_client(self, model: str = None) -> None:
        return None  # LM Studio may not provide embeddings

class LLMManager:
    """Central manager for all LLM providers (singleton)"""

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
        self.providers = {}
        self.active_provider = None
        self.active_model = None
        self._load_providers()

    def _load_providers(self):
        """Load all configured providers"""
        # Cloud providers
        self.providers["openai"] = OpenAIProvider({"api_key": os.getenv("OPENAI_API_KEY")})
        self.providers["anthropic"] = AnthropicProvider({"api_key": os.getenv("ANTHROPIC_API_KEY")})
        self.providers["openrouter"] = OpenRouterProvider({"api_key": os.getenv("OPENROUTER_API_KEY")})

        # Local providers
        self.providers["ollama"] = OllamaProvider({"base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")})
        self.providers["lmstudio"] = LMStudioProvider({"base_url": os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234")})

    def get_available_providers(self) -> List[str]:
        """Get list of available providers"""
        return [name for name, provider in self.providers.items() if provider.is_available()]

    def get_provider_models(self, provider_name: str) -> List[str]:
        """Get models for a specific provider"""
        if provider_name in self.providers:
            return self.providers[provider_name].list_models()
        return []

    def test_provider_connection(self, provider_name: str, model: str) -> bool:
        """Test connection to a provider and model"""
        if provider_name in self.providers:
            return self.providers[provider_name].test_connection(model)
        return False

    def get_langchain_llm(self, provider_name: str, model: str, **kwargs) -> Any:
        """Get LangChain LLM instance for a provider and model"""
        if provider_name in self.providers:
            return self.providers[provider_name].get_langchain_llm(model, **kwargs)
        raise ValueError(f"Provider {provider_name} not found")

    def get_embeddings_client(self, provider_name: str, model: str = None) -> Any:
        """Get embeddings client for a provider"""
        if provider_name in self.providers:
            return self.providers[provider_name].get_embeddings_client(model)
        return None

    def update_provider_config(self, provider_name: str, config: Dict[str, Any]):
        """Update configuration for a provider"""
        if provider_name in self.providers:
            # Reinitialize provider with new config
            if provider_name == "openai":
                self.providers[provider_name] = OpenAIProvider(config)
            elif provider_name == "anthropic":
                self.providers[provider_name] = AnthropicProvider(config)
            elif provider_name == "openrouter":
                self.providers[provider_name] = OpenRouterProvider(config)
            elif provider_name == "ollama":
                self.providers[provider_name] = OllamaProvider(config)
            elif provider_name == "lmstudio":
                self.providers[provider_name] = LMStudioProvider(config)

    def set_active(self, provider_name: str, model: str):
        """Set the active provider and model for queries."""
        self.active_provider = provider_name
        self.active_model = model

    def get_chat_llm(self) -> Any:
        """Get the chat LLM. Uses active provider/model if set, otherwise auto-selects."""
        # Use explicitly configured provider/model if set
        if self.active_provider and self.active_model:
            try:
                return self.get_langchain_llm(self.active_provider, self.active_model)
            except Exception as e:
                logger.warning("Failed to use active LLM %s/%s: %s", self.active_provider, self.active_model, e)

        # Fallback: auto-select first available
        available_providers = self.get_available_providers()
        priority_order = ["openai", "anthropic", "openrouter", "ollama", "lmstudio"]

        for provider in priority_order:
            if provider in available_providers:
                try:
                    models = self.get_provider_models(provider)
                    if models:
                        return self.get_langchain_llm(provider, models[0])
                except Exception as e:
                    logger.warning("Failed to get LLM from %s: %s", provider, e)
                    continue

        raise ValueError("No available LLM providers found. Please configure at least one provider.")

    def get_embedding_client(self) -> Any:
        """Get the best available embedding client"""
        available_providers = self.get_available_providers()
        
        # Try providers that support embeddings
        embedding_providers = ["openai", "ollama", "lmstudio"]  # Add more as needed
        
        for provider in embedding_providers:
            if provider in available_providers:
                try:
                    return self.get_embeddings_client(provider)
                except Exception as e:
                    logger.warning("Failed to get embeddings from %s: %s", provider, e)
                    continue
        
        return None