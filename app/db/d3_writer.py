"""
D3 — Query Writer

Writes a SELECT-only SQL query from schema mapping and information requirements.
Safety is enforced at the code level using sqlparse AST parsing, not instructions.

IMPORTANT: sanitize_query() uses AST-level checks, not string matching.
"""

import json
import logging
from dataclasses import dataclass

import sqlparse
import sqlparse.tokens as sqltokens

from app.db.d1_extractor import InformationRequirements
from app.db.d2_schema import SchemaMapping
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)

MAX_SAFE_ROWS = 10_000


class QuerySafetyError(Exception):
    """Raised when a query contains forbidden operations."""


@dataclass
class SQLPlan:
    sql: str                        # Sanitized SELECT SQL
    columns_requested: list         # For D5 to cross-reference with governance
    estimated_row_count: int = 100  # Conservative estimate for LIMIT injection
    explanation: str = ""           # One-sentence explanation for audit


class QueryWriter:
    """D3 — generates SELECT-only SQL."""

    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager

    async def write(
        self,
        mapping: SchemaMapping,
        requirements: InformationRequirements,
    ) -> SQLPlan:
        if not mapping.relevant_tables or not mapping.schema_summary:
            raise ValueError("D3: no schema mapping available to write query")

        concepts = "\n".join(f"- {c}" for c in requirements.data_concepts)
        filters = "\n".join(f"- {f}" for f in requirements.filters) or "none"
        aggs = ", ".join(requirements.aggregations) or "none"

        prompt = f"""Write a SQL SELECT query for the following requirements.

Database schema ({mapping.dialect_hint}):
{mapping.schema_summary}

Data needed:
{concepts}

Filters: {filters}
Aggregations needed: {aggs}
Sort preference: {requirements.sort_preference or "none"}
Row limit hint: {requirements.row_limit_hint}

Rules:
- Write ONLY a SELECT statement (no INSERT/UPDATE/DELETE/DROP/CREATE)
- Use only the table and column names shown in the schema above
- Include appropriate WHERE clauses for the filters
- Include LIMIT clause
- Return ONLY valid JSON:

{{
  "sql": "SELECT ...",
  "columns_used": ["table.column", ...],
  "explanation": "one sentence"
}}"""

        sql = ""
        columns_used = []
        explanation = ""
        try:
            raw = await self.llm.chat(prompt, max_tokens=800, temperature=0.0)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                sql = data.get("sql", "").strip()
                columns_used = data.get("columns_used", [])
                explanation = data.get("explanation", "")
        except Exception as e:
            logger.warning("D3 LLM call failed: %s", e)
            raise ValueError(f"D3 could not generate SQL: {e}") from e

        if not sql:
            raise ValueError("D3: LLM returned empty SQL")

        # Technical safety enforcement (AST-level, not instruction-level)
        sql = self.sanitize_query(sql)

        # Auto-inject LIMIT if missing or too large
        sql = self._enforce_limit(sql, requirements.row_limit_hint)

        return SQLPlan(
            sql=sql,
            columns_requested=columns_used,
            estimated_row_count=requirements.row_limit_hint,
            explanation=explanation,
        )

    @staticmethod
    def sanitize_query(sql: str) -> str:
        """
        AST-level SELECT-only enforcement using sqlparse.
        Raises QuerySafetyError for any non-SELECT statement.
        """
        sql = sql.strip().rstrip(";")

        # Strip SQL block comments
        import re
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        # Strip line comments
        sql = re.sub(r"--[^\n]*", "", sql)
        sql = sql.strip()

        statements = [s for s in sqlparse.parse(sql) if str(s).strip()]
        if not statements:
            raise QuerySafetyError("Empty SQL statement after sanitization")

        for stmt in statements:
            stmt_type = stmt.get_type()

            if stmt_type == "SELECT":
                continue  # safe

            if stmt_type is None:
                # Could be a CTE (WITH ... SELECT ...) — inspect token stream
                for token in stmt.flatten():
                    if token.ttype is sqltokens.Keyword.DML:
                        if token.normalized.upper() != "SELECT":
                            raise QuerySafetyError(
                                f"Forbidden DML keyword: {token.normalized}"
                            )
                continue

            # Any named type other than SELECT is forbidden
            raise QuerySafetyError(
                f"Only SELECT statements are allowed. Got: {stmt_type}"
            )

        return sql

    @staticmethod
    def _enforce_limit(sql: str, row_limit: int) -> str:
        """Inject or clamp LIMIT clause to prevent huge result sets."""
        safe_limit = min(max(row_limit, 1), MAX_SAFE_ROWS)
        sql_upper = sql.upper()

        if "LIMIT" not in sql_upper:
            return f"{sql} LIMIT {safe_limit}"

        # If LIMIT exists, ensure it's not above MAX_SAFE_ROWS
        import re
        def clamp_limit(m):
            existing = int(m.group(1))
            return f"LIMIT {min(existing, MAX_SAFE_ROWS)}"

        return re.sub(r"LIMIT\s+(\d+)", clamp_limit, sql, flags=re.IGNORECASE)
