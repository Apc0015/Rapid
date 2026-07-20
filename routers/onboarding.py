"""Self-service organization start flow for the RAPID product portal."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from infrastructure.jwt_manager import get_jwt_manager
from infrastructure.organization_profiles import DEPLOYMENT_POLICIES, catalog
from infrastructure.tenant_provisioning import ProvisioningError, provision_organization

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OrganizationStartRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=160)
    owner_name: str = Field(min_length=1, max_length=160)
    owner_email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    profile_key: str
    deployment_mode: Optional[str] = None
    industry: str = Field(default="", max_length=100)


@router.get("/catalog")
async def onboarding_catalog():
    """Public, non-sensitive profile choices used before authentication."""
    return {
        "profiles": catalog(),
        "deployment_modes": [
            {"key": key, **value} for key, value in DEPLOYMENT_POLICIES.items()
        ],
    }


@router.post("/organizations", status_code=201)
async def start_organization(body: OrganizationStartRequest):
    """Create a trial tenant, its owner account, operating profile, and demo workspace."""
    if os.getenv("RAPID_ENV", "development") == "production" and os.getenv("RAPID_ALLOW_SELF_SERVICE_PROVISIONING", "false").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        result = provision_organization(
            company_name=body.company_name,
            owner_name=body.owner_name,
            owner_email=body.owner_email,
            password=body.password,
            profile_key=body.profile_key,
            deployment_mode=body.deployment_mode,
            industry=body.industry,
        )
    except (ProvisioningError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    owner = result["owner"]
    jwt = get_jwt_manager()
    access_token = jwt.create_access_token(
        user_id=owner["login_key"], role="ceo",
        permitted_departments=owner["permitted_departments"],
        extra={"tenant_id": result["tenant_id"]},
    )
    refresh_token = jwt.create_refresh_token(owner["login_key"])
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in_minutes": 30,
        "user_id": owner["login_key"],
        "name": owner["name"],
        "role": "ceo",
        "tenant_id": result["tenant_id"],
        "permitted_departments": owner["permitted_departments"],
        "operating_profile": result["operating_profile"],
    }
