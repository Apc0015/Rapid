"""Encrypted local secret vault plus environment reference resolution."""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SecretVaultError(ValueError):
    pass


class SecretVault:
    def __init__(self, db_path: str | None = None, key_path: str | None = None):
        self.db_path = Path(db_path or os.getenv("RAPID_SECRETS_DB_PATH", "data/db/secrets.db"))
        self.key_path = Path(key_path or os.getenv("RAPID_LOCAL_VAULT_KEY_PATH", "data/.rapid_vault_key"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._load_key())
        self._init_db()

    def _load_key(self) -> bytes:
        configured = os.getenv("RAPID_ENCRYPTION_KEY", "").encode()
        if configured:
            try:
                Fernet(configured)
            except (ValueError, TypeError) as error:
                raise SecretVaultError("RAPID_ENCRYPTION_KEY must be a valid Fernet key") from error
            return configured
        if os.getenv("RAPID_ENV", "development") == "production":
            raise SecretVaultError("RAPID_ENCRYPTION_KEY is required in production")
        if self.key_path.exists():
            return self.key_path.read_bytes().strip()
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        self.key_path.write_bytes(key)
        os.chmod(self.key_path, 0o600)
        return key

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS encrypted_secrets (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    ciphertext BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(tenant_id, name)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def put(self, tenant_id: str, name: str, value: str) -> str:
        if not tenant_id.strip() or not name.strip() or not value:
            raise SecretVaultError("Tenant, secret name, and value are required")
        if len(value.encode("utf-8")) > 100_000:
            raise SecretVaultError("Secret is too large")
        now = datetime.now(timezone.utc).isoformat()
        secret_id = f"sec_{uuid.uuid4().hex[:16]}"
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO encrypted_secrets VALUES (?,?,?,?,?,?)
                   ON CONFLICT(tenant_id, name) DO UPDATE SET ciphertext=excluded.ciphertext, updated_at=excluded.updated_at""",
                (secret_id, tenant_id, name, self._fernet.encrypt(value.encode()), now, now),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM encrypted_secrets WHERE tenant_id=? AND name=?", (tenant_id, name)).fetchone()
            return f"vault://{row['id']}"
        finally:
            conn.close()

    def resolve(self, reference: str, tenant_id: str | None = None) -> str:
        if reference.startswith("env://"):
            variable = reference.removeprefix("env://")
            value = os.getenv(variable, "")
            if not value:
                raise SecretVaultError(f"Environment secret '{variable}' is not configured")
            return value
        if not reference.startswith("vault://"):
            raise SecretVaultError("Secret references must use env:// or vault://")
        secret_id = reference.removeprefix("vault://")
        conn = self._connect()
        try:
            query, args = "SELECT * FROM encrypted_secrets WHERE id=?", [secret_id]
            if tenant_id:
                query += " AND tenant_id=?"
                args.append(tenant_id)
            row = conn.execute(query, args).fetchone()
            if not row:
                raise SecretVaultError("Secret reference was not found")
            try:
                return self._fernet.decrypt(row["ciphertext"]).decode()
            except InvalidToken as error:
                raise SecretVaultError("Secret could not be decrypted with the configured key") from error
        finally:
            conn.close()

    def delete(self, tenant_id: str, reference: str) -> None:
        secret_id = reference.removeprefix("vault://")
        conn = self._connect()
        try:
            conn.execute("DELETE FROM encrypted_secrets WHERE id=? AND tenant_id=?", (secret_id, tenant_id))
            conn.commit()
        finally:
            conn.close()


def get_secret_vault() -> SecretVault:
    return SecretVault()
