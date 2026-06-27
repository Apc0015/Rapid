"""
infrastructure/tenant_manager.py — Tenant management for RAPID multi-tenancy.

Every company using RAPID is a tenant. This module manages:
  - Tenant registration and provisioning
  - Tenant lookup and validation
  - Tenant configuration (LLM, branding, industry pack)

Phase 1: Single-tenant mode is supported by a default tenant.
Phase 8: Full multi-tenant onboarding added on top.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

# Default tenant ID used in single-tenant / dev mode
DEFAULT_TENANT_ID = "default"


# ── Schema creation ───────────────────────────────────────────────────────────

TENANT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id           TEXT PRIMARY KEY,
    company_name        TEXT NOT NULL,
    industry            TEXT,
    size_band           TEXT DEFAULT 'smb',
    plan                TEXT DEFAULT 'starter',
    industry_pack       TEXT,
    llm_provider        TEXT DEFAULT 'anthropic',
    llm_model           TEXT DEFAULT 'claude-opus-4-6',
    llm_config          TEXT,
    primary_language    TEXT DEFAULT 'en',
    timezone            TEXT DEFAULT 'UTC',
    branding            TEXT,
    status              TEXT DEFAULT 'active',
    created_at          TEXT DEFAULT (datetime('now')),
    trial_ends_at       TEXT,
    subscription_start  TEXT
);

CREATE TABLE IF NOT EXISTS tenant_usage (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id           TEXT NOT NULL,
    date                TEXT NOT NULL,
    queries_count       INTEGER DEFAULT 0,
    analysis_runs       INTEGER DEFAULT 0,
    documents_produced  INTEGER DEFAULT 0,
    llm_tokens_used     INTEGER DEFAULT 0,
    storage_mb          REAL DEFAULT 0,
    active_projects     INTEGER DEFAULT 0,
    active_users        INTEGER DEFAULT 0,
    UNIQUE(tenant_id, date)
);
"""


class TenantManager:
    """
    Manages tenant lifecycle — creation, lookup, config, usage tracking.
    Uses the global rapid.db as the platform-level store.
    """

    def __init__(self, db_path: str = config.DB_PATH):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._ensure_default_tenant()

    # ── Schema init ───────────────────────────────────────────────────────────

    def _init_schema(self):
        """Create tenant tables if they don't exist."""
        conn = self._connect()
        try:
            conn.executescript(TENANT_SCHEMA_SQL)
            conn.commit()
            logger.info("[TenantManager] Tenant schema initialized")
        except Exception as e:
            logger.error(f"[TenantManager] Schema init failed: {e}")
            raise
        finally:
            conn.close()

    def _ensure_default_tenant(self):
        """Create the default tenant if it doesn't exist (single-tenant / dev mode)."""
        if not self.get_tenant(DEFAULT_TENANT_ID):
            self.create_tenant(
                tenant_id=DEFAULT_TENANT_ID,
                company_name="Default Organization",
                industry="technology",
                plan="enterprise",
            )
            logger.info(f"[TenantManager] Default tenant '{DEFAULT_TENANT_ID}' created")

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_tenant(
        self,
        company_name: str,
        industry: str = None,
        plan: str = "starter",
        llm_provider: str = "anthropic",
        llm_model: str = "claude-opus-4-6",
        industry_pack: str = None,
        tenant_id: str = None,
    ) -> dict:
        """
        Register a new company as a tenant.
        Returns the created tenant record.
        """
        tid = tenant_id or str(uuid.uuid4())
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO tenants
                    (tenant_id, company_name, industry, plan,
                     llm_provider, llm_model, industry_pack, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tid, company_name, industry, plan,
                 llm_provider, llm_model, industry_pack,
                 datetime.utcnow().isoformat()),
            )
            conn.commit()
            logger.info(f"[TenantManager] Tenant created: {tid} ({company_name})")
            return self.get_tenant(tid)
        except sqlite3.IntegrityError:
            logger.warning(f"[TenantManager] Tenant {tid} already exists")
            return self.get_tenant(tid)
        finally:
            conn.close()

    def get_tenant(self, tenant_id: str) -> Optional[dict]:
        """Return tenant record or None if not found."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_tenants(self) -> list[dict]:
        """Return all active tenants."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM tenants WHERE status = 'active' ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_tenant(self, tenant_id: str, **fields) -> Optional[dict]:
        """Update tenant fields."""
        if not fields:
            return self.get_tenant(tenant_id)
        allowed = {
            "company_name", "industry", "plan", "llm_provider",
            "llm_model", "llm_config", "branding", "status",
            "industry_pack", "primary_language", "timezone",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_tenant(tenant_id)
        cols = ", ".join(f"{k} = ?" for k in updates)
        conn = self._connect()
        try:
            conn.execute(
                f"UPDATE tenants SET {cols} WHERE tenant_id = ?",
                (*updates.values(), tenant_id),
            )
            conn.commit()
            return self.get_tenant(tenant_id)
        finally:
            conn.close()

    # ── Usage tracking ────────────────────────────────────────────────────────

    def record_usage(
        self,
        tenant_id: str,
        queries: int = 0,
        analysis: int = 0,
        documents: int = 0,
        tokens: int = 0,
    ):
        """Increment today's usage counters for a tenant."""
        today = datetime.utcnow().date().isoformat()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO tenant_usage (tenant_id, date, queries_count,
                    analysis_runs, documents_produced, llm_tokens_used)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, date) DO UPDATE SET
                    queries_count    = queries_count    + excluded.queries_count,
                    analysis_runs    = analysis_runs    + excluded.analysis_runs,
                    documents_produced = documents_produced + excluded.documents_produced,
                    llm_tokens_used  = llm_tokens_used  + excluded.llm_tokens_used
                """,
                (tenant_id, today, queries, analysis, documents, tokens),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"[TenantManager] Usage tracking failed: {e}")
        finally:
            conn.close()

    def get_usage(self, tenant_id: str, days: int = 30) -> list[dict]:
        """Return usage stats for the last N days."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM tenant_usage
                WHERE tenant_id = ?
                  AND date >= date('now', ?)
                ORDER BY date DESC
                """,
                (tenant_id, f"-{days} days"),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=config.DB_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        return conn


# ── Singleton ─────────────────────────────────────────────────────────────────

_tenant_manager: Optional[TenantManager] = None


def get_tenant_manager() -> TenantManager:
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager()
    return _tenant_manager
