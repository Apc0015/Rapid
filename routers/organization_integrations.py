"""Organization integration registry and event-trigger API."""
from __future__ import annotations

from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from infrastructure.integration_hub import IntegrationHubError, get_integration_hub
from infrastructure.secret_vault import SecretVaultError, get_secret_vault
from infrastructure.people_ops_store import DEPARTMENTS, PLAYBOOKS, PRIVILEGED_ROLES
from routers.deps import get_current_user

router = APIRouter(prefix="/organization/integrations", tags=["organization-integrations"])


def _tenant(user: dict) -> str:
    return str(user.get("tenant_id") or "default")


def _allowed_departments(user: dict) -> set[str]:
    return set(DEPARTMENTS) if user.get("role") in {"admin", "ceo"} else set(user.get("depts") or []) & set(DEPARTMENTS)


def _require_department(user: dict, department: str) -> None:
    if department not in _allowed_departments(user):
        raise HTTPException(status_code=403, detail="You do not have access to this department")


def _require_operator(user: dict) -> None:
    if user.get("role") not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="Department operator role required")


def _raise(error: IntegrationHubError) -> None:
    raise HTTPException(status_code=404 if "not found" in str(error).lower() else 400, detail=str(error))


class ConnectionRequest(BaseModel):
    department: str
    provider: str
    label: str = Field(min_length=1, max_length=160)
    auth_mode: str
    credential_ref: str = Field(default="", max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)


class TriggerRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=100)
    playbook_key: str
    subject_name: str = Field(min_length=1, max_length=160)
    subject_email: str = Field(default="", max_length=254)
    payload: dict[str, Any] = Field(default_factory=dict)


class ScheduleRequest(BaseModel):
    connection_id: str
    playbook_key: str
    subject_name: str = Field(min_length=1, max_length=160)
    subject_email: str = Field(default="", max_length=254)
    payload: dict[str, Any] = Field(default_factory=dict)
    interval_minutes: int = Field(ge=5, le=43_200)


class ScheduleEnabledRequest(BaseModel):
    enabled: bool


def _connection_with_access(connection_id: str, user: dict) -> dict:
    try:
        connection = get_integration_hub().get_connection(_tenant(user), connection_id)
    except IntegrationHubError as error:
        _raise(error)
    _require_department(user, connection["department"])
    return connection


@router.get("/catalog")
async def catalog(current_user: dict = Depends(get_current_user)):
    return {"providers": get_integration_hub().list_catalog()}


