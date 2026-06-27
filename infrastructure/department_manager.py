"""
infrastructure/department_manager.py — Per-tenant department management.

Each tenant configures their own departments.
The default tenant pre-loads the 10 departments from the original RAPID design.
Every department maps to an agent that RAPID creates for it.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import config
from infrastructure.tenant_manager import DEFAULT_TENANT_ID

logger = logging.getLogger(__name__)

DEPARTMENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS departments (
    dept_id             TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT,
    head_user_id        TEXT,
    csuite_escalation   TEXT DEFAULT 'ceo',
    icon                TEXT,
    color               TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    status              TEXT DEFAULT 'active',
    PRIMARY KEY (dept_id, tenant_id)
);
"""

# Default departments for the original RAPID single-tenant setup
DEFAULT_DEPARTMENTS = [
    {
        "dept_id": "finance",
        "name": "Finance",
        "description": "Financial data, budgets, revenue, invoices, cash flow, and compliance.",
        "csuite_escalation": "cfo",
        "icon": "💰",
        "color": "#22c55e",
    },
    {
        "dept_id": "hr",
        "name": "Human Resources",
        "description": "Employee records, recruitment, payroll, performance, and DEI metrics.",
        "csuite_escalation": "cfo",
        "icon": "👥",
        "color": "#3b82f6",
    },
    {
        "dept_id": "legal",
        "name": "Legal",
        "description": "Contracts, compliance, litigation, IP portfolio, and regulatory tracking.",
        "csuite_escalation": "ceo",
        "icon": "⚖️",
        "color": "#8b5cf6",
    },
    {
        "dept_id": "sales",
        "name": "Sales",
        "description": "Deals, pipeline, quota attainment, forecasting, and customer interactions.",
        "csuite_escalation": "coo",
        "icon": "📈",
        "color": "#f59e0b",
    },
    {
        "dept_id": "marketing",
        "name": "Marketing",
        "description": "Campaigns, ad spend, leads, brand sentiment, and web analytics.",
        "csuite_escalation": "coo",
        "icon": "📣",
        "color": "#ec4899",
    },
    {
        "dept_id": "ops",
        "name": "Operations",
        "description": "Logistics, production metrics, inventory, SLAs, and facility management.",
        "csuite_escalation": "cto",
        "icon": "⚙️",
        "color": "#64748b",
    },
    {
        "dept_id": "it",
        "name": "Information Technology",
        "description": "Systems, incidents, assets, security events, and change management.",
        "csuite_escalation": "cto",
        "icon": "💻",
        "color": "#06b6d4",
    },
    {
        "dept_id": "procurement",
        "name": "Procurement",
        "description": "Purchase orders, suppliers, RFQs, spend analytics, and vendor contracts.",
        "csuite_escalation": "cfo",
        "icon": "🛒",
        "color": "#f97316",
    },
    {
        "dept_id": "rd",
        "name": "Research & Development",
        "description": "R&D projects, experiments, innovation pipeline, IP registry, and talent.",
        "csuite_escalation": "cto",
        "icon": "🔬",
        "color": "#84cc16",
    },
    {
        "dept_id": "customer_success",
        "name": "Customer Success",
        "description": "Account health, NPS, churn, renewals, onboarding, and expansion revenue.",
        "csuite_escalation": "coo",
        "icon": "🤝",
        "color": "#14b8a6",
    },
]


class DepartmentManager:
    """
    Manages per-tenant department configuration.
    Departments define the shape of the agent system for each tenant.
    """

    def __init__(self, db_path: str = config.DB_PATH):
        self._db_path = db_path
        self._init_schema()
        self._ensure_default_departments()

    def _init_schema(self):
        conn = self._connect()
        try:
            conn.executescript(DEPARTMENT_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    def _ensure_default_departments(self):
        """Seed default 10 departments for the default tenant."""
        existing = self.list_departments(DEFAULT_TENANT_ID)
        existing_ids = {d["dept_id"] for d in existing}
        for dept in DEFAULT_DEPARTMENTS:
            if dept["dept_id"] not in existing_ids:
                self.create_department(
                    tenant_id=DEFAULT_TENANT_ID,
                    dept_id=dept["dept_id"],
                    name=dept["name"],
                    description=dept["description"],
                    csuite_escalation=dept["csuite_escalation"],
                    icon=dept.get("icon"),
                    color=dept.get("color"),
                )
        logger.info(f"[DepartmentManager] Default departments ready for tenant '{DEFAULT_TENANT_ID}'")

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_department(
        self,
        tenant_id: str,
        name: str,
        description: str = None,
        dept_id: str = None,
        csuite_escalation: str = "ceo",
        icon: str = None,
        color: str = None,
    ) -> dict:
        did = dept_id or name.lower().replace(" ", "_")
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO departments
                    (dept_id, tenant_id, name, description,
                     csuite_escalation, icon, color, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (did, tenant_id, name, description,
                 csuite_escalation, icon, color,
                 datetime.utcnow().isoformat()),
            )
            conn.commit()
            return self.get_department(tenant_id, did)
        finally:
            conn.close()

    def get_department(self, tenant_id: str, dept_id: str) -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM departments WHERE tenant_id = ? AND dept_id = ?",
                (tenant_id, dept_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_departments(self, tenant_id: str) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM departments WHERE tenant_id = ? AND status = 'active' ORDER BY name",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_department(self, tenant_id: str, dept_id: str, **fields) -> Optional[dict]:
        allowed = {"name", "description", "head_user_id", "csuite_escalation",
                   "icon", "color", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_department(tenant_id, dept_id)
        cols = ", ".join(f"{k} = ?" for k in updates)
        conn = self._connect()
        try:
            conn.execute(
                f"UPDATE departments SET {cols} WHERE tenant_id = ? AND dept_id = ?",
                (*updates.values(), tenant_id, dept_id),
            )
            conn.commit()
            return self.get_department(tenant_id, dept_id)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=config.DB_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        return conn


# ── Singleton ─────────────────────────────────────────────────────────────────

_dept_manager: Optional[DepartmentManager] = None


def get_department_manager() -> DepartmentManager:
    global _dept_manager
    if _dept_manager is None:
        _dept_manager = DepartmentManager()
    return _dept_manager
