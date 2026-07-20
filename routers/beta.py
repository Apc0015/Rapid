"""Public beta applications and reviewer-controlled activation."""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from infrastructure.beta_access_store import BetaAccessError, get_beta_access_store
from infrastructure.jwt_manager import get_jwt_manager
from infrastructure.tenant_provisioning import provision_organization
from infrastructure.user_registry import load_users, set_provisioned_password
from routers.deps import get_current_user

router = APIRouter(prefix="/beta", tags=["beta"])


class BetaApplicationRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=160)
    owner_name: str = Field(min_length=1, max_length=160)
    owner_email: str = Field(min_length=3, max_length=254)
    industry: str = Field(default="", max_length=100)
    website: str = Field(default="", max_length=255)
    use_case: str = Field(default="", max_length=1_000)


class ReviewRequest(BaseModel):
    notes: str = Field(default="", max_length=1_000)


class ActivationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=255)
    password: str = Field(min_length=8, max_length=256)


def _reviewer_ids() -> set[str]:
    return {item.strip() for item in os.getenv("RAPID_BETA_REVIEWER_IDS", "").split(",") if item.strip()}


def _is_reviewer(user: dict) -> bool:
    configured = _reviewer_ids()
    if configured:
        return str(user.get("sub") or "") in configured
    return os.getenv("RAPID_ENV", "development") != "production" and user.get("role") in {"admin", "ceo"}


def _require_reviewer(user: dict) -> None:
    if not _is_reviewer(user):
        raise HTTPException(status_code=403, detail="Beta reviewer access required")


def _raise(error: Exception) -> None:
    raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/applications", status_code=202)
async def apply(body: BetaApplicationRequest):
    try:
        return get_beta_access_store().submit(**body.model_dump())
    except BetaAccessError as error:
        _raise(error)


@router.get("/reviewer-status")
async def reviewer_status(current_user: dict = Depends(get_current_user)):
    return {"reviewer": _is_reviewer(current_user)}


@router.get("/applications")
async def applications(current_user: dict = Depends(get_current_user)):
    _require_reviewer(current_user)
    return {"applications": get_beta_access_store().list_applications()}


@router.post("/applications/{application_id}/approve")
async def approve(application_id: str, body: ReviewRequest, current_user: dict = Depends(get_current_user)):
    _require_reviewer(current_user)
    store = get_beta_access_store()
    pending = next((item for item in store.list_applications() if item["id"] == application_id), None)
    if not pending:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        provisioned = provision_organization(
            company_name=pending["company_name"], owner_name=pending["owner_name"], owner_email=pending["owner_email"],
            password=secrets.token_urlsafe(32), industry=pending.get("industry") or "", profile_key="startup", deployment_mode="cloud",
        )
        application, token = store.approve(
            application_id, tenant_id=provisioned["tenant_id"], owner_login_key=provisioned["owner"]["login_key"], reviewer_notes=body.notes,
        )
        base_url = os.getenv("RAPID_PORTAL_URL", "http://127.0.0.1:4173").rstrip("/")
        return {"application": application, "activation_url": f"{base_url}/activate?token={token}"}
    except (BetaAccessError, ValueError) as error:
        _raise(error)


@router.post("/applications/{application_id}/decline")
async def decline(application_id: str, body: ReviewRequest, current_user: dict = Depends(get_current_user)):
    _require_reviewer(current_user)
    try:
        return {"application": get_beta_access_store().reject(application_id, body.notes)}
    except BetaAccessError as error:
        _raise(error)


@router.post("/activate")
async def activate(body: ActivationRequest):
    try:
        application = get_beta_access_store().redeem_activation(body.token)
        set_provisioned_password(application["owner_login_key"], body.password)
        user = load_users().get(application["owner_login_key"])
        if not user:
            raise BetaAccessError("Approved account is unavailable")
        get_beta_access_store().mark_activated(application["id"])
        manager = get_jwt_manager()
        return {
            "access_token": manager.create_access_token(user_id=application["owner_login_key"], role="ceo", permitted_departments=user.get("permitted_departments", []), extra={"tenant_id": application["tenant_id"]}),
            "refresh_token": manager.create_refresh_token(application["owner_login_key"]),
            "token_type": "bearer", "expires_in_minutes": 30,
            "user_id": application["owner_login_key"], "name": user.get("name", ""), "role": "ceo",
            "tenant_id": application["tenant_id"], "permitted_departments": user.get("permitted_departments", []),
        }
    except (BetaAccessError, ValueError) as error:
        _raise(error)
