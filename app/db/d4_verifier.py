"""
D4 — Result Verifier

Executes the validated SQL query and checks result quality before passing
to the governance filter. Raw rows stay within this module and D5.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.db.d3_writer import SQLPlan
from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_SECONDS = 30


@dataclass
class VerifiedResult:
    rows: List[Dict[str, Any]]      # Raw rows — visible ONLY to D4 and D5
    columns: List[str]
    row_count: int
    quality_flags: List[str] = field(default_factory=list)
    execution_ms: int = 0
    conn_id: str = ""


class ResultVerifier:
    """D4 — executes and quality-checks the SQL result."""

    def __init__(self, db_service: DatabaseService):
        self.db = db_service

    async def verify(self, sql_plan: SQLPlan, conn_id: str) -> VerifiedResult:
        start = time.monotonic()
        quality_flags: List[str] = []

        try:
            df = self.db.execute_query(conn_id, sql_plan.sql)
        except Exception as e:
            logger.error("D4 query execution failed: %s", e)
            raise RuntimeError(f"Query execution failed: {e}") from e

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if elapsed_ms > QUERY_TIMEOUT_SECONDS * 1000:
            quality_flags.append("timeout")

        rows = df.to_dict(orient="records") if not df.empty else []
        columns = list(df.columns) if not df.empty else []
        row_count = len(rows)

        if row_count == 0:
            quality_flags.append("empty_result")
            logger.info("D4: query returned 0 rows (empty_result)")

        # Check if LIMIT was hit (suggests truncation)
        from app.db.d3_writer import MAX_SAFE_ROWS
        if row_count >= MAX_SAFE_ROWS:
            quality_flags.append("row_limit_hit")
            logger.warning("D4: result hit row limit (%d rows)", row_count)

        # Check for high null rate in any column
        if rows:
            for col in columns:
                null_count = sum(1 for r in rows if r.get(col) is None)
                null_rate = null_count / row_count
                if null_rate > 0.80:
                    quality_flags.append(f"high_null_rate:{col}")
                    logger.warning("D4: column %s has %.0f%% nulls", col, null_rate * 100)

        # Verify expected columns are present (if D3 specified them)
        if sql_plan.columns_requested:
            requested_bare = {
                c.split(".")[-1].lower() for c in sql_plan.columns_requested
            }
            actual = {c.lower() for c in columns}
            missing = requested_bare - actual
            if missing:
                quality_flags.append(f"missing_columns:{','.join(missing)}")

        result = VerifiedResult(
            rows=rows,
            columns=columns,
            row_count=row_count,
            quality_flags=quality_flags,
            execution_ms=elapsed_ms,
            conn_id=conn_id,
        )

        logger.info(
            "D4: %d rows, %d columns, flags=%s, %dms",
            row_count, len(columns), quality_flags, elapsed_ms,
        )
        return result
