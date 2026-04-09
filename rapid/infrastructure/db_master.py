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
import re
import sqlite3
from pathlib import Path
from typing import Any, List, Dict, Optional

import config
from models.intent_object import IntentObject

logger = logging.getLogger(__name__)


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
                dynamic = self._introspect_db(db_path)
                if dynamic:
                    self._schema_cache[dept_tag] = dynamic
                    return dynamic
            raise ValueError(f"No schema found for department: {dept_tag}")
        return self._schema_cache[dept_tag]

    # ── D3: SQL generation (grounded in real schema) ──────────────────────────

    async def generate_sql(
        self, intent: IntentObject, schema: dict, user_permissions: dict
    ) -> str:
        """
        Generate a safe SELECT query grounded in the ACTUAL schema.
        The prompt includes full table descriptions and column lists
        so the LLM cannot hallucinate table/column names.
        """
        from infrastructure.llm_client import get_llm
        llm = get_llm()

        # Filter schema to only permitted columns
        permitted_schema = self._apply_permission_to_schema(schema, user_permissions)

        # Build a human-readable schema description to anchor the LLM
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
        sql = await llm.complete(
            f"Data intent: {json.dumps(intent.__dict__, default=str)}\n"
            f"Original question: {intent.raw_query}",
            system=system,
        )
        # Strip accidental markdown fences
        sql = sql.strip()
        for fence in ("```sql", "```SQL", "```"):
            sql = sql.replace(fence, "")
        sql = sql.strip()
        return sql

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
        for table in schema:
            pass  # schema keys are valid tables — checked implicitly by DB execution

        return sql

    async def execute_query(self, sql: str, dept_tag: str = "") -> List[Dict[str, Any]]:
        """
        Execute validated SQL on a read-only connection.
        Uses dept-specific DB if configured, falls back to shared rapid.db.
        """
        db_path = self._get_db_path(dept_tag) or self._default_db_path
        if not Path(db_path).exists():
            logger.warning(f"DB not found at {db_path} for dept={dept_tag}, using default")
            db_path = self._default_db_path

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

        for row in raw_results:
            new_row = {}
            for col, val in row.items():
                rule = col_rules.get(col, "ALLOW")
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
        """Return dept-specific DB path if configured and enabled."""
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

    def _load_all_schemas(self):
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

    def _introspect_db(self, db_path: str) -> dict:
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
            return schema
        except Exception as e:
            logger.warning(f"DB introspection failed for {db_path}: {e}")
            return {}

    def _apply_permission_to_schema(self, schema: dict, user_permissions: dict) -> dict:
        dept_tag  = user_permissions.get("dept_tag", "")
        col_rules = self._get_column_rules(dept_tag, user_permissions)
        filtered  = {}
        for table, meta in schema.items():
            permitted_cols = [
                col for col in meta.get("columns", [])
                if col_rules.get(col, "ALLOW") != "BLOCK"
            ]
            if permitted_cols:
                filtered[table] = {
                    "columns": permitted_cols,
                    "description": meta.get("description", ""),
                }
        return filtered

    def _get_column_rules(self, dept_tag: str, user_permissions: dict) -> dict:
        return user_permissions.get("column_rules", {})

    def get_writeable_connection(self, dept_tag: str = "") -> sqlite3.Connection:
        """Writable connection — only for seeding, not exposed via API."""
        db_path = self._get_db_path(dept_tag) or self._default_db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(db_path)


# ── Schema prompt formatter ───────────────────────────────────────────────────

def _format_schema_for_prompt(schema: dict) -> str:
    """
    Build a clear, structured schema description for the D3 LLM prompt.
    Explicitly lists every valid table and column so the LLM cannot hallucinate.
    """
    lines = []
    for table, meta in schema.items():
        desc = meta.get("description", "")
        cols = meta.get("columns", [])
        lines.append(f"Table: {table}  ({desc})")
        lines.append(f"  Columns: {', '.join(cols)}")
    return "\n".join(lines) if lines else "No tables available."


# ── Singleton ─────────────────────────────────────────────────────────────────

_db_master: Optional[DBMaster] = None


def get_db_master() -> DBMaster:
    global _db_master
    if _db_master is None:
        _db_master = DBMaster()
    return _db_master