@router.get("/connections")
async def connections(department: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if department:
        _require_department(current_user, department)
    allowed = _allowed_departments(current_user)
    return {"connections": [item for item in get_integration_hub().list_connections(_tenant(current_user), department) if item["department"] in allowed]}


@router.post("/connections", status_code=201)
async def create_connection(body: ConnectionRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _require_department(current_user, body.department)
    try:
        return {"connection": get_integration_hub().register_connection(_tenant(current_user), body.department, body.provider, body.label, body.auth_mode, body.credential_ref, body.config, current_user["sub"])}
    except IntegrationHubError as error:
        _raise(error)


@router.post("/connections/{connection_id}/test")
async def test_connection(connection_id: str, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _connection_with_access(connection_id, current_user)
    try:
        return get_integration_hub().test_connection(_tenant(current_user), connection_id)
    except IntegrationHubError as error:
        _raise(error)


@router.post("/connections/{connection_id}/oauth/start")
async def start_oauth(connection_id: str, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    _connection_with_access(connection_id, current_user)
    try:
        return get_integration_hub().create_oauth_authorization(_tenant(current_user), connection_id)
    except IntegrationHubError as error:
        _raise(error)


@router.get("/oauth/callback")
async def oauth_callback(state: str, code: str):
    hub = get_integration_hub()
    try:
        state_record = hub.consume_oauth_state(state)
        exchange = hub.oauth_exchange_config(state_record)
        client_secret = get_secret_vault().resolve(exchange["client_secret_ref"], exchange["tenant_id"])
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.post(exchange["token_url"], data={
                "grant_type": "authorization_code", "code": code, "client_id": exchange["client_id"],
                "client_secret": client_secret, "redirect_uri": exchange["redirect_uri"], "code_verifier": exchange["code_verifier"],
            })
        if response.status_code >= 400:
            raise IntegrationHubError("OAuth provider rejected the authorization code")
        token_data = response.json()
        if not token_data.get("access_token"):
            raise IntegrationHubError("OAuth provider returned no access token")
        token_reference = get_secret_vault().put(
            exchange["tenant_id"], f"oauth/{exchange['connection_id']}",
            __import__("json").dumps(token_data, default=str),
        )
        connection = hub.mark_oauth_connected(exchange["tenant_id"], exchange["connection_id"], token_reference)
        return {"connected": True, "connection": connection}
    except (IntegrationHubError, SecretVaultError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/connections/{connection_id}/events")
async def trigger_event(connection_id: str, body: TriggerRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    connection = _connection_with_access(connection_id, current_user)
    playbook = PLAYBOOKS.get(body.playbook_key)
    if not playbook or playbook["department"] != connection["department"]:
        raise HTTPException(status_code=400, detail="The selected playbook does not belong to this connection's department")
    try:
        return get_integration_hub().trigger_event(_tenant(current_user), connection_id, body.idempotency_key, body.event_type, body.playbook_key, body.subject_name, body.subject_email, body.payload, current_user["sub"])
    except IntegrationHubError as error:
        _raise(error)


@router.post("/webhooks/{connection_id}", status_code=202)
async def receive_webhook(
    connection_id: str,
    request: Request,
    x_rapid_signature: str = Header(default=""),
    x_rapid_timestamp: str = Header(default=""),
    x_idempotency_key: str = Header(default=""),
):
    body = await request.body()
    try:
        return get_integration_hub().receive_webhook(
            connection_id, body, x_rapid_signature, x_rapid_timestamp, x_idempotency_key,
        )
    except IntegrationHubError as error:
        message = str(error)
        status = 401 if "signature" in message.lower() or "secret" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from error


@router.get("/schedules")
async def schedules(department: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if department:
        _require_department(current_user, department)
    allowed = _allowed_departments(current_user)
    return {"schedules": [item for item in get_integration_hub().list_schedules(_tenant(current_user), department) if item["department"] in allowed]}


@router.post("/schedules", status_code=201)
async def create_schedule(body: ScheduleRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    connection = _connection_with_access(body.connection_id, current_user)
    playbook = PLAYBOOKS.get(body.playbook_key)
    if not playbook or playbook["department"] != connection["department"]:
        raise HTTPException(status_code=400, detail="The selected playbook does not belong to this connection's department")
    try:
        return {"schedule": get_integration_hub().create_schedule(
            _tenant(current_user), body.connection_id, body.playbook_key, body.subject_name, body.subject_email,
            body.payload, body.interval_minutes, current_user["sub"],
        )}
    except IntegrationHubError as error:
        _raise(error)


@router.post("/schedules/{schedule_id}/enabled")
async def set_schedule_enabled(schedule_id: str, body: ScheduleEnabledRequest, current_user: dict = Depends(get_current_user)):
    _require_operator(current_user)
    try:
        schedule = get_integration_hub().get_schedule(_tenant(current_user), schedule_id)
        _require_department(current_user, schedule["department"])
        return {"schedule": get_integration_hub().set_schedule_enabled(_tenant(current_user), schedule_id, body.enabled)}
    except IntegrationHubError as error:
        _raise(error)


@router.post("/schedules/dispatch")
async def dispatch_schedules(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in {"admin", "ceo"}:
        raise HTTPException(status_code=403, detail="Executive operator role required to dispatch schedules")
    return {"results": get_integration_hub().dispatch_due_schedules(_tenant(current_user))}
