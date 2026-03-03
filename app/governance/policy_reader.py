"""
Policy Reader — parses uploaded governance policy documents.

Extracts column-level Allow/Anonymize/Block rules from natural language
policy documents. Rules are stored in ColumnRegistry after human review.
"""

import json
import logging
import os
from typing import List

from app.governance.column_registry import ColumnRule, VALID_STATES
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)


class PolicyReader:
    """
    Parses a governance policy document and extracts column-level rules.
    Output must be reviewed by an admin before being committed to the registry.
    """

    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager

    async def parse_policy(
        self,
        policy_text: str,
        db_service,
        conn_id: str,
    ) -> List[ColumnRule]:
        """
        Extract governance rules from policy text.

        Steps:
        1. Get actual table/column names from database schema
        2. Ask LLM to map policy statements to column states
        3. Validate output against actual schema
        4. Return List[ColumnRule] for admin review before saving

        Args:
            policy_text: Full text of the policy document
            db_service: DatabaseService for schema lookup
            conn_id: Connection ID to validate columns against

        Returns:
            List of ColumnRule objects (not yet committed to registry)
        """
        # Get actual schema to validate against
        schema_description = self._get_schema_description(db_service, conn_id)
        known_columns = self._get_known_columns(db_service, conn_id)

        prompt = f"""You are extracting data governance rules from a policy document.

Policy document:
---
{policy_text[:4000]}
---

Database schema available:
{schema_description}

For each table and column mentioned or implied in the policy, determine the access state:
- "allowed": full access, exact values can be shown
- "anonymize": only aggregates (average, count, range) — never individual values
- "block": completely hidden, treat as non-existent

Also extract any department or role-specific overrides.

Return ONLY valid JSON array:
[
  {{
    "table_name": "employees",
    "column_name": "salary",
    "default_state": "anonymize",
    "dept_overrides": {{"HR": "allowed", "Finance": "allowed"}},
    "role_overrides": {{"admin": "allowed"}}
  }},
  ...
]

Only include columns from the schema above. Use exact table and column names.
If a column is not mentioned in the policy, do not include it."""

        try:
            raw = await self.llm.chat(prompt, max_tokens=2000, temperature=0.0)
            # Extract JSON array
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start < 0 or end <= start:
                logger.warning("PolicyReader: no JSON array found in LLM response")
                return []

            data = json.loads(raw[start:end])

        except json.JSONDecodeError as e:
            logger.error("PolicyReader: JSON parse error: %s", e)
            return []
        except Exception as e:
            logger.error("PolicyReader: LLM call failed: %s", e)
            return []

        # Validate and build ColumnRule objects
        rules = []
        for item in data:
            table = item.get("table_name", "").strip()
            col = item.get("column_name", "").strip()
            state = item.get("default_state", "allowed").strip().lower()

            if not table or not col:
                continue
            if state not in VALID_STATES:
                logger.warning("PolicyReader: invalid state %r for %s.%s — skipping", state, table, col)
                continue

            # Validate against actual schema
            if known_columns and (table, col) not in known_columns:
                logger.warning(
                    "PolicyReader: %s.%s not in schema — including anyway for review", table, col
                )

            # Validate overrides
            dept_overrides = {
                k: v for k, v in item.get("dept_overrides", {}).items()
                if v in VALID_STATES
            }
            role_overrides = {
                k: v for k, v in item.get("role_overrides", {}).items()
                if v in VALID_STATES
            }

            rules.append(ColumnRule(
                table_name=table,
                column_name=col,
                default_state=state,
                dept_overrides=dept_overrides,
                role_overrides=role_overrides,
            ))

        logger.info("PolicyReader: extracted %d rules from policy document", len(rules))
        return rules

    @staticmethod
    def _get_schema_description(db_service, conn_id: str) -> str:
        try:
            tables = db_service.list_tables(conn_id)
            parts = []
            for table in tables[:20]:
                try:
                    schema = db_service.get_table_schema(conn_id, table)
                    cols = ", ".join(c["name"] for c in schema.get("columns", []))
                    parts.append(f"Table {table}: {cols}")
                except Exception:
                    parts.append(f"Table {table}: (schema unavailable)")
            return "\n".join(parts) if parts else "No schema available"
        except Exception as e:
            logger.warning("PolicyReader: could not get schema: %s", e)
            return "Schema unavailable"

    @staticmethod
    def _get_known_columns(db_service, conn_id: str) -> set:
        """Return set of (table, column) tuples for validation."""
        known = set()
        try:
            tables = db_service.list_tables(conn_id)
            for table in tables:
                try:
                    schema = db_service.get_table_schema(conn_id, table)
                    for col in schema.get("columns", []):
                        known.add((table, col["name"]))
                except Exception:
                    pass
        except Exception:
            pass
        return known
