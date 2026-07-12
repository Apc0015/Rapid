from __future__ import annotations
"""
DBMaster — manages all database query operations.

D1  Intent extraction       (LLM → IntentObject — no SQL yet)
D2  Schema reading          (deterministic — no LLM, no hallucination)
D3  SQL generation          (LLM, grounded in real schema with table+column descriptions)
D4  Validation + execution  (AST SELECT-only check, per-dept DB connection)
D5  Governance + NL + DESTROY RAW DATA  (firewall — raw rows never leave)

Per-department DB support:
  Each dept can have its own SQLite file or external DB (PostgreSQL/MySQL).
  Configured via DeptConfig. Falls back to shared rapid.db if not configured.
"""

import json
import logging
import os
import re
import sqlite3
from contextvars import ContextVar
from pathlib import Path
from typing import Any, List, Dict, Optional

import config
from models.intent_object import IntentObject

logger = logging.getLogger(__name__)


# ── Per-request tenant context ────────────────────────────────────────────────
# Seeded from the JWT's ``tenant_id`` claim inside main.py's ``_run_query``.
# Each asyncio Task inherits its own copy; changing it in one coroutine does
# not bleed into any other concurrent request.

_current_tenant: ContextVar[str] = ContextVar("rapid_tenant_id", default="default")


def set_current_tenant(tenant_id: str) -> None:
    """Bind the active tenant for this async task.
    Must be called once per request before any DB access.
    """
    _current_tenant.set(tenant_id or "default")


def get_current_tenant() -> str:
    """Return the tenant_id bound to the current async task (default: 'default')."""
    return _current_tenant.get()


class SecurityException(Exception):
    pass


