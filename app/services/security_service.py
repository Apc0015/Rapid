import os
import jwt
import bcrypt
import sqlite3
import logging
import json
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from collections import defaultdict
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from logging.handlers import RotatingFileHandler
import secrets

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USER_DB_PATH = os.path.join(DB_DIR, "users.db")
AUDIT_LOG_PATH = os.path.join(DB_DIR, "audit.log")

MIN_PASSWORD_LENGTH = 8


class SecurityService:
    """Service for handling authentication and authorization"""

    def __init__(self):
        self.secret_key = os.getenv("JWT_SECRET_KEY", "")
        if not self.secret_key:
            secret_file = os.path.join(DB_DIR, ".jwt_secret")
            os.makedirs(DB_DIR, exist_ok=True)
            if os.path.exists(secret_file):
                with open(secret_file, "r") as f:
                    self.secret_key = f.read().strip()
            else:
                self.secret_key = secrets.token_hex(32)
                with open(secret_file, "w") as f:
                    f.write(self.secret_key)
                os.chmod(secret_file, 0o600)

        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
        self.security = HTTPBearer()

        # Rate limiting state (in-memory, per-process)
        self._rate_limit_lock = threading.Lock()
        self._rate_limit_records: Dict[str, list] = defaultdict(list)

        # Initialize SQLite user database
        self._init_db()

        # Setup rotating audit log handler
        self._init_audit_logger()

    def _init_db(self):
        """Initialize the SQLite user database"""
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(USER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        # Add missing columns for multi-tenant RBAC (safe to run repeatedly)
        cursor.execute("PRAGMA table_info(users)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if "org_id" not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN org_id TEXT")
        if "department" not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN department TEXT")
        if "groups" not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN groups TEXT")
        if "oauth_provider" not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_provider TEXT")
        if "oauth_id" not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_id TEXT")

        # Organizations table (minimal for Phase 1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                org_id TEXT PRIMARY KEY,
                org_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                settings TEXT,
                active INTEGER DEFAULT 1
            )
        """)

        # Seed default organization if empty
        count = cursor.execute("SELECT COUNT(1) FROM organizations").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "INSERT INTO organizations (org_id, org_name, created_at, settings, active) "
                "VALUES (?, ?, ?, ?, 1)",
                ("default", "Default Organization", now, None),
            )

        # Backfill org_id and groups for existing users
        cursor.execute("UPDATE users SET org_id = COALESCE(org_id, 'default')")
        cursor.execute("UPDATE users SET groups = COALESCE(groups, '[]')")
        conn.commit()
        conn.close()

    def _init_audit_logger(self):
        """Initialize rotating file handler for audit logs"""
        os.makedirs(DB_DIR, exist_ok=True)
        # Create rotating handler: max 10MB per file, keep 5 backups
        self.audit_handler = RotatingFileHandler(
            AUDIT_LOG_PATH,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        self.audit_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(message)s')
        )
        # Create dedicated logger for audit
        self.audit_logger = logging.getLogger('audit')
        self.audit_logger.setLevel(logging.INFO)
        self.audit_logger.addHandler(self.audit_handler)
        self.audit_logger.propagate = False  # Don't propagate to root logger

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(USER_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    @staticmethod
    def validate_password(password: str):
        """Validate password strength. Raises HTTPException on failure."""
        if len(password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters long",
            )
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        if not (has_upper and has_lower and has_digit):
            raise HTTPException(
                status_code=400,
                detail="Password must contain at least one uppercase letter, one lowercase letter, and one digit",
            )

    def create_user(self, username: str, password: str, role: str = "user") -> Dict[str, Any]:
        """Create a new user (role is always forced to 'user' for public registration)"""
        # Force role to 'user' — admin accounts must be created through other means
        role = "user"

        self.validate_password(password)

        conn = self._get_db()
        try:
            existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="User already exists")

            hashed_password = self.hash_password(password)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO users (username, password_hash, role, active, created_at, org_id, groups) "
                "VALUES (?, ?, ?, 1, ?, ?, ?)",
                (username, hashed_password, role, now, "default", json.dumps([])),
            )
            conn.commit()
            return {"username": username, "role": role, "message": "User created successfully"}
        finally:
            conn.close()

    def create_user_admin(
        self,
        username: str,
        password: str,
        role: str = "user",
        org_id: str = "default",
        department: Optional[str] = None,
        groups: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Create a new user with explicit role/org (admin-only path)."""
        if role not in ("admin", "manager", "user"):
            raise HTTPException(status_code=400, detail="Invalid role")

        self.validate_password(password)

        conn = self._get_db()
        try:
            existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="User already exists")

            hashed_password = self.hash_password(password)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO users (username, password_hash, role, active, created_at, org_id, department, groups) "
                "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
                (username, hashed_password, role, now, org_id, department, json.dumps(groups or [])),
            )
            conn.commit()
            return {"username": username, "role": role, "org_id": org_id, "message": "User created successfully"}
        finally:
            conn.close()

    def create_oauth_user(
        self,
        username: str,
        provider: str,
        oauth_id: str,
        org_id: str = "default",
    ) -> Dict[str, Any]:
        """Create a user record for OAuth login."""
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")
        if not oauth_id:
            raise HTTPException(status_code=400, detail="OAuth id is required")

        conn = self._get_db()
        try:
            existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="User already exists")

            # Random password placeholder (not used for OAuth)
            random_password = secrets.token_urlsafe(32)
            hashed_password = self.hash_password(random_password)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO users (username, password_hash, role, active, created_at, org_id, groups, oauth_provider, oauth_id) "
                "VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)",
                (username, hashed_password, "user", now, org_id, json.dumps([]), provider, oauth_id),
            )
            conn.commit()
            return {"username": username, "role": "user", "org_id": org_id}
        finally:
            conn.close()

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a user"""
        conn = self._get_db()
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row or not row["active"]:
                return None
            if not self.verify_password(password, row["password_hash"]):
                return None
            groups = json.loads(row["groups"]) if row["groups"] else []
            return {
                "username": row["username"],
                "role": row["role"],
                "org_id": row["org_id"] or "default",
                "department": row["department"],
                "groups": groups,
            }
        finally:
            conn.close()

    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> Dict[str, Any]:
        """Get current authenticated user from JWT token"""
        token = credentials.credentials
        payload = self.verify_token(token)

        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        conn = self._get_db()
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="User not found")
            if not row["active"]:
                raise HTTPException(status_code=401, detail="User account is disabled")
            groups = json.loads(row["groups"]) if row["groups"] else []
            return {
                "username": row["username"],
                "role": row["role"],
                "org_id": row["org_id"] or "default",
                "department": row["department"],
                "groups": groups,
            }
        finally:
            conn.close()

    def require_role(self, required_role: str):
        """Dependency to require specific role"""
        def role_checker(current_user: Dict = Depends(self.get_current_user)):
            if current_user["role"] != required_role and current_user["role"] != "admin":
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return current_user
        return role_checker

    def rate_limit_check(self, user_id: str, action: str, limit: int = 100, window_seconds: int = 3600) -> bool:
        """Simple in-memory rate limiting using a sliding window."""
        key = f"{user_id}:{action}"
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - window_seconds

        with self._rate_limit_lock:
            # Prune old entries
            self._rate_limit_records[key] = [t for t in self._rate_limit_records[key] if t > cutoff]
            if len(self._rate_limit_records[key]) >= limit:
                return False
            self._rate_limit_records[key].append(now)
            return True

    def audit_log(self, user: str, action: str, resource: str, details: Dict = None):
        """Log security events to a rotating file"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": user,
            "action": action,
            "resource": resource,
            "details": details or {},
        }
        # Log using the rotating handler
        self.audit_logger.info(json.dumps(log_entry))
        # Also log to standard logger for console output
        logger.info("AUDIT: %s", log_entry)

    def sanitize_input(self, input_text: str) -> str:
        """Sanitize user input — light sanitization that preserves legitimate text.

        The real protection against SQL injection is parameterized queries in
        database_service.py, not stripping characters here.
        """
        import re
        # Only strip HTML script tags to prevent XSS if content is ever rendered
        input_text = re.sub(r"<script[^>]*>.*?</script>", "", input_text, flags=re.IGNORECASE | re.DOTALL)
        # Strip other HTML tags
        input_text = re.sub(r"<[^>]+>", "", input_text)
        return input_text.strip()
