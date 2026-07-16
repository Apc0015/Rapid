"""Invite-only beta application and activation state."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class BetaAccessError(ValueError):
    """Safe error surfaced by the beta application flow."""


class BetaAccessStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or os.getenv("RAPID_BETA_DB_PATH", "data/db/beta_access.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS beta_applications (
                    id TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    owner_name TEXT NOT NULL,
                    owner_email TEXT NOT NULL UNIQUE,
                    industry TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '',
                    use_case TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    tenant_id TEXT,
                    owner_login_key TEXT,
                    reviewer_notes TEXT NOT NULL DEFAULT '',
                    activation_token_hash TEXT,
                    activation_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    activated_at TEXT
                )"""
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _public(record: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        value = dict(record)
        for key in ("activation_token_hash", "activation_expires_at", "owner_login_key"):
            value.pop(key, None)
        return value

    def submit(self, *, company_name: str, owner_name: str, owner_email: str, industry: str = "", website: str = "", use_case: str = "") -> dict[str, Any]:
        company_name = company_name.strip()
        owner_name = owner_name.strip()
        owner_email = owner_email.strip().lower()
        if not company_name or len(company_name) > 160:
            raise BetaAccessError("Company name is required")
        if not owner_name or len(owner_name) > 160:
            raise BetaAccessError("Your name is required")
        if "@" not in owner_email or len(owner_email) > 254:
            raise BetaAccessError("Enter a valid work email")
        if len(industry) > 100 or len(website) > 255 or len(use_case) > 1_000:
            raise BetaAccessError("One of the application fields is too long")
        if website:
            parsed = urlparse(website)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise BetaAccessError("Website must be a valid http or https URL")
        application_id = str(uuid.uuid4())
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO beta_applications
                    (id, company_name, owner_name, owner_email, industry, website, use_case, status, created_at)
                    VALUES (?,?,?,?,?,?,?,'pending_review',?)""",
                    (application_id, company_name, owner_name, owner_email, industry.strip(), website.strip(), use_case.strip(), self._now()),
                )
        except sqlite3.IntegrityError as error:
            raise BetaAccessError("An application for this email already exists") from error
        return {"application_id": application_id, "status": "pending_review"}

    def list_applications(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM beta_applications ORDER BY CASE status WHEN 'pending_review' THEN 0 ELSE 1 END, created_at DESC"
            ).fetchall()
        return [self._public(row) for row in rows]

    def approve(self, application_id: str, *, tenant_id: str, owner_login_key: str, reviewer_notes: str = "") -> tuple[dict[str, Any], str]:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM beta_applications WHERE id=?", (application_id,)).fetchone()
            if not row:
                raise BetaAccessError("Application not found")
            if row["status"] != "pending_review":
                raise BetaAccessError("Only pending applications can be approved")
            connection.execute(
                """UPDATE beta_applications SET status='approved', tenant_id=?, owner_login_key=?, reviewer_notes=?,
                   activation_token_hash=?, activation_expires_at=?, reviewed_at=? WHERE id=?""",
                (tenant_id, owner_login_key, reviewer_notes.strip(), token_hash, expires_at, self._now(), application_id),
            )
            updated = connection.execute("SELECT * FROM beta_applications WHERE id=?", (application_id,)).fetchone()
        return self._public(updated), token

    def reject(self, application_id: str, reviewer_notes: str = "") -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM beta_applications WHERE id=?", (application_id,)).fetchone()
            if not row:
                raise BetaAccessError("Application not found")
            if row["status"] != "pending_review":
                raise BetaAccessError("Only pending applications can be declined")
            connection.execute(
                "UPDATE beta_applications SET status='declined', reviewer_notes=?, reviewed_at=? WHERE id=?",
                (reviewer_notes.strip(), self._now(), application_id),
            )
            updated = connection.execute("SELECT * FROM beta_applications WHERE id=?", (application_id,)).fetchone()
        return self._public(updated)

    def redeem_activation(self, token: str) -> dict[str, Any]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM beta_applications WHERE activation_token_hash=?", (token_hash,)
            ).fetchone()
            if not row or row["status"] != "approved":
                raise BetaAccessError("This activation link is invalid or has already been used")
            expires_at = datetime.fromisoformat(row["activation_expires_at"])
            if expires_at <= datetime.now(timezone.utc):
                raise BetaAccessError("This activation link has expired")
            return dict(row)

    def mark_activated(self, application_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE beta_applications SET status='activated', activation_token_hash=NULL,
                   activation_expires_at=NULL, activated_at=? WHERE id=?""",
                (self._now(), application_id),
            )


_store: BetaAccessStore | None = None


def get_beta_access_store() -> BetaAccessStore:
    global _store
    if _store is None:
        _store = BetaAccessStore()
    return _store
