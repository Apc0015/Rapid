"""
infrastructure/project_provisioner.py — Auto-provisions project databases.

When a project is created, the ProjectProvisioner:
  1. Creates the project's own SQLite database
  2. Creates all 6 universal tables inside it
  3. Creates the FAISS index directory
  4. Registers the project in project_registry
  5. Registers the schema in project_schema_registry
  6. Creates domain-specific tables based on the department

This runs automatically — no manual setup needed per project.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ── Platform-level tables (global rapid.db) ───────────────────────────────────

PLATFORM_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    project_id          TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT,
    project_type        TEXT NOT NULL DEFAULT 'single_dept',
    primary_dept_id     TEXT NOT NULL,
    status              TEXT DEFAULT 'active',
    priority            TEXT DEFAULT 'medium',
    owner_user_id       TEXT NOT NULL,
    start_date          TEXT,
    target_end_date     TEXT,
    actual_end_date     TEXT,
    budget_total        REAL,
    tags                TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS project_departments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    dept_id             TEXT NOT NULL,
    role                TEXT DEFAULT 'contributor',
    joined_at           TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, dept_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS project_members (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    user_id             TEXT NOT NULL,
    dept_id             TEXT NOT NULL,
    role                TEXT NOT NULL DEFAULT 'member',
    access_level        TEXT DEFAULT 'standard',
    joined_at           TEXT DEFAULT (datetime('now')),
    invited_by          TEXT,
    status              TEXT DEFAULT 'active',
    UNIQUE(project_id, user_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS project_registry (
    project_id          TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    db_path             TEXT NOT NULL,
    faiss_index_path    TEXT NOT NULL,
    schema_version      TEXT DEFAULT '1.0',
    db_size_mb          REAL DEFAULT 0,
    last_accessed       TEXT,
    provisioned_at      TEXT DEFAULT (datetime('now')),
    archived_at         TEXT,
    status              TEXT DEFAULT 'active',
    PRIMARY KEY (project_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS project_schema_registry (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    table_name          TEXT NOT NULL,
    column_name         TEXT NOT NULL,
    data_type           TEXT NOT NULL,
    is_required         INTEGER DEFAULT 0,
    is_pii              INTEGER DEFAULT 0,
    description         TEXT,
    registered_at       TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, tenant_id, table_name, column_name)
);

CREATE TABLE IF NOT EXISTS project_sessions (
    session_id          TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    user_id             TEXT NOT NULL,
    mode                TEXT DEFAULT 'query',
    context             TEXT,
    started_at          TEXT DEFAULT (datetime('now')),
    last_active         TEXT DEFAULT (datetime('now')),
    status              TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS agent_action_queue (
    action_id           TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    project_id          TEXT NOT NULL,
    session_id          TEXT,
    agent_dept          TEXT NOT NULL,
    action_type         TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'B_approve',
    title               TEXT NOT NULL,
    description         TEXT,
    reasoning           TEXT,
    evidence            TEXT,
    output_file_path    TEXT,
    priority            TEXT DEFAULT 'medium',
    status              TEXT DEFAULT 'pending',
    created_at          TEXT DEFAULT (datetime('now')),
    reviewed_by         TEXT,
    reviewed_at         TEXT,
    executed_at         TEXT,
    rejection_reason    TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id              TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    session_id          TEXT NOT NULL,
    user_id             TEXT NOT NULL,
    mode                TEXT NOT NULL,
    query               TEXT NOT NULL,
    retrieval_tier      TEXT,
    data_fetched        TEXT,
    output              TEXT,
    confidence          REAL,
    data_gaps           TEXT,
    sources             TEXT,
    llm_tokens          INTEGER,
    duration_ms         INTEGER,
    created_at          TEXT DEFAULT (datetime('now'))
);
"""

# ── Universal tables (created in every project database) ─────────────────────

