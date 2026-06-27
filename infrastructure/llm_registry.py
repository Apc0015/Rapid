"""
infrastructure/llm_registry.py — LLM Provider & Model Registry.

Catalogs every supported LLM provider and their available models with:
  - context window size
  - cost tier (free / low / medium / high)
  - capabilities (chat, json_mode, vision, streaming, function_calling)
  - required config keys
  - API style (anthropic_messages / openai_chat / ollama_chat)

Used by:
  - LLMAdapter (infrastructure/llm_adapter.py) to route per-tenant calls
  - Tenant config API (routers/llm.py) to validate and document choices
  - Admin UI model picker

Supported providers
───────────────────
  anthropic    — Claude models via Anthropic Messages API
  openai       — GPT models via OpenAI Chat Completions
  openrouter   — Any model via OpenRouter proxy (OpenAI-compatible)
  azure        — Azure OpenAI deployments (OpenAI-compatible)
  google       — Gemini models via Google AI Studio
  ollama       — Local models via Ollama (OpenAI-compatible)
  siliconflow  — Qwen / DeepSeek via SiliconFlow (OpenAI-compatible, free tier)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Cost tier labels ──────────────────────────────────────────────────────────

class CostTier:
    FREE   = "free"       # No API cost (local or free-tier)
    LOW    = "low"        # < $1 / M tokens
    MEDIUM = "medium"     # $1–$10 / M tokens
    HIGH   = "high"       # > $10 / M tokens


# ── API call style ────────────────────────────────────────────────────────────

class APIStyle:
    ANTHROPIC_MESSAGES = "anthropic_messages"   # POST /v1/messages
    OPENAI_CHAT        = "openai_chat"           # POST /v1/chat/completions
    GOOGLE_GENERATE    = "google_generate"       # POST /v1beta/models/{model}:generateContent


# ── Model descriptor ──────────────────────────────────────────────────────────

@dataclass
class ModelSpec:
    """
    Full descriptor for a single LLM model.

    model_id          — Exact string sent to the API (e.g. "claude-3-5-haiku-20241022")
    display_name      — Human-friendly name ("Claude 3.5 Haiku")
    provider          — Parent provider ID ("anthropic")
    api_style         — Which HTTP call pattern to use
    context_window    — Max context tokens
    max_output_tokens — Max generation tokens
    cost_tier         — Cost bucket
    capabilities      — Set of strings: "chat", "json_mode", "vision", "streaming", "function_calling"
    is_fast           — True if this is the recommended fast/cheap model for a provider
    is_strong         — True if this is the recommended strong/expensive model for a provider
    notes             — Optional documentation blurb
    """
    model_id:          str
    display_name:      str
    provider:          str
    api_style:         str
    context_window:    int
    max_output_tokens: int
    cost_tier:         str
    capabilities:      set[str]           = field(default_factory=set)
    is_fast:           bool               = False
    is_strong:         bool               = False
    notes:             str                = ""

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def to_dict(self) -> dict:
        return {
            "model_id":          self.model_id,
            "display_name":      self.display_name,
            "provider":          self.provider,
            "api_style":         self.api_style,
            "context_window":    self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "cost_tier":         self.cost_tier,
            "capabilities":      sorted(self.capabilities),
            "is_fast":           self.is_fast,
            "is_strong":         self.is_strong,
            "notes":             self.notes,
        }


# ── Provider descriptor ───────────────────────────────────────────────────────

@dataclass
class ProviderSpec:
    """
    Descriptor for an LLM provider.

    provider_id       — Short key used in tenant config ("anthropic")
    display_name      — Human-readable name
    api_style         — Default API style for this provider
    base_url          — Default API base URL (overridable per-tenant)
    required_keys     — Config keys the tenant must supply (e.g. ["api_key"])
    optional_keys     — Config keys that override defaults (e.g. ["base_url", "model"])
    models            — Dict[model_id → ModelSpec] for all known models
    notes             — Usage notes or caveats
    """
    provider_id:   str
    display_name:  str
    api_style:     str
    base_url:      str
    required_keys: list[str]
    optional_keys: list[str]                    = field(default_factory=list)
    models:        dict[str, ModelSpec]         = field(default_factory=dict)
    notes:         str                          = ""

    @property
    def fast_model(self) -> Optional[ModelSpec]:
        return next((m for m in self.models.values() if m.is_fast), None)

    @property
    def strong_model(self) -> Optional[ModelSpec]:
        return next((m for m in self.models.values() if m.is_strong), None)

    def to_dict(self) -> dict:
        fm = self.fast_model
        sm = self.strong_model
        return {
            "provider_id":    self.provider_id,
            "display_name":   self.display_name,
            "api_style":      self.api_style,
            "base_url":       self.base_url,
            "required_keys":  self.required_keys,
            "optional_keys":  self.optional_keys,
            "fast_model":     fm.model_id if fm else None,
            "strong_model":   sm.model_id if sm else None,
            "model_count":    len(self.models),
            "notes":          self.notes,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Provider & Model Definitions
# ─────────────────────────────────────────────────────────────────────────────

_CHAT_JSON_STREAM  = {"chat", "json_mode", "streaming"}
_FULL_CAPS         = {"chat", "json_mode", "streaming", "function_calling"}
_VISION_FULL       = {"chat", "json_mode", "streaming", "function_calling", "vision"}


# ── Anthropic ─────────────────────────────────────────────────────────────────

_ANTHROPIC_MODELS: dict[str, ModelSpec] = {
    "claude-3-5-haiku-20241022": ModelSpec(
        model_id          = "claude-3-5-haiku-20241022",
        display_name      = "Claude 3.5 Haiku",
        provider          = "anthropic",
        api_style         = APIStyle.ANTHROPIC_MESSAGES,
        context_window    = 200_000,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.LOW,
        capabilities      = _VISION_FULL,
        is_fast           = True,
        notes             = "Best speed/cost ratio. Ideal for routing, classification, summaries.",
    ),
    "claude-3-5-sonnet-20241022": ModelSpec(
        model_id          = "claude-3-5-sonnet-20241022",
        display_name      = "Claude 3.5 Sonnet",
        provider          = "anthropic",
        api_style         = APIStyle.ANTHROPIC_MESSAGES,
        context_window    = 200_000,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.MEDIUM,
        capabilities      = _VISION_FULL,
        is_strong         = True,
        notes             = "State-of-the-art reasoning. Use for complex analysis and planning.",
    ),
    "claude-opus-4-6": ModelSpec(
        model_id          = "claude-opus-4-6",
        display_name      = "Claude Opus 4",
        provider          = "anthropic",
        api_style         = APIStyle.ANTHROPIC_MESSAGES,
        context_window    = 200_000,
        max_output_tokens = 32_000,
        cost_tier         = CostTier.HIGH,
        capabilities      = _VISION_FULL,
        notes             = "Anthropic's most powerful model. Use for highest-stakes tasks.",
    ),
}

ANTHROPIC = ProviderSpec(
    provider_id   = "anthropic",
    display_name  = "Anthropic Claude",
    api_style     = APIStyle.ANTHROPIC_MESSAGES,
    base_url      = "https://api.anthropic.com",
    required_keys = ["api_key"],
    optional_keys = ["base_url", "fast_model", "strong_model"],
    models        = _ANTHROPIC_MODELS,
    notes         = "Direct Anthropic API. Requires ANTHROPIC_API_KEY or tenant-level api_key.",
)


# ── OpenAI ────────────────────────────────────────────────────────────────────

_OPENAI_MODELS: dict[str, ModelSpec] = {
    "gpt-4o-mini": ModelSpec(
        model_id          = "gpt-4o-mini",
        display_name      = "GPT-4o Mini",
        provider          = "openai",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 16_384,
        cost_tier         = CostTier.LOW,
        capabilities      = _VISION_FULL,
        is_fast           = True,
        notes             = "Fast, cheap GPT-4o variant. Good for high-volume tasks.",
    ),
    "gpt-4o": ModelSpec(
        model_id          = "gpt-4o",
        display_name      = "GPT-4o",
        provider          = "openai",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 16_384,
        cost_tier         = CostTier.MEDIUM,
        capabilities      = _VISION_FULL,
        is_strong         = True,
        notes             = "OpenAI's flagship multimodal model.",
    ),
    "o1-mini": ModelSpec(
        model_id          = "o1-mini",
        display_name      = "OpenAI o1-mini",
        provider          = "openai",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 65_536,
        cost_tier         = CostTier.MEDIUM,
        capabilities      = {"chat", "streaming"},
        notes             = "Reasoning model — slower but excellent for math/logic tasks.",
    ),
}

OPENAI = ProviderSpec(
    provider_id   = "openai",
    display_name  = "OpenAI",
    api_style     = APIStyle.OPENAI_CHAT,
    base_url      = "https://api.openai.com/v1",
    required_keys = ["api_key"],
    optional_keys = ["base_url", "fast_model", "strong_model", "organization"],
    models        = _OPENAI_MODELS,
    notes         = "OpenAI Chat Completions API.",
)


# ── OpenRouter ────────────────────────────────────────────────────────────────

_OPENROUTER_MODELS: dict[str, ModelSpec] = {
    "openai/gpt-4o": ModelSpec(
        model_id          = "openai/gpt-4o",
        display_name      = "GPT-4o (via OpenRouter)",
        provider          = "openrouter",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 16_384,
        cost_tier         = CostTier.MEDIUM,
        capabilities      = _VISION_FULL,
        is_strong         = True,
    ),
    "openai/gpt-4o-mini": ModelSpec(
        model_id          = "openai/gpt-4o-mini",
        display_name      = "GPT-4o Mini (via OpenRouter)",
        provider          = "openrouter",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 16_384,
        cost_tier         = CostTier.LOW,
        capabilities      = _VISION_FULL,
        is_fast           = True,
    ),
    "anthropic/claude-3-5-sonnet": ModelSpec(
        model_id          = "anthropic/claude-3-5-sonnet",
        display_name      = "Claude 3.5 Sonnet (via OpenRouter)",
        provider          = "openrouter",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 200_000,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.MEDIUM,
        capabilities      = _VISION_FULL,
    ),
    "google/gemini-flash-1.5": ModelSpec(
        model_id          = "google/gemini-flash-1.5",
        display_name      = "Gemini 1.5 Flash (via OpenRouter)",
        provider          = "openrouter",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 1_000_000,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.LOW,
        capabilities      = _VISION_FULL,
    ),
    "meta-llama/llama-3.1-8b-instruct:free": ModelSpec(
        model_id          = "meta-llama/llama-3.1-8b-instruct:free",
        display_name      = "Llama 3.1 8B Instruct Free (via OpenRouter)",
        provider          = "openrouter",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 131_072,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.FREE,
        capabilities      = _CHAT_JSON_STREAM,
    ),
}

OPENROUTER = ProviderSpec(
    provider_id   = "openrouter",
    display_name  = "OpenRouter",
    api_style     = APIStyle.OPENAI_CHAT,
    base_url      = "https://openrouter.ai/api/v1",
    required_keys = ["api_key"],
    optional_keys = ["base_url", "fast_model", "strong_model", "site_url", "site_name"],
    models        = _OPENROUTER_MODELS,
    notes         = "OpenRouter proxy — access 200+ models with one API key.",
)


# ── Azure OpenAI ──────────────────────────────────────────────────────────────

_AZURE_MODELS: dict[str, ModelSpec] = {
    "gpt-4o": ModelSpec(
        model_id          = "gpt-4o",
        display_name      = "GPT-4o (Azure deployment)",
        provider          = "azure",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 16_384,
        cost_tier         = CostTier.MEDIUM,
        capabilities      = _VISION_FULL,
        is_strong         = True,
    ),
    "gpt-4o-mini": ModelSpec(
        model_id          = "gpt-4o-mini",
        display_name      = "GPT-4o Mini (Azure deployment)",
        provider          = "azure",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 16_384,
        cost_tier         = CostTier.LOW,
        capabilities      = _VISION_FULL,
        is_fast           = True,
    ),
}

AZURE = ProviderSpec(
    provider_id   = "azure",
    display_name  = "Azure OpenAI",
    api_style     = APIStyle.OPENAI_CHAT,
    base_url      = "https://{resource_name}.openai.azure.com/openai/deployments/{deployment_name}",
    required_keys = ["api_key", "endpoint", "deployment_name"],
    optional_keys = ["api_version", "fast_model", "strong_model"],
    models        = _AZURE_MODELS,
    notes         = (
        "Azure OpenAI uses deployment names instead of model IDs. "
        "Set 'endpoint' to your Azure resource URL and 'deployment_name' to the deployment."
    ),
)


# ── Google AI / Gemini ────────────────────────────────────────────────────────

_GOOGLE_MODELS: dict[str, ModelSpec] = {
    "gemini-1.5-flash": ModelSpec(
        model_id          = "gemini-1.5-flash",
        display_name      = "Gemini 1.5 Flash",
        provider          = "google",
        api_style         = APIStyle.GOOGLE_GENERATE,
        context_window    = 1_000_000,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.LOW,
        capabilities      = _VISION_FULL,
        is_fast           = True,
        notes             = "Very fast, 1M context. Great for long document analysis.",
    ),
    "gemini-1.5-pro": ModelSpec(
        model_id          = "gemini-1.5-pro",
        display_name      = "Gemini 1.5 Pro",
        provider          = "google",
        api_style         = APIStyle.GOOGLE_GENERATE,
        context_window    = 2_000_000,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.MEDIUM,
        capabilities      = _VISION_FULL,
        is_strong         = True,
        notes             = "2M context window. Best for very long document analysis.",
    ),
    "gemini-2.0-flash-exp": ModelSpec(
        model_id          = "gemini-2.0-flash-exp",
        display_name      = "Gemini 2.0 Flash Experimental",
        provider          = "google",
        api_style         = APIStyle.GOOGLE_GENERATE,
        context_window    = 1_000_000,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.LOW,
        capabilities      = _VISION_FULL,
        notes             = "Latest Gemini — experimental. May not be stable for production.",
    ),
}

GOOGLE = ProviderSpec(
    provider_id   = "google",
    display_name  = "Google AI (Gemini)",
    api_style     = APIStyle.GOOGLE_GENERATE,
    base_url      = "https://generativelanguage.googleapis.com/v1beta",
    required_keys = ["api_key"],
    optional_keys = ["base_url", "fast_model", "strong_model"],
    models        = _GOOGLE_MODELS,
    notes         = "Google AI Studio API. Requires GOOGLE_API_KEY.",
)


# ── Ollama (local) ────────────────────────────────────────────────────────────

_OLLAMA_MODELS: dict[str, ModelSpec] = {
    "llama3.2": ModelSpec(
        model_id          = "llama3.2",
        display_name      = "Llama 3.2 (3B)",
        provider          = "ollama",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 4_096,
        cost_tier         = CostTier.FREE,
        capabilities      = _CHAT_JSON_STREAM,
        is_fast           = True,
        notes             = "Small, fast local model. Good for dev/testing.",
    ),
    "llama3.1": ModelSpec(
        model_id          = "llama3.1",
        display_name      = "Llama 3.1 (8B)",
        provider          = "ollama",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 131_072,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.FREE,
        capabilities      = _CHAT_JSON_STREAM,
        is_strong         = True,
        notes             = "Solid 8B local model. Best Ollama default for production-like use.",
    ),
    "mistral": ModelSpec(
        model_id          = "mistral",
        display_name      = "Mistral 7B",
        provider          = "ollama",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 32_768,
        max_output_tokens = 4_096,
        cost_tier         = CostTier.FREE,
        capabilities      = _CHAT_JSON_STREAM,
    ),
    "qwen2.5": ModelSpec(
        model_id          = "qwen2.5",
        display_name      = "Qwen 2.5 (7B)",
        provider          = "ollama",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 128_000,
        max_output_tokens = 8_192,
        cost_tier         = CostTier.FREE,
        capabilities      = _CHAT_JSON_STREAM,
        notes             = "Strong multilingual model, good for non-English tenants.",
    ),
    # Sentinel entry: "any" means Ollama will use whatever model_id is configured
    "__custom__": ModelSpec(
        model_id          = "__custom__",
        display_name      = "Custom Ollama model",
        provider          = "ollama",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 32_768,
        max_output_tokens = 4_096,
        cost_tier         = CostTier.FREE,
        capabilities      = {"chat", "streaming"},
        notes             = "Any locally-pulled Ollama model. Set model_id in tenant config.",
    ),
}

OLLAMA = ProviderSpec(
    provider_id   = "ollama",
    display_name  = "Ollama (Local)",
    api_style     = APIStyle.OPENAI_CHAT,
    base_url      = "http://localhost:11434",
    required_keys = [],
    optional_keys = ["base_url", "model"],
    models        = _OLLAMA_MODELS,
    notes         = "No API key needed. Requires Ollama running locally or on a reachable host.",
)


# ── SiliconFlow ───────────────────────────────────────────────────────────────

_SILICONFLOW_MODELS: dict[str, ModelSpec] = {
    "Qwen/Qwen2.5-7B-Instruct": ModelSpec(
        model_id          = "Qwen/Qwen2.5-7B-Instruct",
        display_name      = "Qwen 2.5 7B Instruct",
        provider          = "siliconflow",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 131_072,
        max_output_tokens = 4_096,
        cost_tier         = CostTier.FREE,
        capabilities      = _CHAT_JSON_STREAM,
        is_fast           = True,
        notes             = "Free tier fast model. Good for high-volume tasks.",
    ),
    "Qwen/Qwen2.5-72B-Instruct": ModelSpec(
        model_id          = "Qwen/Qwen2.5-72B-Instruct",
        display_name      = "Qwen 2.5 72B Instruct",
        provider          = "siliconflow",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 131_072,
        max_output_tokens = 4_096,
        cost_tier         = CostTier.LOW,
        capabilities      = _CHAT_JSON_STREAM,
        is_strong         = True,
        notes             = "Powerful open-weight model via SiliconFlow's free/low-cost tier.",
    ),
    "deepseek-ai/DeepSeek-V2.5": ModelSpec(
        model_id          = "deepseek-ai/DeepSeek-V2.5",
        display_name      = "DeepSeek V2.5",
        provider          = "siliconflow",
        api_style         = APIStyle.OPENAI_CHAT,
        context_window    = 32_768,
        max_output_tokens = 4_096,
        cost_tier         = CostTier.FREE,
        capabilities      = _CHAT_JSON_STREAM,
        notes             = "Strong coding and reasoning model, free tier.",
    ),
}

SILICONFLOW = ProviderSpec(
    provider_id   = "siliconflow",
    display_name  = "SiliconFlow",
    api_style     = APIStyle.OPENAI_CHAT,
    base_url      = "https://api.siliconflow.cn/v1",
    required_keys = ["api_key"],
    optional_keys = ["base_url", "fast_model", "strong_model"],
    models        = _SILICONFLOW_MODELS,
    notes         = "OpenAI-compatible. Free tier for Qwen/DeepSeek models.",
)


# ─────────────────────────────────────────────────────────────────────────────
# Registry — single source of truth
# ─────────────────────────────────────────────────────────────────────────────

PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
    "anthropic":   ANTHROPIC,
    "openai":      OPENAI,
    "openrouter":  OPENROUTER,
    "azure":       AZURE,
    "google":      GOOGLE,
    "ollama":      OLLAMA,
    "siliconflow": SILICONFLOW,
}

# Flat model lookup: model_id → ModelSpec (across all providers)
_FLAT_MODEL_INDEX: dict[str, ModelSpec] = {}
for _p in PROVIDER_REGISTRY.values():
    for _m in _p.models.values():
        _FLAT_MODEL_INDEX[_m.model_id] = _m


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_provider(provider_id: str) -> Optional[ProviderSpec]:
    """Return provider spec or None if unknown."""
    return PROVIDER_REGISTRY.get(provider_id)


def get_model(provider_id: str, model_id: str) -> Optional[ModelSpec]:
    """Return model spec for a given provider+model pair. None if not in catalog."""
    provider = PROVIDER_REGISTRY.get(provider_id)
    if not provider:
        return None
    # Exact match in catalog
    if model_id in provider.models:
        return provider.models[model_id]
    # Ollama / Azure: allow custom model IDs not in the catalog
    if provider_id in ("ollama", "azure", "openrouter"):
        # Return the __custom__ sentinel for Ollama, or a synthesised spec for others
        if provider_id == "ollama":
            return provider.models.get("__custom__")
        # For OpenRouter/Azure, build a minimal spec on-the-fly
        return ModelSpec(
            model_id          = model_id,
            display_name      = model_id,
            provider          = provider_id,
            api_style         = provider.api_style,
            context_window    = 32_768,
            max_output_tokens = 4_096,
            cost_tier         = CostTier.MEDIUM,
            capabilities      = {"chat", "streaming"},
            notes             = "Custom / unregistered model.",
        )
    return None


def list_providers() -> list[dict]:
    """Return serialised list of all providers (for API response)."""
    return [p.to_dict() for p in PROVIDER_REGISTRY.values()]


def list_models(provider_id: Optional[str] = None) -> list[dict]:
    """
    Return serialised list of known models.
    If provider_id is given, scoped to that provider only.
    """
    if provider_id:
        provider = PROVIDER_REGISTRY.get(provider_id)
        if not provider:
            return []
        return [m.to_dict() for m in provider.models.values() if m.model_id != "__custom__"]
    return [m.to_dict() for m in _FLAT_MODEL_INDEX.values() if m.model_id != "__custom__"]


def validate_tenant_llm_config(provider_id: str, model_id: str, llm_config: dict) -> list[str]:
    """
    Validate a tenant's LLM configuration against the registry.
    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []

    provider = PROVIDER_REGISTRY.get(provider_id)
    if not provider:
        errors.append(f"Unknown provider '{provider_id}'. "
                      f"Valid: {', '.join(PROVIDER_REGISTRY.keys())}")
        return errors  # no point continuing

    # Check required config keys
    for key in provider.required_keys:
        if key not in llm_config or not llm_config[key]:
            errors.append(f"Provider '{provider_id}' requires config key '{key}'")

    # Warn about unknown config keys (non-fatal, just informational)
    all_known_keys = set(provider.required_keys) | set(provider.optional_keys)
    unknown = set(llm_config.keys()) - all_known_keys
    if unknown:
        # Not an error — allow pass-through; just note it
        pass

    # Model validation — skip for Ollama/OpenRouter (open-ended)
    if provider_id not in ("ollama", "openrouter", "azure"):
        if model_id not in provider.models:
            known = ", ".join(provider.models.keys())
            errors.append(f"Model '{model_id}' not in catalog for '{provider_id}'. Known: {known}")

    return errors


def get_recommended_config(provider_id: str, use_strong: bool = False) -> dict:
    """
    Return a recommended tenant LLM config skeleton for a provider.
    Useful for onboarding / admin UI defaults.
    """
    provider = PROVIDER_REGISTRY.get(provider_id)
    if not provider:
        return {}

    model = provider.strong_model if use_strong else provider.fast_model
    model_id = model.model_id if model else ""
    # Strip the __custom__ sentinel
    if model_id == "__custom__":
        model_id = "llama3.1"

    skeleton: dict = {k: "" for k in provider.required_keys}
    skeleton["model"] = model_id
    return skeleton