class DBMaster:

    FORBIDDEN_KEYWORDS = {
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
        "CREATE", "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
    }
    SYSTEM_TABLES = {"sqlite_master", "sqlite_sequence", "sqlite_stat1"}

    def __init__(self, db_path: str = config.DB_PATH):
        self._default_db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._schema_cache: Dict[str, dict] = {}
        self._load_all_schemas()

    # ── D1: Intent extraction ─────────────────────────────────────────────────

    async def extract_intent(self, query: str) -> IntentObject:
        """
        Use LLM to extract structured data intent — NOT SQL.
        Returns IntentObject describing what data is needed.
        """
        from infrastructure.llm_client import get_llm
        llm = get_llm()
        system = (
            "You extract structured data intent from natural language queries. "
            "Return ONLY valid JSON with these exact fields: "
            '{"fields_needed": ["field1", "field2"], '
            '"filters": {"column": "value"}, '
            '"aggregation": "AVG|SUM|COUNT|null", '
            '"sort": "column ASC|DESC or null", '
            '"limit": 100}. '
            "Do NOT generate SQL. Describe only what data is needed."
        )
        try:
            result = await llm.json_complete(query, system=system)
            return IntentObject(
                fields_needed=result.get("fields_needed", []),
                filters=result.get("filters", {}),
                aggregation=result.get("aggregation"),
                sort=result.get("sort"),
                limit=result.get("limit", 100),
                raw_query=query,
            )
        except Exception as e:
            logger.warning(f"D1 intent extraction failed ({e}), using raw query")
            return IntentObject(
                fields_needed=[], filters={}, aggregation=None,
                sort=None, limit=100, raw_query=query,
            )

    # ── D2: Schema reading ────────────────────────────────────────────────────

    def read_schema(self, dept_tag: str) -> dict:
        """
        Read pre-cached schema for this department.
        NEVER uses LLM — deterministic to prevent hallucinated column names.
        """
        if dept_tag not in self._schema_cache:
            # Try to load schema from dept-specific DB dynamically
            db_path = self._get_db_path(dept_tag)
            if db_path and Path(db_path).exists():
                dynamic = self._introspect_db(db_path, dept_tag=dept_tag)
                if dynamic:
                    self._schema_cache[dept_tag] = dynamic
                    return dynamic
            raise ValueError(f"No schema found for department: {dept_tag}")
        return self._schema_cache[dept_tag]

    # ── D3: SQL generation (grounded in real schema) ──────────────────────────

    async def generate_sql(
        self,
        intent: IntentObject,
        schema: dict,
        user_permissions: dict,
        error_context: Optional[str] = None,
        prev_sql: Optional[str] = None,
    ) -> str:
        """
        Generate a safe SELECT query grounded in the ACTUAL schema.
        When error_context + prev_sql are provided (retry path), the previous
        failed SQL and its validation error are included so the LLM can correct.
        """
        from infrastructure.llm_client import get_llm
        llm = get_llm()

        permitted_schema = self._apply_permission_to_schema(schema, user_permissions)
        schema_description = _format_schema_for_prompt(permitted_schema)

        system = (
            "You generate safe, read-only SQLite SELECT queries.\n"
            "STRICT RULES — any violation causes the query to be rejected:\n"
            "1. Only SELECT statements are allowed.\n"
            "2. ONLY reference table and column names EXACTLY as listed in the schema below.\n"
            "3. Do NOT invent, guess, or paraphrase table/column names.\n"
            "4. No INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE.\n"
            "5. No system tables (sqlite_master, etc).\n"
            "6. Always include LIMIT (max 500).\n"
            "7. Return ONLY the raw SQL string — no markdown, no explanation.\n\n"
            f"AVAILABLE SCHEMA:\n{schema_description}"
        )

        correction_block = ""
        if error_context and prev_sql:
            correction_block = (
                f"\n\nPREVIOUS ATTEMPT FAILED — fix the error:\n"
                f"SQL tried:\n{prev_sql}\n"
                f"Validation error: {error_context}\n"
                f"Generate a corrected SQL that avoids this error."
            )

        sql = await llm.complete(
            f"Data intent: {json.dumps(intent.__dict__, default=str)}\n"
            f"Original question: {intent.raw_query}"
            + correction_block,
            system=system,
        )
        sql = sql.strip()
        for fence in ("```sql", "```SQL", "```"):
            sql = sql.replace(fence, "")
        return sql.strip()

    # ── D4: Validation + execution ────────────────────────────────────────────

    def validate_sql(self, sql: str, schema: dict) -> str:
        """Static analysis before execution. Raises SecurityException on violation."""
        upper = sql.strip().upper()

        if not upper.startswith("SELECT"):
            raise SecurityException(f"Non-SELECT query rejected: {sql[:80]}")

        for kw in self.FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{kw}\b", upper):
                raise SecurityException(f"Forbidden keyword '{kw}' in query")

        for sys_table in self.SYSTEM_TABLES:
            if sys_table.lower() in sql.lower():
                raise SecurityException(f"System table reference rejected: {sys_table}")

        # Validate that all referenced tables exist in schema
        referenced = re.findall(r'\bFROM\s+(\w+)|\bJOIN\s+(\w+)', sql, re.IGNORECASE)
        referenced_tables = {t for pair in referenced for t in pair if t}
        unknown_tables = referenced_tables - set(schema.keys())
        if unknown_tables:
            raise SecurityException(f"Query references table(s) not in permitted schema: {unknown_tables}")

        return sql

    async def execute_query(self, sql: str, dept_tag: str = "") -> List[Dict[str, Any]]:
        """
        Execute validated SQL.
        Routes to PostgreSQL when DATABASE_URL is set, otherwise SQLite.
        """
        db_url = os.getenv("DATABASE_URL", config.DATABASE_URL)
        if db_url and db_url.startswith(("postgresql", "postgres")):
            return await self._execute_postgres(sql, db_url)
        return await self._execute_sqlite(sql, dept_tag)

    async def _execute_sqlite(self, sql: str, dept_tag: str) -> List[Dict[str, Any]]:
        # Dept-specific path takes priority; fall back to the tenant's own DB file.
        tenant_db = self._get_tenant_db_path(get_current_tenant())
        db_path = self._get_db_path(dept_tag) or tenant_db
        if not Path(db_path).exists():
            logger.warning(f"DB not found at {db_path} for dept={dept_tag}, using tenant DB")
            db_path = tenant_db
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            timeout=config.DB_TIMEOUT_SECONDS,
        )
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    async def _execute_postgres(self, sql: str, db_url: str) -> List[Dict[str, Any]]:
        """Read-only PostgreSQL execution via asyncpg."""
        try:
            import asyncpg
        except ImportError:
            raise RuntimeError(
                "asyncpg is required for PostgreSQL support. "
                "Install it: pip install asyncpg"
            )
        conn = await asyncpg.connect(db_url, timeout=config.DB_TIMEOUT_SECONDS)
        try:
            rows = await conn.fetch(sql)
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    def verify_results(self, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not raw_results:
            return []
        non_null = [r for r in raw_results if any(v is not None for v in r.values())]
        if not non_null:
            logger.warning("All result rows contain only null values")
        return raw_results

    # ── D5: Governance + NL conversion + destroy ──────────────────────────────

    def apply_governance(
        self, raw_results: List[Dict[str, Any]], user_permissions: dict, dept_tag: str
    ) -> tuple[List[Dict[str, Any]], List[dict]]:
        """Apply Constitution rules column-by-column."""
        if not raw_results:
            return [], []

        col_rules = self._get_column_rules(dept_tag, user_permissions)
        governed, governance_log = [], []

        # Deny-by-default: columns with no explicit rule follow the constitution's
        # Article 0 default_action (BLOCK unless overridden). Single source of truth
        # is the GovernanceFilter so the DB path and the agent-output path agree.
        from agents.system.governance_filter import get_governance
        default_action = get_governance().default_action

        for row in raw_results:
            new_row = {}
            for col, val in row.items():
                rule = col_rules.get(col, default_action)
                if rule == "ALLOW":
                    new_row[col] = val
                    governance_log.append({"col": col, "action": "ALLOW"})
                elif rule == "ANONYMIZE":
                    new_row[col] = f"[ANONYMIZED:{col}]"
                    governance_log.append({"col": col, "action": "ANONYMIZE"})
                elif rule == "BLOCK":
                    governance_log.append({"col": col, "action": "BLOCK", "severity": "HIGH"})
                elif rule.startswith("ALLOW_"):
                    required_role = rule.split("_", 1)[1].lower()
                    user_role = (user_permissions.get("role") or "").lower()
                    if user_role in (required_role, "admin"):
                        new_row[col] = val
                        governance_log.append({"col": col, "action": "ALLOW_ROLE"})
                    else:
                        governance_log.append({"col": col, "action": "BLOCK_ROLE", "severity": "MEDIUM"})
            governed.append(new_row)

        return governed, governance_log

    async def convert_to_nl(self, governed_results: List[Dict[str, Any]], query: str) -> str:
        """Convert governed rows to NL. Last step before raw data is destroyed."""
        from infrastructure.llm_client import get_llm
        llm = get_llm()
        if not governed_results:
            return "No data was found matching your query."
        system = (
            "Convert structured data results into a clear, professional natural language answer. "
            "For any field marked [ANONYMIZED:fieldname], describe it as a team/department aggregate. "
            "Be factual and concise. Do not add information not present in the data."
        )
        prompt = (
            f"Original question: {query}\n\n"
            f"Data results: {json.dumps(governed_results, default=str)}"
        )
        return await llm.complete(prompt, system=system)

    def destroy_raw_data(self, *args):
        """Firewall: explicitly destroy all raw data references."""
        for arg in args:
            if isinstance(arg, list):
                arg.clear()
            elif isinstance(arg, dict):
                arg.clear()
        import gc
        gc.collect()
        logger.debug("Raw data destroyed — DB firewall applied")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_db_path(self, dept_tag: str) -> Optional[str]:
        """Return dept-specific SQLite path if configured. Returns None for PostgreSQL."""
        db_url = os.getenv("DATABASE_URL", config.DATABASE_URL)
        if db_url and db_url.startswith(("postgresql", "postgres")):
            return None  # PostgreSQL path — no file path needed
        if not dept_tag:
            return None
        try:
            from infrastructure.dept_config import get_dept_config
            cfg = get_dept_config().get_db(dept_tag)
            if cfg.get("enabled") and cfg.get("type") == "sqlite":
                return cfg.get("path") or f"data/db/{dept_tag}.db"
        except Exception:
            pass
        return None

    def _get_tenant_db_path(self, tenant_id: str) -> str:
        """Return the SQLite file path for a given tenant.

        The *default* tenant (single-org deployments) reuses the existing
        ``rapid.db`` so no data migration is needed.  All other tenants get
        their own isolated file under ``data/db/{tenant_id}.db``, inside the
        same directory that the backup system already covers.
        """
        if not tenant_id or tenant_id == "default":
            return self._default_db_path
        tenant_db = Path(self._default_db_path).parent / f"{tenant_id}.db"
        tenant_db.parent.mkdir(parents=True, exist_ok=True)
        return str(tenant_db)

    def _load_all_schemas(self):
        # Try PostgreSQL introspection first when DATABASE_URL is configured
        db_url = os.getenv("DATABASE_URL", config.DATABASE_URL)
        if db_url and db_url.startswith(("postgresql", "postgres")):
            pg_schema = self._introspect_postgres_sync(db_url)
            if pg_schema:
                self._schema_cache.update(pg_schema)
                logger.info(f"[PostgreSQL] Loaded schemas: {list(pg_schema.keys())}")
                return

        schema_dir = Path(config.SCHEMA_DIR)
        if not schema_dir.exists():
            return
        for schema_file in schema_dir.glob("*.json"):
            dept_tag = schema_file.stem
            try:
                with open(schema_file) as f:
                    self._schema_cache[dept_tag] = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load schema {schema_file}: {e}")
        logger.info(f"Loaded schemas for: {list(self._schema_cache.keys())}")

    def _introspect_postgres_sync(self, db_url: str) -> Dict[str, dict]:
        """
        Synchronous PostgreSQL schema introspection (runs once at startup).
        Groups tables by dept_tag prefix (e.g. 'finance_revenue' → 'finance').
        Falls back to a flat schema keyed by table name if no prefix convention.
        """
        try:
            import psycopg2  # sync driver — only used at startup
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            logger.warning(f"[PostgreSQL] Schema introspection failed: {e}")
            return {}

        tables: Dict[str, List[str]] = {}
        for table, column, _ in rows:
            tables.setdefault(table, []).append(column)

        # Group by dept prefix (table name before first underscore), else use table name as dept
        schemas: Dict[str, dict] = {}
        for table, columns in tables.items():
            dept_key = table.split("_")[0] if "_" in table else table
            schemas.setdefault(dept_key, {})
            schemas[dept_key][table] = {
                "columns": columns,
                "description": f"{table} table",
            }
        return schemas

    def _introspect_db(self, db_path: str, dept_tag: str = "") -> dict:
        """Dynamically read schema from a SQLite DB."""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            schema = {}
            for table in tables:
                col_cursor = conn.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in col_cursor.fetchall()]
                schema[table] = {"columns": columns, "description": f"{table} table"}
            conn.close()
        except sqlite3.OperationalError as e:
            logger.error(
                f"DBMaster: schema introspection failed for dept='{dept_tag}': {e!r} "
                "— DB may be missing or corrupt"
            )
            return {}
        except Exception as e:
            logger.error(f"DBMaster: unexpected error during schema introspection: {e!r}")
            return {}
        if not schema and dept_tag:
            logger.warning(
                f"DBMaster: empty schema for dept='{dept_tag}' — DB queries will return no results"
            )
        return schema

    def _apply_permission_to_schema(self, schema: dict, user_permissions: dict) -> dict:
        """
        Filter schema columns based on:
        1. Column-level sensitivity flags embedded in the rich schema (block/anonymize/allow)
        2. Constitution column_rules from user_permissions (BLOCK/ALLOW/ANONYMIZE)

        Supports both old list format {"columns": [...]} and new rich dict format
        {"columns": {"col": {"type":..., "sensitivity":...}}}.
        """
        dept_tag  = user_permissions.get("dept_tag", "")
        col_rules = self._get_column_rules(dept_tag, user_permissions)
        role      = user_permissions.get("role", "employee")
        filtered  = {}

        for table, meta in schema.items():
            raw_cols = meta.get("columns", [])
            row_limit = meta.get("row_limit", 500)

            # ── Rich format: columns is a dict ───────────────────────────────
            if isinstance(raw_cols, dict):
                permitted = {}
                for col_name, col_meta in raw_cols.items():
                    schema_sensitivity = col_meta.get("sensitivity", "allow").upper()
                    constitution_rule  = col_rules.get(col_name, "ALLOW").upper()

                    # BLOCK wins from either source
                    if schema_sensitivity == "BLOCK" or constitution_rule == "BLOCK":
                        continue
                    # ANONYMIZE from either source → mark it
                    anonymize = (schema_sensitivity == "ANONYMIZE" or
                                 constitution_rule == "ANONYMIZE")
                    # Managers and above skip anonymization
                    if anonymize and role in ("manager", "dept_head", "division_head",
                                              "c_suite", "ceo", "admin"):
                        anonymize = False
                    permitted[col_name] = {**col_meta, "anonymize": anonymize}

                if permitted:
                    filtered[table] = {
                        "columns": permitted,
                        "description": meta.get("description", ""),
                        "row_limit": row_limit,
                    }

            # ── Legacy list format: columns is a list ─────────────────────
            else:
                permitted_cols = [
                    col for col in raw_cols
                    if col_rules.get(col, "ALLOW").upper() != "BLOCK"
                ]
                if permitted_cols:
                    filtered[table] = {
                        "columns": permitted_cols,
                        "description": meta.get("description", ""),
                        "row_limit": row_limit,
                    }

        return filtered

    def _get_column_rules(self, dept_tag: str, user_permissions: dict) -> dict:
        return user_permissions.get("column_rules", {})

    def get_writeable_connection(self, dept_tag: str = "") -> sqlite3.Connection:
        """Writable connection — only for seeding, not exposed via API."""
        db_path = self._get_db_path(dept_tag) or self._get_tenant_db_path(get_current_tenant())
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(db_path)


