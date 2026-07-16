"""Transactional-enough provisioning service for the self-service RAPID path."""
from __future__ import annotations

import re
import uuid
from typing import Any

from infrastructure.demo_workspace import get_demo_workspace_store
from infrastructure.organization_profiles import resolve_profile
from infrastructure.tenant_admin_store import get_tenant_admin_store
from infrastructure.tenant_manager import get_tenant_manager
from infrastructure.user_registry import create_tenant_owner


class ProvisioningError(ValueError):
    """A safe error returned by the organization start flow."""


def _tenant_id(company_name: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")[:36] or "organization"
    return f"org-{stem}-{uuid.uuid4().hex[:6]}"


def provision_organization(
    *,
    company_name: str,
    owner_name: str,
    owner_email: str,
    password: str,
    profile_key: str,
    deployment_mode: str | None,
    industry: str = "",
) -> dict[str, Any]:
    if not company_name.strip() or len(company_name.strip()) > 160:
        raise ProvisioningError("Organization name must be between 1 and 160 characters")
    if not owner_name.strip() or len(owner_name.strip()) > 160:
        raise ProvisioningError("Owner name is required")
    if not owner_email or "@" not in owner_email or len(owner_email) > 254:
        raise ProvisioningError("A valid work email is required")
    if len(password) < 8:
        raise ProvisioningError("Password must be at least 8 characters")
    try:
        profile = resolve_profile(profile_key, deployment_mode)
    except ValueError as error:
        raise ProvisioningError(str(error)) from error

    tenant_id = _tenant_id(company_name)
    manager = get_tenant_manager()
    manager.create_tenant(
        tenant_id=tenant_id,
        company_name=company_name.strip(),
        industry=(industry.strip() or profile["name"]),
        plan="trial",
        llm_provider="ollama",
        llm_model="llama3.1:8b",
        industry_pack=profile.get("industry_pack"),
    )
    store = get_tenant_admin_store()
    try:
        operating_profile = store.apply_operating_profile(
            tenant_id,
            profile_key=profile_key,
            deployment_mode=profile["deployment_mode"],
            departments=profile["departments"],
            features=profile["features"],
        )
        owner = create_tenant_owner(
            owner_name=owner_name.strip(), owner_email=owner_email.strip().lower(),
            password=password, tenant_id=tenant_id,
            permitted_departments=operating_profile["departments"],
        )
        get_demo_workspace_store().provision_workspace(
            tenant_id=tenant_id,
            company_name=company_name.strip(),
            industry=(industry.strip() or profile["name"]),
            department_keys=operating_profile["departments"],
        )
    except Exception:
        # We deliberately leave the tenant record for an operator/audit trail.  The
        # generated tenant ID makes a retry safe and avoids attaching to another org.
        raise
    return {"tenant_id": tenant_id, "owner": owner, "operating_profile": operating_profile}
