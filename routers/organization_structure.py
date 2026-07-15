"""Organization hierarchy and membership API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from infrastructure.organization_structure import OrganizationStructureError, get_organization_structure_store
from routers.deps import get_current_user

router = APIRouter(prefix="/organization/structure", tags=["organization-structure"])


def _tenant(user: dict) -> str:
    return str(user.get("tenant_id") or "default")


def _require_admin(user: dict) -> None:
    if user.get("role") not in {"admin", "ceo"}:
        raise HTTPException(status_code=403, detail="Organization administrator role required")


def _raise(error: OrganizationStructureError) -> None:
    raise HTTPException(status_code=404 if "not found" in str(error).lower() else 400, detail=str(error))


class UnitRequest(BaseModel):
    parent_id: str
    name: str = Field(min_length=1, max_length=160)
    unit_type: str
    owner_user_id: str = Field(default="", max_length=160)


class MembershipRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=160)
    title: str = Field(default="", max_length=160)
    manager_user_id: str = Field(default="", max_length=160)


@router.get("")
async def list_structure(current_user: dict = Depends(get_current_user)):
    return {"units": get_organization_structure_store().list_units(_tenant(current_user))}


@router.post("/units", status_code=201)
async def create_unit(body: UnitRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        return {"unit": get_organization_structure_store().create_unit(_tenant(current_user), body.parent_id, body.name, body.unit_type, body.owner_user_id)}
    except OrganizationStructureError as error:
        _raise(error)


@router.post("/units/{unit_id}/members", status_code=201)
async def assign_member(unit_id: str, body: MembershipRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        return {"membership": get_organization_structure_store().assign_member(_tenant(current_user), unit_id, body.user_id, body.title, body.manager_user_id)}
    except OrganizationStructureError as error:
        _raise(error)
