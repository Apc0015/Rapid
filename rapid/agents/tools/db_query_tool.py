from __future__ import annotations
"""DBQueryTool — structured data access via the existing D1-D5 pipeline."""

import logging
from agents.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class DBQueryTool(BaseTool):
    name = "query_database"
    description = (
        "Query department structured data (databases/tables). "
        "Returns a natural-language summary — never raw rows."
    )

    async def run(self, query: str, dept_tag: str, user_permissions: dict) -> str:
        """
        Runs the full D1-D5 DB pipeline for the given dept and query.
        Returns the NL summary string or an empty string on failure.
        """
        from pipelines.db_pipeline import run_db_pipeline
        try:
            result = await run_db_pipeline(query, dept_tag, user_permissions)
            return result.summary or ""
        except Exception as exc:
            logger.error(f"DBQueryTool failed for dept={dept_tag}: {exc!r}")
            return ""
