"""
routers/deps.py — FastAPI dependency helpers.

Auth is now JWT Bearer token via Authorization header.
Legacy password-based auth kept for backward compat during transition.
"""

from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt as pyjwt

from infrastructure.user_registry import verify_password, load_users
from infrastructure.jwt_manager import get_jwt_manager

# ── OAuth2 Bearer scheme ──────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def _load_users() -> dict:
    """Load users from the DB-backed store (public-facing for internal use)."""
    return load_users()


# ── Primary: JWT Bearer dependency ────────────────────────────────────────────

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """
    FastAPI dependency — validates JWT Bearer token from Authorization header.
    Returns the decoded user payload: {sub, role, depts, ...}
    Raises HTTP 401 on failure.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Authorization header required (Bearer token)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = get_jwt_manager().verify_access_token(credentials.credentials)
        return payload
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Access token expired — please refresh",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Dependency — requires admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_role(*roles: str):
    """Dependency factory — requires one of the given roles."""
    def _dep(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Required role: {' or '.join(roles)}",
            )
        return current_user
    return _dep


# ── Legacy: password-based auth (used internally + backward compat) ───────────

def auth_user_password(user_id: str, password: str) -> dict:
    """
    Authenticate with user_id + password directly.
    Used by login endpoint and legacy paths.
    Returns the raw user record on success.
    Raises HTTP 401 on failure.
    """
    users = _load_users()
    user  = users.get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication failed")
    stored = user.get("password_hash", "")
    if not stored:
        # Legacy plaintext tokens are no longer accepted — all accounts must have password_hash.
        raise HTTPException(status_code=401, detail="Authentication failed")
    ok = verify_password(password, stored)
    if not ok:
        raise HTTPException(status_code=401, detail="Authentication failed")
    return user


def auth_user(user_id: str, password: str) -> dict:
    """Alias for backward compatibility."""
    return auth_user_password(user_id, password)


def require_admin_password(user_id: str, password: str) -> dict:
    """Legacy admin check via password — used by endpoints not yet migrated."""
    user = auth_user_password(user_id, password)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
