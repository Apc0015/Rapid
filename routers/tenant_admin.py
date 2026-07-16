"""Tenant administrator configuration API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from infrastructure.tenant_admin_store import TenantAdminError, get_tenant_admin_store
from routers.deps import get_current_user

router = APIRouter(prefix="/tenant-admin", tags=["tenant-admin"])


def _tenant(user: dict) -> str:
    return str(user.get("tenant_id") or "default")


def _require_admin(user: dict) -> None:
    if user.get("role") not in {"admin", "ceo"}:
        raise HTTPException(status_code=403, detail="Organization administrator role required")


def _raise(error: TenantAdminError) -> None:
    raise HTTPException(status_code=400, detail=str(error))


class FeatureRequest(BaseModel): enabled: bool
class ModelRequest(BaseModel):
    enabled: bool
    model_name: str = Field(default="", max_length=160)
    endpoint: str = Field(default="", max_length=500)
    credential_ref: str = Field(default="", max_length=255)
class ConnectionRequest(BaseModel):
    kind: str
    enabled: bool
    label: str = Field(min_length=1, max_length=160)
    configuration: dict[str, Any] = Field(default_factory=dict)
    credential_ref: str = Field(default="", max_length=255)
class InvitationRequest(BaseModel):
    email: str
    name: str
    role: str = "employee"
    departments: list[str] = []
class OperatingProfileRequest(BaseModel):
    profile_key: str
    deployment_mode: str
    departments: list[str] | None = None
    features: list[str] | None = None

@router.get("/configuration")
async def configuration(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return get_tenant_admin_store().configuration(_tenant(current_user))


@router.get("/trust-summary")
async def trust_summary(current_user: dict = Depends(get_current_user)):
    """Expose the active data and approval controls without exposing secrets."""
    _require_admin(current_user)
    return {"trust_summary": get_tenant_admin_store().trust_summary(_tenant(current_user))}


@router.get("/operating-profile")
async def operating_profile(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return {"operating_profile": get_tenant_admin_store().operating_profile(_tenant(current_user))}


@router.put("/operating-profile")
async def update_operating_profile(body: OperatingProfileRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        return {"operating_profile": get_tenant_admin_store().apply_operating_profile(
            _tenant(current_user), profile_key=body.profile_key,
            deployment_mode=body.deployment_mode,
            departments=body.departments, features=body.features,
        )}
    except TenantAdminError as error:
        _raise(error)


@router.get("/features")
async def feature_manifest(current_user: dict = Depends(get_current_user)):
    """Expose product visibility to authenticated users without disclosing tenant configuration."""
    return {"features": get_tenant_admin_store().feature_manifest(_tenant(current_user))}

@router.put("/features/{feature_key}")
async def update_feature(feature_key: str, body: FeatureRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try: return {"feature": get_tenant_admin_store().update_feature(_tenant(current_user), feature_key, body.enabled)}
    except TenantAdminError as error: _raise(error)

@router.put("/models/{provider}")
async def update_model(provider: str, body: ModelRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try: return {"model": get_tenant_admin_store().update_model(_tenant(current_user), provider, body.enabled, body.model_name, body.endpoint, body.credential_ref)}
    except TenantAdminError as error: _raise(error)

@router.put("/connections/{connection_key}")
async def update_connection(connection_key: str, body: ConnectionRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try: return {"connection": get_tenant_admin_store().update_connection(_tenant(current_user), connection_key, body.kind, body.enabled, body.label, body.configuration, body.credential_ref)}
    except TenantAdminError as error: _raise(error)

@router.get("/invitations")
async def invitations(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return {"invitations": get_tenant_admin_store().list_invitations(_tenant(current_user))}

@router.post("/invitations", status_code=201)
async def invite(body: InvitationRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try: return {"invitation": get_tenant_admin_store().invite_user(_tenant(current_user), body.email, body.name, body.role, body.departments)}
    except TenantAdminError as error: _raise(error)
