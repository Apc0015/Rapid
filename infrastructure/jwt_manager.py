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
_raw_secret = os.getenv("JWT_SECRET_KEY", "")
if not _raw_secret or _raw_secret == "CHANGE_ME_IN_PRODUCTION":
    raise RuntimeError(
        "[jwt_manager] JWT_SECRET_KEY env var is missing or still set to the "
        "default placeholder. Set a strong random secret before starting the server.\n"
        "  Example:  export JWT_SECRET_KEY=$(python -c \"import secrets; print(secrets.token_hex(32))\")"
    )
SECRET_KEY  = _raw_secret
ALGORITHM   = "HS256"
ACCESS_EXP  = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_EXP = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS",   "7"))
_DB_PRIMARY = str(Path(__file__).parent.parent / "data" / "db" / "jwt_tokens.db")
_DB_FALLBACK = "/tmp/rapid_jwt_tokens.db"


def _resolve_db_path() -> str:
    """
    Return a writable SQLite path.
    Try the project path first; fall back to /tmp if the filesystem
    does not support SQLite journal files (e.g. certain network/overlay mounts).
    """
    primary = Path(_DB_PRIMARY)
    try:
        primary.parent.mkdir(parents=True, exist_ok=True)
        test_conn = sqlite3.connect(str(primary), timeout=3)
        # Test that we can actually write — not just open the file
        test_conn.execute("CREATE TABLE IF NOT EXISTS _probe (x INTEGER)")
        test_conn.execute("INSERT INTO _probe VALUES (1)")
        test_conn.commit()
        test_conn.execute("DELETE FROM _probe")
        test_conn.commit()
        test_conn.close()
        return str(primary)
    except sqlite3.OperationalError as e:
        logger.warning(
            f"[jwt_manager] Cannot use primary DB path {primary} "
            f"({e}). Falling back to {_DB_FALLBACK}"
        )
        return _DB_FALLBACK


DB_PATH: str = _resolve_db_path()


# ── Token store (refresh tokens) ──────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    # Enable WAL only if supported (some mounted filesystems don't support it)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # Fallback to default journal mode
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
