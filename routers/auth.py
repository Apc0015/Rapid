"""
routers/auth.py — Authentication endpoints.

  POST /auth/register   — Self-registration
  POST /auth/login      — Returns JWT access + refresh tokens
  POST /auth/refresh    — Exchange refresh token for new access token
  POST /auth/logout     — Revoke refresh token
  POST /auth/logout-all — Revoke all devices
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

_auth_limiter = Limiter(key_func=get_remote_address)

from infrastructure.user_registry import (
    register_user, verify_password, set_db_mode,
    get_user_access, change_password as registry_change_password,
    load_users,
)
from infrastructure.jwt_manager import get_jwt_manager
from shared import spokesperson
from .deps import get_current_user, auth_user_password

router = APIRouter(tags=["auth"])


# ── Self-registration ─────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    employee_name:   str
    org_email:       str
    password:        str
    employee_id:     str
    requested_depts: list
    justification:   str


@router.post("/auth/register")
async def register(body: RegisterRequest):
    """Any employee can self-register using their org email and a password."""
    try:
        req = register_user(
            employee_name   = body.employee_name,
            org_email       = body.org_email,
            password        = body.password,
            employee_id     = body.employee_id,
            requested_depts = body.requested_depts,
            justification   = body.justification,
        )
        return {
            "status":     "submitted",
            "request_id": req["request_id"],
            "message":    f"Registration submitted ({req['request_id']}). "
                          "Your request is now with the department heads for review.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Login — returns JWT ───────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    user_id:  str
    password: str


@router.post("/auth/login")
@_auth_limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """
    Login with user_id + password.
    Returns JWT access token (30 min) + refresh token (7 days).
    """
    users = load_users()
    if not users:
        raise HTTPException(status_code=401, detail="No user accounts found")

    user  = users.get(body.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    stored = user.get("password_hash", "")
    if not stored:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    ok = verify_password(body.password, stored)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    jwt = get_jwt_manager()
    permitted_depts = user.get("permitted_departments", [])
    role            = user.get("role", "employee")

    access_token  = jwt.create_access_token(
        user_id=body.user_id,
        role=role,
        permitted_departments=permitted_depts,
        extra={"tenant_id": user.get("tenant_id", "default")},
    )
    refresh_token = jwt.create_refresh_token(user_id=body.user_id)

    return {
        "access_token":          access_token,
        "refresh_token":         refresh_token,
        "token_type":            "bearer",
        "expires_in_minutes":    30,
        # Profile fields (for Flutter to cache)
        "user_id":               body.user_id,
        "name":                  user.get("name", body.user_id),
        "role":                  role,
        "email":                 user.get("email", ""),
        "rapid_user_id":         user.get("rapid_user_id", ""),
        "permitted_departments": permitted_depts,
        "db_mode_enabled":       user.get("db_mode_enabled", False),
    }


# ── Refresh token ─────────────────────────────────────────────────────────────

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/auth/refresh")
async def refresh_token(body: RefreshRequest):
    """
    Exchange a valid refresh token for a new access token.
    The refresh token is NOT rotated (same refresh token remains valid).
    """
    jwt = get_jwt_manager()
    try:
        payload = jwt.verify_refresh_token(body.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    user_id = payload["sub"]

    # Reload user to get latest role + permissions (DB-backed)
    users = load_users()
    user  = users.get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")

    access_token = jwt.create_access_token(
        user_id=user_id,
        role=user.get("role", "employee"),
        permitted_departments=user.get("permitted_departments", []),
        extra={"tenant_id": user.get("tenant_id", "default")},
    )
    return {
        "access_token":       access_token,
        "token_type":         "bearer",
        "expires_in_minutes": 30,
    }


# ── Logout ────────────────────────────────────────────────────────────────────

class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/auth/logout")
async def logout(body: LogoutRequest, current_user: dict = Depends(get_current_user)):
    """Revoke refresh token for this device.
    Verifies the submitted token belongs to the authenticated user before revoking.
    """
    import jwt as _pyjwt
    try:
        payload = _pyjwt.decode(
            body.refresh_token,
            options={"verify_signature": False, "verify_exp": False},
            algorithms=["HS256"],
        )
        if payload.get("sub") != current_user["sub"]:
            raise HTTPException(
                status_code=403,
                detail="Cannot revoke a token that does not belong to you",
            )
    except _pyjwt.DecodeError:
        raise HTTPException(status_code=400, detail="Invalid refresh token format")
    get_jwt_manager().revoke_refresh_token(body.refresh_token)
    return {"status": "ok", "message": "Logged out successfully"}


@router.post("/auth/logout-all")
async def logout_all(current_user: dict = Depends(get_current_user)):
    """Revoke all refresh tokens for this user (all devices)."""
    user_id = current_user["sub"]
    count = get_jwt_manager().revoke_all_for_user(user_id)
    return {"status": "ok", "message": f"Logged out from {count} device(s)"}


# ── User self-service ─────────────────────────────────────────────────────────

@router.get("/users/my-access")
async def my_access(current_user: dict = Depends(get_current_user)):
    """User views their own access profile."""
    return get_user_access(current_user["sub"])


class DbModeRequest(BaseModel):
    enabled: bool


@router.post("/users/db-mode")
async def toggle_db_mode(body: DbModeRequest, current_user: dict = Depends(get_current_user)):
    """User toggles database mode on/off."""
    set_db_mode(current_user["sub"], body.enabled)
    return {"status": "ok", "db_mode_enabled": body.enabled}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str


@router.post("/users/change-password")
async def change_password_endpoint(body: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    """User changes their own password. Revokes all refresh tokens after change."""
    user_id = current_user["sub"]
    # Verify current password (DB-backed lookup)
    users = load_users()
    user  = users.get(user_id, {})
    stored = user.get("password_hash", "")
    if not stored:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    ok = verify_password(body.current_password, stored)
    if not ok:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        registry_change_password(user_id, body.current_password, body.new_password)
        spokesperson.reload_users()
        # Revoke all sessions — user must log in again
        get_jwt_manager().revoke_all_for_user(user_id)
        return {"status": "ok", "message": "Password updated. Please log in again."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
