"""Configuration-driven operating profiles for a RAPID tenant.

Profiles are starting points, not product editions.  Every tenant receives the
same governed core; a profile selects the initial departments, modules, and AI
data-residency policy.  Administrators can refine these choices after launch.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


ALL_DEPARTMENTS = (
    "hr", "finance", "legal", "sales", "marketing", "ops", "it",
    "procurement", "rd", "customer_success",
)
ALL_FEATURES = (
    "meetings", "workflows", "knowledge", "automations", "integrations",
    "reports", "projects", "people", "crm", "tickets",
)


def _profile(
    name: str,
    description: str,
    departments: tuple[str, ...],
    features: tuple[str, ...],
    *,
    industry_pack: str | None = None,
    default_deployment: str = "cloud",
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "departments": list(departments),
        "features": list(features),
        "industry_pack": industry_pack,
        "default_deployment": default_deployment,
    }


PROFILE_CATALOG: dict[str, dict[str, Any]] = {
    "solo_business": _profile(
        "Solo business", "A focused operating team for an owner-led business.",
        ("sales", "marketing", "ops", "finance", "customer_success"),
        ("meetings", "workflows", "knowledge", "reports", "crm", "tickets"),
    ),
    "startup": _profile(
        "Startup operating workspace", "A practical operating system for product, growth, customer, and delivery work.",
        ("sales", "marketing", "rd", "it", "ops", "finance", "customer_success"),
        ("meetings", "workflows", "knowledge", "automations", "integrations", "reports", "projects", "people", "crm", "tickets"),
        industry_pack="tech_saas",
    ),
    "service_business": _profile(
        "Service business", "Client delivery, pipeline, staffing, and financial control.",
        ("sales", "marketing", "ops", "finance", "hr", "customer_success"),
        ("meetings", "workflows", "knowledge", "automations", "reports", "projects", "people", "crm", "tickets"),
    ),
    "commerce": _profile(
        "Commerce", "Commercial operations, supply coordination, service, and financial visibility.",
        ("sales", "marketing", "ops", "procurement", "finance", "customer_success"),
        ("meetings", "workflows", "knowledge", "automations", "integrations", "reports", "projects", "crm", "tickets"),
    ),
    "established_organization": _profile(
        "Established organization", "A cross-functional workspace for teams with established operating rhythms.",
        ALL_DEPARTMENTS, ALL_FEATURES,
    ),
    "regulated": _profile(
        "Regulated organization", "Governed operations with local or private AI deployment by default.",
        ("hr", "finance", "legal", "ops", "it", "procurement", "customer_success", "rd"),
        ("meetings", "workflows", "knowledge", "automations", "integrations", "reports", "projects", "people", "tickets"),
        industry_pack="healthcare",
        default_deployment="private",
    ),
}

DEPLOYMENT_POLICIES: dict[str, dict[str, Any]] = {
    "cloud": {
        "name": "Managed cloud AI",
        "description": "Use approved hosted models after a secret-manager reference is configured.",
        "data_residency": "customer-approved cloud region",
        "allowed_providers": ["ollama", "openrouter"],
        "cloud_egress": "allowed",
    },
    "private": {
        "name": "Private AI environment",
        "description": "Run inference and retrieval inside a customer-controlled private environment.",
        "data_residency": "customer private environment",
        "allowed_providers": ["ollama"],
        "cloud_egress": "blocked",
    },
    "on_prem": {
        "name": "Customer-managed / on-prem AI",
        "description": "Keep documents, embeddings, retrieval, logs, and inference inside the customer network.",
        "data_residency": "customer-managed environment",
        "allowed_providers": ["ollama"],
        "cloud_egress": "blocked",
    },
    "hybrid": {
        "name": "Hybrid AI",
        "description": "Keep sensitive workloads local and route only approved, classified work to cloud models.",
        "data_residency": "policy-controlled by data classification",
        "allowed_providers": ["ollama", "openrouter"],
        "cloud_egress": "approved workloads only",
    },
}


def catalog() -> list[dict[str, Any]]:
    return [
        {"key": key, **deepcopy(value)}
        for key, value in PROFILE_CATALOG.items()
    ]


def resolve_profile(profile_key: str, deployment_mode: str | None = None) -> dict[str, Any]:
    if profile_key not in PROFILE_CATALOG:
        raise ValueError("Unknown organization profile")
    profile = deepcopy(PROFILE_CATALOG[profile_key])
    mode = deployment_mode or profile["default_deployment"]
    if mode not in DEPLOYMENT_POLICIES:
        raise ValueError("Unknown AI deployment mode")
    return {
        "profile_key": profile_key,
        **profile,
        "deployment_mode": mode,
        "deployment_policy": deepcopy(DEPLOYMENT_POLICIES[mode]),
    }


def validate_departments(values: list[str]) -> list[str]:
    unique = list(dict.fromkeys(value.strip() for value in values if value and value.strip()))
    if not unique or any(value not in ALL_DEPARTMENTS for value in unique):
        raise ValueError("Select one or more supported departments")
    return unique


def validate_features(values: list[str]) -> list[str]:
    unique = list(dict.fromkeys(value.strip() for value in values if value and value.strip()))
    if any(value not in ALL_FEATURES for value in unique):
        raise ValueError("Unsupported product module")
    return unique
