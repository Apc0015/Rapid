"""
D2 — Schema Analyzer

Reads database metadata (table/column names, types) and maps the abstract
information requirements from D1 onto the actual schema.

Reads metadata only — never queries actual row data.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.db.d1_extractor import InformationRequirements
from app.governance.rules import GovernanceRules
from app.services.database_service import DatabaseService
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)


@dataclass
class SchemaMapping:
    conn_id: str
    relevant_tables: List[str]
    # concept string → list of matching column names
    column_mappings: Dict[str, List[str]] = field(default_factory=dict)
    # "table.column" → governance state
    governance_flags: Dict[str, str] = field(default_factory=dict)
    # Compact schema text for D3 (no data values)
    schema_summary: str = ""
    dialect_hint: str = "standard SQL"


class SchemaAnalyzer:
    """
    D2 — maps information requirements to actual schema.
    Consults governance rules for each column.
    """

    def __init__(
        self,
        db_service: DatabaseService,
        governance_rules: GovernanceRules,
        llm_manager: LLMManager,
    ):
        self.db = db_service
        self.gov = governance_rules
        self.llm = llm_manager

    async def analyze(
        self,
        requirements: InformationRequirements,
        conn_id: str,
        department: str = "general",
        role: str = "viewer",
    ) -> SchemaMapping:
        tables = self.db.list_tables(conn_id)
        if not tables:
            logger.warning("D2: no tables found in %s", conn_id)
            return SchemaMapping(conn_id=conn_id, relevant_tables=[])

        # Build full schema description (metadata only)
        schema_lines = []
        all_schema: Dict[str, List[dict]] = {}
        for table in tables:
            try:
                s = self.db.get_table_schema(conn_id, table)
                cols = s.get("columns", [])
                all_schema[table] = cols
                col_str = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
                schema_lines.append(f"Table {table}: {col_str}")
            except Exception as e:
                logger.warning("D2: could not get schema for %s.%s: %s", conn_id, table, e)

        full_schema_text = "\n".join(schema_lines)
        concepts_text = "\n".join(f"- {c}" for c in requirements.data_concepts)

        prompt = f"""You are a database analyst. Match data concepts to database tables and columns.

Database schema:
{full_schema_text}

Data concepts needed:
{concepts_text}

Return ONLY valid JSON:
{{
  "relevant_tables": ["table1", "table2"],
  "column_mappings": {{
    "concept name": ["table.column", "table.column"]
  }}
}}

Only include tables and columns that are relevant. Use exact table and column names from the schema."""

        relevant_tables = []
        column_mappings: Dict[str, List[str]] = {}
        try:
            raw = await self.llm.chat(prompt, max_tokens=600, temperature=0.0)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                relevant_tables = data.get("relevant_tables", [])
                column_mappings = data.get("column_mappings", {})
        except Exception as e:
            logger.warning("D2 LLM mapping failed, using all tables: %s", e)
            relevant_tables = tables[:5]  # cap at 5 tables as fallback

        # Build governance flags for each relevant column
        governance_flags: Dict[str, str] = {}
        for table in relevant_tables:
            cols = all_schema.get(table, [])
            for col in cols:
                key = f"{table}.{col['name']}"
                state = self.gov.get_state(table, col["name"], department, role)
                governance_flags[key] = state

        # Build compact schema summary for D3 (only relevant tables/columns)
        summary_parts = []
        for table in relevant_tables:
            cols = all_schema.get(table, [])
            # Only include non-blocked columns in schema summary for D3
            visible_cols = [
                f"{c['name']} ({c['type']})"
                for c in cols
                if governance_flags.get(f"{table}.{c['name']}", "allowed") != "block"
            ]
            if visible_cols:
                summary_parts.append(f"Table {table}: {', '.join(visible_cols)}")

        schema_summary = "\n".join(summary_parts)

        # Detect dialect hint from conn_id
        if "postgres" in conn_id:
            dialect_hint = "PostgreSQL"
        elif "mysql" in conn_id:
            dialect_hint = "MySQL"
        else:
            dialect_hint = "SQLite"

        return SchemaMapping(
            conn_id=conn_id,
            relevant_tables=relevant_tables,
            column_mappings=column_mappings,
            governance_flags=governance_flags,
            schema_summary=schema_summary,
            dialect_hint=dialect_hint,
        )
