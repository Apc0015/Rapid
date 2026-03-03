"""
Auth Service — simplified authentication with department and role.

Replaces the old SecurityService. Keeps JWT + bcrypt, drops OAuth/groups/org_id.
Department and role are first-class fields used by the governance layer.
"""

import os
import jwt
import bcrypt
import sqlite3
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USER_DB_PATH = os.path.join(DATA_DIR, "users.db")
MIN_PASSWORD_LENGTH = 8

VALID_ROLES = ("admin", "manager", "viewer")


class AuthService:
    """Authentication with department/role for governance scoping."""

    def __init__(self):
        self.secret_key = self._load_or_create_secret()
        self.algorithm = "HS256"
        self.token_expire_minutes = 480  # 8 hours
        self._init_db()

    def _load_or_create_secret(self) -> str:
        os.makedirs(DATA_DIR, exist_ok=True)
        if env_key := os.getenv("JWT_SECRET_KEY"):
            return env_key
        secret_file = os.path.join(DATA_DIR, ".jwt_secret")
        if os.path.exists(secret_file):
            with open(secret_file) as f:
                return f.read().strip()
        key = secrets.token_hex(32)
        with open(secret_file, "w") as f:
            f.write(key)
        os.chmod(secret_file, 0o600)
        return key

    def _init_db(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username    TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    department  TEXT NOT NULL DEFAULT 'general',
                    role        TEXT NOT NULL DEFAULT 'viewer',
                    active      INTEGER NOT NULL DEFAULT 1,
                    created_at  TEXT NOT NULL
                )
            """)
            conn.commit()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(USER_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    # ─── Password helpers ─────────────────────────────────────────────────────

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    @staticmethod
    def validate_password(password: str):
        if len(password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        if not (
            any(c.isupper() for c in password)
            and any(c.islower() for c in password)
            and any(c.isdigit() for c in password)
        ):
            raise HTTPException(
                400, "Password must contain uppercase, lowercase, and a digit"
            )

    # ─── User management ──────────────────────────────────────────────────────

    def create_user(
        self,
        username: str,
        password: str,
        department: str = "general",
        role: str = "viewer",
    ) -> Dict[str, Any]:
        if role not in VALID_ROLES:
            raise HTTPException(400, f"Invalid role. Must be one of: {VALID_ROLES}")
        self.validate_password(password)
        with self._get_db() as conn:
            if conn.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)
            ).fetchone():
                raise HTTPException(400, "Username already exists")
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO users (username, password_hash, department, role, active, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (username, self.hash_password(password), department, role, now),
            )
            conn.commit()
        return {"username": username, "department": department, "role": role}

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        with self._get_db() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        if not row or not row["active"]:
            return None
        if not self.verify_password(password, row["password_hash"]):
            return None
        return {
            "username": row["username"],
            "department": row["department"],
            "role": row["role"],
        }

    def list_users(self) -> List[Dict[str, Any]]:
        with self._get_db() as conn:
            rows = conn.execute(
                "SELECT username, department, role, active, created_at FROM users"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_user(
        self,
        username: str,
        department: Optional[str] = None,
        role: Optional[str] = None,
        active: Optional[bool] = None,
    ):
        if role is not None and role not in VALID_ROLES:
            raise HTTPException(400, f"Invalid role: {role}")
        updates, params = [], []
        if department is not None:
            updates.append("department = ?")
            params.append(department)
        if role is not None:
            updates.append("role = ?")
            params.append(role)
        if active is not None:
            updates.append("active = ?")
            params.append(1 if active else 0)
        if not updates:
            return
        params.append(username)
        with self._get_db() as conn:
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE username = ?", params
            )
            conn.commit()

    # ─── JWT ──────────────────────────────────────────────────────────────────

    def create_token(self, user_data: Dict[str, Any]) -> str:
        payload = {
            "sub": user_data["username"],
            "username": user_data["username"],
            "department": user_data["department"],
            "role": user_data["role"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=self.token_expire_minutes),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.PyJWTError:
            return None

    # ─── FastAPI dependencies ──────────────────────────────────────────────────

    def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    ) -> Dict[str, Any]:
        payload = self.verify_token(credentials.credentials)
        if not payload:
            raise HTTPException(401, "Invalid or expired token")
        with self._get_db() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (payload.get("sub"),)
            ).fetchone()
        if not row or not row["active"]:
            raise HTTPException(401, "User not found or disabled")
        return {
            "username": row["username"],
            "department": row["department"],
            "role": row["role"],
        }

    def require_role(self, required_role: str):
        def checker(user: Dict = Depends(self.get_current_user)):
            if user["role"] != required_role and user["role"] != "admin":
                raise HTTPException(403, "Insufficient permissions")
            return user
        return checker
