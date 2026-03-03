"""
Governance Rules — column-level state evaluation engine.

Priority: role_override > dept_override > default_state.
Unregistered columns default to "allowed".
"""

import logging
from typing import Optional
from app.governance.column_registry import ColumnRegistry, ColumnRule, VALID_STATES

logger = logging.getLogger(__name__)


class GovernanceRules:
    """Evaluates Allow/Anonymize/Block state for a column given user context."""

    def __init__(self, registry: ColumnRegistry):
        self.registry = registry

    def get_state(
        self,
        table_name: str,
        column_name: str,
        department: str,
        role: str,
    ) -> str:
        """
        Return governance state for a column.

        Priority: role_override > dept_override > default_state.
        Falls back to "allowed" for columns not in registry.
        """
        rule = self.registry.get_rule(table_name, column_name)
        if rule is None:
            # Unregistered column — open by default
            return "allowed"

        # Role override has highest priority
        if role and role in rule.role_overrides:
            state = rule.role_overrides[role]
            if state in VALID_STATES:
                return state

        # Department override
        if department and department in rule.dept_overrides:
            state = rule.dept_overrides[department]
            if state in VALID_STATES:
                return state

        return rule.default_state

    def get_all_rules(self):
        return self.registry.list_rules()

    def get_tables(self):
        return self.registry.list_tables()

    def upsert_column_rule(
        self,
        table_name: str,
        column_name: str,
        default_state: str,
        dept_overrides: Optional[dict] = None,
        role_overrides: Optional[dict] = None,
    ) -> ColumnRule:
        if default_state not in VALID_STATES:
            raise ValueError(f"Invalid state '{default_state}'. Must be: {VALID_STATES}")
        rule = ColumnRule(
            table_name=table_name,
            column_name=column_name,
            default_state=default_state,
            dept_overrides=dept_overrides or {},
            role_overrides=role_overrides or {},
        )
        self.registry.upsert_rule(rule)
        logger.info(
            "Governance rule set: %s.%s = %s", table_name, column_name, default_state
        )
        return rule

    def bulk_upsert(self, rules: list) -> int:
        """Bulk insert/update a list of ColumnRule objects. Returns count saved."""
        count = 0
        for rule in rules:
            self.registry.upsert_rule(rule)
            count += 1
        logger.info("Bulk upserted %d governance rules", count)
        return count

    def scan_and_register_schema(
        self,
        db_service,
        conn_id: str,
        default_state: str = "allowed",
    ) -> int:
        """
        Scan database schema and register all columns with default_state.
        Existing rules are NOT overwritten.

        Returns number of new rules created.
        """
        tables = db_service.list_tables(conn_id)
        new_count = 0
        for table in tables:
            try:
                schema = db_service.get_table_schema(conn_id, table)
                for col in schema.get("columns", []):
                    col_name = col["name"]
                    if not self.registry.get_rule(table, col_name):
                        self.registry.upsert_rule(
                            ColumnRule(
                                table_name=table,
                                column_name=col_name,
                                default_state=default_state,
                            )
                        )
                        new_count += 1
            except Exception as e:
                logger.warning("Could not scan table %s: %s", table, e)
        logger.info(
            "Schema scan complete for %s: %d new rules registered", conn_id, new_count
        )
        return new_count