# ── Schema prompt formatter ───────────────────────────────────────────────────

def _format_schema_for_prompt(schema: dict) -> str:
    """
    Build a rich, structured schema description for the D3 LLM prompt.
    Supports both the new rich dict format and the legacy list format.

    Rich format output example:
        Table: financials  — Monthly financial performance  [max 200 rows]
          revenue       (real)    Total revenue in USD
          gross_margin  (real)    Gross margin percentage
          executive_comp  [ANONYMIZED]

    This grounds the LLM in exact column names, types, and descriptions
    so it cannot hallucinate schema elements.
    """
    lines = []
    for table, meta in schema.items():
        desc      = meta.get("description", "")
        row_limit = meta.get("row_limit", 500)
        raw_cols  = meta.get("columns", [])

        lines.append(f"Table: {table}  — {desc}  [max {row_limit} rows]")

        # ── Rich dict format ─────────────────────────────────────────────────
        if isinstance(raw_cols, dict):
            for col_name, col_meta in raw_cols.items():
                col_type = col_meta.get("type", "text")
                col_desc = col_meta.get("description", "")
                col_ex   = col_meta.get("example", "")
                anonymize = col_meta.get("anonymize", False)

                if anonymize:
                    lines.append(f"  {col_name:<24} ({col_type})  {col_desc}  [ANONYMIZED IN OUTPUT]")
                elif col_ex:
                    lines.append(f"  {col_name:<24} ({col_type})  {col_desc}  e.g. {col_ex}")
                else:
                    lines.append(f"  {col_name:<24} ({col_type})  {col_desc}")

        # ── Legacy list format ───────────────────────────────────────────────
        else:
            lines.append(f"  Columns: {', '.join(raw_cols)}")

        lines.append("")  # blank line between tables

    return "\n".join(lines) if lines else "No tables available."


# ── Singleton ─────────────────────────────────────────────────────────────────

_db_master: Optional[DBMaster] = None


def get_db_master() -> DBMaster:
    global _db_master
    if _db_master is None:
        _db_master = DBMaster()
    return _db_master