UNIVERSAL_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS project_metadata (
    project_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT,
    dept_id             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',
    priority            TEXT DEFAULT 'medium',
    owner_name          TEXT,
    start_date          TEXT,
    target_end_date     TEXT,
    budget_total        REAL,
    budget_spent        REAL DEFAULT 0,
    budget_remaining    REAL,
    completion_pct      REAL DEFAULT 0,
    health_status       TEXT DEFAULT 'on_track',
    last_updated        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_kpis (
    kpi_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kpi_name            TEXT NOT NULL,
    category            TEXT DEFAULT 'custom',
    current_value       REAL,
    target_value        REAL,
    unit                TEXT,
    trend               TEXT DEFAULT 'stable',
    status              TEXT DEFAULT 'on_track',
    period              TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_milestones (
    milestone_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    description         TEXT,
    owner               TEXT,
    due_date            TEXT NOT NULL,
    completed_date      TEXT,
    status              TEXT DEFAULT 'pending',
    priority            TEXT DEFAULT 'medium',
    dependencies        TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_risks (
    risk_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    description         TEXT,
    category            TEXT DEFAULT 'general',
    probability         TEXT DEFAULT 'medium',
    impact              TEXT DEFAULT 'medium',
    risk_score          INTEGER DEFAULT 4,
    owner               TEXT,
    mitigation_plan     TEXT,
    status              TEXT DEFAULT 'open',
    identified_at       TEXT DEFAULT (datetime('now')),
    reviewed_at         TEXT
);

CREATE TABLE IF NOT EXISTS project_activity_log (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type          TEXT NOT NULL,
    description         TEXT NOT NULL,
    actor               TEXT,
    old_value           TEXT,
    new_value           TEXT,
    related_entity      TEXT,
    related_id          TEXT,
    logged_at           TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_documents (
    doc_id              TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    doc_type            TEXT NOT NULL DEFAULT 'upload',
    skill_used          TEXT,
    file_path           TEXT,
    file_format         TEXT,
    produced_by         TEXT,
    approved_by         TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    status              TEXT DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS project_notifications (
    notification_id     TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    tenant_id           TEXT NOT NULL,
    title               TEXT NOT NULL,
    message             TEXT NOT NULL,
    severity            TEXT DEFAULT 'medium',
    category            TEXT,
    source              TEXT,
    action_id           TEXT,
    read_by             TEXT,
    read_at             TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    delivered_channels  TEXT DEFAULT '[]',
    dismissed           INTEGER DEFAULT 0
);
"""

# ── Domain-specific tables per department ─────────────────────────────────────

DOMAIN_TABLES = {
    "finance": """
        CREATE TABLE IF NOT EXISTS project_budget_lines (
            line_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            category        TEXT NOT NULL,
            description     TEXT,
            allocated       REAL NOT NULL DEFAULT 0,
            spent           REAL DEFAULT 0,
            remaining       REAL,
            period          TEXT,
            status          TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS project_invoices (
            invoice_id      TEXT PRIMARY KEY,
            vendor          TEXT,
            amount          REAL,
            due_date        TEXT,
            paid            INTEGER DEFAULT 0,
            category        TEXT,
            approved_by     TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS project_expenses (
            expense_id      TEXT PRIMARY KEY,
            category        TEXT,
            description     TEXT,
            amount          REAL,
            submitted_by    TEXT,
            submitted_date  TEXT,
            status          TEXT DEFAULT 'pending',
            approved_by     TEXT
        );
    """,

    "sales": """
        CREATE TABLE IF NOT EXISTS project_pipeline (
            deal_id         TEXT PRIMARY KEY,
            customer_name   TEXT,
            stage           TEXT DEFAULT 'prospecting',
            value           REAL,
            close_date      TEXT,
            owner           TEXT,
            probability     REAL DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS project_targets (
            target_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            metric          TEXT NOT NULL,
            target_value    REAL NOT NULL,
            current_value   REAL DEFAULT 0,
            period          TEXT,
            status          TEXT DEFAULT 'on_track'
        );
        CREATE TABLE IF NOT EXISTS project_activities (
            activity_id     TEXT PRIMARY KEY,
            deal_id         TEXT,
            activity_type   TEXT,
            outcome         TEXT,
            owner           TEXT,
            activity_date   TEXT,
            notes           TEXT
        );
    """,

    "hr": """
        CREATE TABLE IF NOT EXISTS project_headcount (
            hc_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            role_title      TEXT NOT NULL,
            department      TEXT,
            filled          INTEGER DEFAULT 0,
            hire_date       TEXT,
            cost_per_month  REAL,
            status          TEXT DEFAULT 'open'
        );
        CREATE TABLE IF NOT EXISTS project_team_capacity (
            capacity_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            member_name     TEXT,
            role            TEXT,
            allocated_pct   REAL,
            start_date      TEXT,
            end_date        TEXT,
            status          TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS project_training (
            training_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            course_name     TEXT,
            provider        TEXT,
            assignee        TEXT,
            due_date        TEXT,
            completion_date TEXT,
            status          TEXT DEFAULT 'pending'
        );
    """,

    "it": """
        CREATE TABLE IF NOT EXISTS project_tasks (
            task_id         TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            description     TEXT,
            assignee        TEXT,
            status          TEXT DEFAULT 'todo',
            priority        TEXT DEFAULT 'medium',
            due_date        TEXT,
            completed_date  TEXT,
            sprint          TEXT,
            story_points    INTEGER,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS project_deployments (
            deploy_id       TEXT PRIMARY KEY,
            environment     TEXT DEFAULT 'dev',
            version         TEXT,
            status          TEXT DEFAULT 'planned',
            deployed_by     TEXT,
            deployed_at     TEXT,
            rollback_available INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS project_incidents (
            incident_id     TEXT PRIMARY KEY,
            title           TEXT,
            severity        TEXT DEFAULT 'medium',
            status          TEXT DEFAULT 'open',
            reported_by     TEXT,
            resolved_at     TEXT,
            root_cause      TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );
    """,

    "marketing": """
        CREATE TABLE IF NOT EXISTS project_campaigns (
            campaign_id     TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            channel         TEXT,
            budget          REAL,
            spent           REAL DEFAULT 0,
            impressions     INTEGER DEFAULT 0,
            clicks          INTEGER DEFAULT 0,
            conversions     INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'draft',
            start_date      TEXT,
            end_date        TEXT
        );
        CREATE TABLE IF NOT EXISTS project_leads (
            lead_id         TEXT PRIMARY KEY,
            source          TEXT,
            status          TEXT DEFAULT 'new',
            campaign_id     TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS project_content (
            content_id      TEXT PRIMARY KEY,
            title           TEXT,
            content_type    TEXT,
            channel         TEXT,
            status          TEXT DEFAULT 'draft',
            publish_date    TEXT,
            owner           TEXT
        );
    """,

    "legal": """
        CREATE TABLE IF NOT EXISTS project_contracts (
            contract_id     TEXT PRIMARY KEY,
            vendor          TEXT,
            contract_type   TEXT,
            effective_date  TEXT,
            expiry_date     TEXT,
            status          TEXT DEFAULT 'draft',
            owner           TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS project_compliance_items (
            item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            regulation      TEXT,
            requirement     TEXT,
            status          TEXT DEFAULT 'open',
            owner           TEXT,
            due_date        TEXT,
            notes           TEXT
        );
    """,

    "ops": """
        CREATE TABLE IF NOT EXISTS project_processes (
            process_id      TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            owner           TEXT,
            status          TEXT DEFAULT 'active',
            efficiency_pct  REAL,
            last_reviewed   TEXT
        );
        CREATE TABLE IF NOT EXISTS project_inventory (
            sku_id          TEXT PRIMARY KEY,
            product_name    TEXT,
            category        TEXT,
            quantity        INTEGER DEFAULT 0,
            reorder_point   INTEGER,
            unit_cost       REAL,
            status          TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS project_vendors (
            vendor_id       TEXT PRIMARY KEY,
            name            TEXT,
            service         TEXT,
            status          TEXT DEFAULT 'active',
            rating          REAL,
            contract_expiry TEXT
        );
    """,

    "procurement": """
        CREATE TABLE IF NOT EXISTS project_purchase_orders (
            po_id           TEXT PRIMARY KEY,
            supplier        TEXT,
            amount          REAL,
            status          TEXT DEFAULT 'draft',
            raised_date     TEXT,
            delivery_date   TEXT,
            category        TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS project_suppliers (
            supplier_id     TEXT PRIMARY KEY,
            name            TEXT,
            category        TEXT,
            status          TEXT DEFAULT 'active',
            rating          REAL,
            spend_ytd       REAL DEFAULT 0
        );
    """,

    "rd": """
        CREATE TABLE IF NOT EXISTS project_experiments (
            exp_id          TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            hypothesis      TEXT,
            status          TEXT DEFAULT 'planned',
            outcome         TEXT,
            started_date    TEXT,
            completed_date  TEXT
        );
        CREATE TABLE IF NOT EXISTS project_innovations (
            idea_id         TEXT PRIMARY KEY,
            title           TEXT,
            submitter       TEXT,
            stage           TEXT DEFAULT 'ideation',
            feasibility     REAL,
            status          TEXT DEFAULT 'under_review',
            created_at      TEXT DEFAULT (datetime('now'))
        );
    """,

    "customer_success": """
        CREATE TABLE IF NOT EXISTS project_accounts (
            account_id      TEXT PRIMARY KEY,
            company_name    TEXT,
            health_score    REAL,
            arr             REAL,
            tier            TEXT DEFAULT 'standard',
            renewal_date    TEXT,
            risk_flag       INTEGER DEFAULT 0,
            csm_owner       TEXT
        );
        CREATE TABLE IF NOT EXISTS project_support_tickets (
            ticket_id       TEXT PRIMARY KEY,
            account_id      TEXT,
            subject         TEXT,
            priority        TEXT DEFAULT 'medium',
            status          TEXT DEFAULT 'open',
            created_date    TEXT DEFAULT (datetime('now')),
            resolved_date   TEXT,
            csat_score      REAL
        );
    """,
}

# ── Universal schema columns (for project_schema_registry) ───────────────────

UNIVERSAL_SCHEMA_COLUMNS = {
    "project_metadata": [
        ("project_id", "TEXT", True, False, "Unique project identifier"),
        ("name", "TEXT", True, False, "Project name"),
        ("description", "TEXT", False, False, "Project description"),
        ("dept_id", "TEXT", True, False, "Owning department"),
        ("status", "TEXT", True, False, "Project status"),
        ("budget_total", "REAL", False, False, "Total budget allocated"),
        ("budget_spent", "REAL", False, False, "Total budget spent so far"),
        ("completion_pct", "REAL", False, False, "Completion percentage 0-100"),
        ("health_status", "TEXT", False, False, "on_track / at_risk / off_track"),
    ],
    "project_kpis": [
        ("kpi_name", "TEXT", True, False, "Name of the KPI"),
        ("current_value", "REAL", False, False, "Current measured value"),
        ("target_value", "REAL", False, False, "Target value"),
        ("unit", "TEXT", False, False, "Unit of measurement"),
        ("status", "TEXT", False, False, "on_track / at_risk / off_track"),
    ],
    "project_milestones": [
        ("name", "TEXT", True, False, "Milestone name"),
        ("due_date", "TEXT", True, False, "Due date (ISO format)"),
        ("status", "TEXT", False, False, "pending / in_progress / completed / delayed"),
        ("owner", "TEXT", False, False, "Responsible person"),
    ],
    "project_risks": [
        ("title", "TEXT", True, False, "Risk title"),
        ("probability", "TEXT", False, False, "low / medium / high"),
        ("impact", "TEXT", False, False, "low / medium / high / critical"),
        ("risk_score", "INTEGER", False, False, "1-9 risk score"),
        ("status", "TEXT", False, False, "open / mitigated / accepted / closed"),
    ],
}


class ProjectProvisioner:
    """
    Automatically provisions everything needed for a new project:
    - Platform tables in rapid.db (one-time per install)
    - Project database with universal + domain tables
    - FAISS index directory
    - Registry entries
    - Schema registry entries
    """

    def __init__(self, platform_db_path: str = config.DB_PATH):
        self._platform_db = platform_db_path
        Path(platform_db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_platform_tables()

    # ── Platform table init ────────────────────────────────────────────────────

    def _init_platform_tables(self):
        """Create all project-related platform tables in rapid.db."""
        conn = self._connect(self._platform_db)
        try:
            conn.executescript(PLATFORM_TABLES_SQL)
            conn.commit()
            logger.info("[ProjectProvisioner] Platform tables initialized")
        finally:
            conn.close()

    # ── Project provisioning ──────────────────────────────────────────────────

    def provision(
        self,
        project_id: str,
        tenant_id: str,
        name: str,
        dept_id: str,
        owner_user_id: str,
        description: str = None,
        project_type: str = "single_dept",
        priority: str = "medium",
        start_date: str = None,
        target_end_date: str = None,
        budget_total: float = None,
        tags: list = None,
    ) -> dict:
        """
        Full project provisioning pipeline.
        Returns the project registry entry.
        """
        logger.info(f"[ProjectProvisioner] Provisioning project {project_id} ({name})")

        # Step 1: Create the project record in platform DB
        self._create_project_record(
            project_id=project_id,
            tenant_id=tenant_id,
            name=name,
            dept_id=dept_id,
            owner_user_id=owner_user_id,
            description=description,
            project_type=project_type,
            priority=priority,
            start_date=start_date,
            target_end_date=target_end_date,
            budget_total=budget_total,
            tags=tags,
        )

        # Step 2: Determine paths
        db_path = self._get_project_db_path(tenant_id, project_id)
        faiss_path = self._get_faiss_path(tenant_id, project_id)

        # Step 3: Create project database
        self._create_project_db(
            db_path=db_path,
            project_id=project_id,
            name=name,
            dept_id=dept_id,
            owner_user_id=owner_user_id,
            budget_total=budget_total,
            start_date=start_date,
            target_end_date=target_end_date,
        )

        # Step 4: Create FAISS index directory
        Path(faiss_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"[ProjectProvisioner] FAISS index dir created: {faiss_path}")

        # Step 5: Register in project_registry
        self._register_project(
            project_id=project_id,
            tenant_id=tenant_id,
            db_path=db_path,
            faiss_path=faiss_path,
        )

        # Step 6: Register schema
        self._register_schema(project_id, tenant_id, dept_id)

        # Step 7: Log the provisioning event in the project DB
        self._log_activity(
            db_path=db_path,
            event_type="project_provisioned",
            description=f"Project '{name}' created and provisioned",
            actor=owner_user_id,
        )

        logger.info(f"[ProjectProvisioner] ✅ Project {project_id} fully provisioned")
        return self.get_registry_entry(project_id, tenant_id)

    # ── Internal steps ────────────────────────────────────────────────────────

    def _create_project_record(self, **kwargs):
        tags = kwargs.get("tags")
        tags_json = json.dumps(tags) if tags else None
        conn = self._connect(self._platform_db)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO projects
                    (project_id, tenant_id, name, description, project_type,
                     primary_dept_id, status, priority, owner_user_id,
                     start_date, target_end_date, budget_total, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kwargs["project_id"], kwargs["tenant_id"], kwargs["name"],
                    kwargs.get("description"), kwargs.get("project_type", "single_dept"),
                    kwargs["dept_id"], kwargs.get("priority", "medium"),
                    kwargs["owner_user_id"],
                    kwargs.get("start_date"), kwargs.get("target_end_date"),
                    kwargs.get("budget_total"), tags_json,
                    datetime.utcnow().isoformat(), datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _create_project_db(
        self,
        db_path: str,
        project_id: str,
        name: str,
        dept_id: str,
        owner_user_id: str,
        budget_total: float = None,
        start_date: str = None,
        target_end_date: str = None,
    ):
        """Create the project's own SQLite DB with universal + domain tables."""
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            # Universal tables
            conn.executescript(UNIVERSAL_TABLES_SQL)

            # Domain-specific tables for the department
            domain_sql = DOMAIN_TABLES.get(dept_id, "")
            if domain_sql:
                conn.executescript(domain_sql)
                logger.info(f"[ProjectProvisioner] Domain tables created for dept '{dept_id}'")
            else:
                logger.info(f"[ProjectProvisioner] No domain tables for dept '{dept_id}' — universal only")

            # Seed project_metadata
            conn.execute(
                """
                INSERT OR IGNORE INTO project_metadata
                    (project_id, name, dept_id, status, owner_name,
                     start_date, target_end_date, budget_total,
                     budget_remaining, last_updated)
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id, name, dept_id, owner_user_id,
                    start_date, target_end_date, budget_total,
                    budget_total,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            logger.info(f"[ProjectProvisioner] Project DB created at {db_path}")
        finally:
            conn.close()

    def _register_project(
        self,
        project_id: str,
        tenant_id: str,
        db_path: str,
        faiss_path: str,
    ):
        conn = self._connect(self._platform_db)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO project_registry
                    (project_id, tenant_id, db_path, faiss_index_path,
                     status, provisioned_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (project_id, tenant_id, db_path, faiss_path,
                 datetime.utcnow().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def _register_schema(self, project_id: str, tenant_id: str, dept_id: str):
        """Register all universal columns in project_schema_registry."""
        conn = self._connect(self._platform_db)
        try:
            for table, columns in UNIVERSAL_SCHEMA_COLUMNS.items():
                for col_name, data_type, is_req, is_pii, desc in columns:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO project_schema_registry
                            (project_id, tenant_id, table_name, column_name,
                             data_type, is_required, is_pii, description, registered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (project_id, tenant_id, table, col_name,
                         data_type, int(is_req), int(is_pii), desc,
                         datetime.utcnow().isoformat()),
                    )
            conn.commit()
        finally:
            conn.close()

    def _log_activity(self, db_path: str, event_type: str, description: str, actor: str):
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                INSERT INTO project_activity_log
                    (event_type, description, actor, logged_at)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, description, actor, datetime.utcnow().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[ProjectProvisioner] Activity log failed: {e}")

    # ── Registry lookups ──────────────────────────────────────────────────────

    def get_registry_entry(self, project_id: str, tenant_id: str) -> Optional[dict]:
        conn = self._connect(self._platform_db)
        try:
            row = conn.execute(
                "SELECT * FROM project_registry WHERE project_id = ? AND tenant_id = ?",
                (project_id, tenant_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_project_db_path(self, project_id: str, tenant_id: str) -> Optional[str]:
        entry = self.get_registry_entry(project_id, tenant_id)
        return entry["db_path"] if entry else None

    def touch_last_accessed(self, project_id: str, tenant_id: str):
        conn = self._connect(self._platform_db)
        try:
            conn.execute(
                "UPDATE project_registry SET last_accessed = ? WHERE project_id = ? AND tenant_id = ?",
                (datetime.utcnow().isoformat(), project_id, tenant_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Path helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_project_db_path(tenant_id: str, project_id: str) -> str:
        return str(Path("data/db/projects") / tenant_id / f"{project_id}.db")

    @staticmethod
    def _get_faiss_path(tenant_id: str, project_id: str) -> str:
        return str(Path("data/faiss/projects") / tenant_id / project_id)

    def _connect(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path, timeout=config.DB_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


# ── Singleton ─────────────────────────────────────────────────────────────────

_provisioner: Optional[ProjectProvisioner] = None


def get_project_provisioner() -> ProjectProvisioner:
    global _provisioner
    if _provisioner is None:
        _provisioner = ProjectProvisioner()
    return _provisioner
