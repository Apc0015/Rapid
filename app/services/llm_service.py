"""
LLM Service — multi-provider async chat interface.

Provides a single `async chat(prompt, system, max_tokens) -> str` method
used by all agents. No LangChain. Raw SDK calls only.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import os
import logging
import requests
import httpx

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        pass

    @abstractmethod
    def test_connection(self, model: str) -> bool:
        pass

    @abstractmethod
    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.0,
    ) -> str:
        pass


class OpenAIProvider(LLMProvider):
    DEFAULT_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]

    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key", os.getenv("OPENAI_API_KEY"))
        self._sync_client = None
        self._async_client = None

    def _get_sync(self):
        if self._sync_client is None and self.api_key:
            from openai import OpenAI
            self._sync_client = OpenAI(api_key=self.api_key)
        return self._sync_client

    def _get_async(self):
        if self._async_client is None and self.api_key:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(api_key=self.api_key)
        return self._async_client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            client = self._get_sync()
            models = client.models.list()
            chat_models = [
                m.id for m in models.data
                if m.id.startswith(("gpt-", "chatgpt-", "o1", "o3"))
            ]
            return sorted(chat_models) or self.DEFAULT_MODELS
        except Exception:
            return self.DEFAULT_MODELS

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            client = self._get_sync()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5,
            )
            return len(resp.choices) > 0
        except Exception:
            return False

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.0,
    ) -> str:
        client = self._get_async()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()


class AnthropicProvider(LLMProvider):
    DEFAULT_MODELS = ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]

    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key", os.getenv("ANTHROPIC_API_KEY"))
        self._sync_client = None
        self._async_client = None

    def _get_sync(self):
        if self._sync_client is None and self.api_key:
            import anthropic
            self._sync_client = anthropic.Anthropic(api_key=self.api_key)
        return self._sync_client

    def _get_async(self):
        if self._async_client is None and self.api_key:
            import anthropic
            self._async_client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._async_client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            client = self._get_sync()
            models = client.models.list()
            return [m.id for m in models.data] or self.DEFAULT_MODELS
        except Exception:
            return self.DEFAULT_MODELS

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            client = self._get_sync()
            resp = client.messages.create(
                model=model, max_tokens=5,
                messages=[{"role": "user", "content": "Hello"}],
            )
            return len(resp.content) > 0
        except Exception:
            return False

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.0,
    ) -> str:
        client = self._get_async()
        kwargs: Dict[str, Any] = {
            "model": model or "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        resp = await client.messages.create(**kwargs)
        return resp.content[0].text.strip()


class OpenRouterProvider(LLMProvider):
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key", os.getenv("OPENROUTER_API_KEY"))
        self._sync_client = None
        self._async_client = None

    def _get_sync(self):
        if self._sync_client is None and self.api_key:
            from openai import OpenAI
            self._sync_client = OpenAI(api_key=self.api_key, base_url=self.BASE_URL)
        return self._sync_client

    def _get_async(self):
        if self._async_client is None and self.api_key:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.BASE_URL)
        return self._async_client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            resp = requests.get(
                f"{self.BASE_URL}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return [m["id"] for m in resp.json().get("data", [])]
        except Exception:
            pass
        return []

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            client = self._get_sync()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5,
            )
            return len(resp.choices) > 0
        except Exception:
            return False

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.0,
    ) -> str:
        client = self._get_async()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await client.chat.completions.create(
            model=model or "openai/gpt-4o-mini",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()


class OllamaProvider(LLMProvider):
    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get(
            "base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            pass
        return []

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": "Hello", "stream": False},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.0,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model or "llama3",
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()


class LMStudioProvider(LLMProvider):
    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get(
            "base_url", os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234")
        )
        self._sync_client = None
        self._async_client = None

    def _get_sync(self):
        if self._sync_client is None:
            from openai import OpenAI
            self._sync_client = OpenAI(base_url=f"{self.base_url}/v1", api_key="lm-studio")
        return self._sync_client

    def _get_async(self):
        if self._async_client is None:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(
                base_url=f"{self.base_url}/v1", api_key="lm-studio"
            )
        return self._async_client

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/v1/models", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        try:
            resp = requests.get(f"{self.base_url}/v1/models", timeout=5)
            if resp.status_code == 200:
                return [m["id"] for m in resp.json().get("data", [])]
        except Exception:
            pass
        return ["local-model"]

    def test_connection(self, model: str) -> bool:
        if not self.is_available():
            return False
        try:
            client = self._get_sync()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5,
            )
            return len(resp.choices) > 0
        except Exception:
            return False

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.0,
    ) -> str:
        client = self._get_async()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await client.chat.completions.create(
            model=model or "local-model",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()


class LLMManager:
    """Central manager for all LLM providers (singleton)."""

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
        self.providers: Dict[str, LLMProvider] = {}
        self.active_provider: Optional[str] = None
        self.active_model: Optional[str] = None
        self._load_providers()

    def _load_providers(self):
        self.providers["openai"] = OpenAIProvider(
            {"api_key": os.getenv("OPENAI_API_KEY")}
        )
        self.providers["anthropic"] = AnthropicProvider(
            {"api_key": os.getenv("ANTHROPIC_API_KEY")}
        )
        self.providers["openrouter"] = OpenRouterProvider(
            {"api_key": os.getenv("OPENROUTER_API_KEY")}
        )
        self.providers["ollama"] = OllamaProvider(
            {"base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")}
        )
        self.providers["lmstudio"] = LMStudioProvider(
            {"base_url": os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234")}
        )

    def get_available_providers(self) -> List[str]:
        return [name for name, p in self.providers.items() if p.is_available()]

    def get_provider_models(self, provider_name: str) -> List[str]:
        if provider_name in self.providers:
            return self.providers[provider_name].list_models()
        return []

    def test_provider_connection(self, provider_name: str, model: str) -> bool:
        if provider_name in self.providers:
            return self.providers[provider_name].test_connection(model)
        return False

    def set_active(self, provider_name: str, model: str):
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        self.active_provider = provider_name
        self.active_model = model
        logger.info("Active LLM set to %s / %s", provider_name, model)

    def update_provider_config(self, provider_name: str, config: Dict[str, Any]):
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

    def _get_active(self) -> tuple:
        """Return (provider, model) — uses configured active or auto-selects."""
        if self.active_provider and self.active_model:
            p = self.providers.get(self.active_provider)
            if p and p.is_available():
                return p, self.active_model

        priority = ["openai", "anthropic", "openrouter", "ollama", "lmstudio"]
        for name in priority:
            p = self.providers.get(name)
            if p and p.is_available():
                models = p.list_models()
                if models:
                    return p, models[0]

        raise ValueError(
            "No available LLM providers. Configure at least one "
            "(OPENAI_API_KEY, ANTHROPIC_API_KEY, or local Ollama/LMStudio)."
        )

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.0,
    ) -> str:
        """Primary async interface used by all agents. Never returns raw data."""
        provider, model = self._get_active()
        return await provider.chat(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "active_provider": self.active_provider,
            "active_model": self.active_model,
            "available": self.get_available_providers(),
        }
