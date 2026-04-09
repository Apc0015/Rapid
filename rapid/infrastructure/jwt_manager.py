from __future__ import annotations
"""
JWT Manager — access + refresh token lifecycle.

Access token:  30 min   (configurable via JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
Refresh token: 7 days   (configurable via JWT_REFRESH_TOKEN_EXPIRE_DAYS)

Refresh tokens are persisted in SQLite so they can be revoked on logout.
"""

import os
import sqlite3
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt as pyjwt

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY  = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
ALGORITHM   = "HS256"
ACCESS_EXP  = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_EXP = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS",   "7"))
DB_PATH     = "data/db/rapid.db"


# ── Token store (refresh tokens) ──────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            jti        TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


class JWTManager:

    # ── Create tokens ─────────────────────────────────────────────────────────

    def create_access_token(self, user_id: str, role: str,
                            permitted_departments: list,
                            extra: Optional[dict] = None) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub":   user_id,
            "role":  role,
            "depts": permitted_departments,
            "iat":   now,
            "exp":   now + timedelta(minutes=ACCESS_EXP),
            "type":  "access",
        }
        if extra:
            payload.update(extra)
        return pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    def create_refresh_token(self, user_id: str) -> str:
        jti = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=REFRESH_EXP)
        payload = {
            "sub":  user_id,
            "jti":  jti,
            "iat":  now,
            "exp":  expires_at,
            "type": "refresh",
        }
        token = pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        # Persist so it can be revoked
        conn = _get_conn()
        conn.execute(
            "INSERT INTO refresh_tokens (jti, user_id, expires_at) VALUES (?,?,?)",
            (jti, user_id, expires_at.isoformat()),
        )
        conn.commit()
        conn.close()
        return token

    # ── Validate tokens ───────────────────────────────────────────────────────

    def verify_access_token(self, token: str) -> dict:
        """
        Decode and validate an access token.
        Returns payload dict on success.
        Raises jwt.InvalidTokenError on failure.
        """
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise pyjwt.InvalidTokenError("Not an access token")
        return payload

    def verify_refresh_token(self, token: str) -> dict:
        """
        Decode, validate, and check DB revocation for a refresh token.
        Returns payload dict on success.
        Raises ValueError on failure.
        """
        try:
            payload = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except pyjwt.ExpiredSignatureError:
            raise ValueError("Refresh token expired — please log in again")
        except pyjwt.InvalidTokenError as e:
            raise ValueError(f"Invalid refresh token: {e}")

        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")

        jti = payload.get("jti", "")
        conn = _get_conn()
        row = conn.execute(
            "SELECT revoked FROM refresh_tokens WHERE jti = ?", (jti,)
        ).fetchone()
        conn.close()

        if not row:
            raise ValueError("Refresh token not found")
        if row[0]:
            raise ValueError("Refresh token has been revoked")

        return payload

    # ── Revoke / logout ───────────────────────────────────────────────────────

    def revoke_refresh_token(self, token: str) -> bool:
        """Revoke a specific refresh token (logout one device)."""
        try:
            payload = pyjwt.decode(
                token, SECRET_KEY, algorithms=[ALGORITHM],
                options={"verify_exp": False},
            )
            jti = payload.get("jti", "")
            conn = _get_conn()
            conn.execute("UPDATE refresh_tokens SET revoked=1 WHERE jti=?", (jti,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.warning(f"Failed to revoke token: {e}")
            return False

    def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user (logout all devices)."""
        conn = _get_conn()
        cursor = conn.execute(
            "UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user_id,)
        )
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return count

    def cleanup_expired(self):
        """Remove expired tokens from DB — run periodically."""
        conn = _get_conn()
        conn.execute(
            "DELETE FROM refresh_tokens WHERE expires_at < ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        conn.close()


# ── Singleton ─────────────────────────────────────────────────────────────────

_jwt_manager: Optional[JWTManager] = None


def get_jwt_manager() -> JWTManager:
    global _jwt_manager
    if _jwt_manager is None:
        _jwt_manager = JWTManager()
    return _jwt_manager
