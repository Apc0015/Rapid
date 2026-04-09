from __future__ import annotations
"""
DB Pipeline — D1 through D5.
The Prompt-Level Data Firewall lives here.
Raw data is destroyed before this function returns.
The LLM never sees raw rows, column names, or schema.
"""

import logging
from models.nl_result import NLResult
from infrastructure.db_master import get_db_master, SecurityException

logger = logging.getLogger(__name__)


async def run_db_pipeline(query: str, dept_tag: str, user_permissions: dict) -> NLResult:
    """
    Full DB pipeline. Returns NLResult — raw data is gone by the time this returns.
    """
    db = get_db_master()

    # D1 — Extract intent (LLM → structured IntentObject, NO SQL yet)
    intent = await db.extract_intent(query)
    logger.debug(f"D1 intent: {intent}")

    # D2 — Read schema (deterministic, NO LLM — prevents hallucinated column names)
    try:
        schema = db.read_schema(dept_tag)
    except ValueError as e:
        return NLResult(
            summary=f"No data available for department '{dept_tag}'.",
            source="database",
            confidence=0.0,
        )

    # D3 — Generate SELECT SQL (LLM, read-only enforced via system prompt)
    try:
        sql = await db.generate_sql(intent, schema, user_permissions)
    except Exception as e:
        logger.error(f"D3 SQL generation failed: {e}")
        return NLResult(summary="Unable to generate a valid query.", source="database", confidence=0.1)

    # D4 — Validate + execute (static analysis then read-only execution)
    try:
        db.validate_sql(sql, schema)
    except SecurityException as e:
        logger.error(f"D4 security violation: {e}")
        return NLResult(summary="Query blocked for security reasons.", source="database", confidence=0.0)

    try:
        raw_results = await db.execute_query(sql, dept_tag=dept_tag)
        verified = db.verify_results(raw_results)
    except Exception as e:
        logger.error(f"D4 execution failed: {e}")
        return NLResult(summary="Database query failed. Please try rephrasing.", source="database", confidence=0.1)

    # D5 — Governance + NL conversion + DESTROY RAW DATA
    governed, governance_log = db.apply_governance(verified, user_permissions, dept_tag)

    if not governed:
        db.destroy_raw_data(raw_results, verified)
        return NLResult(
            summary="No results were found, or all data was restricted by your access permissions.",
            source="database",
            confidence=0.3,
            governance_log=governance_log,
        )

    nl_summary = await db.convert_to_nl(governed, query)

    # THE FIREWALL — raw data destroyed, only NL summary survives
    db.destroy_raw_data(raw_results, verified, governed)

    blocks = [g for g in governance_log if g.get("action") in ("BLOCK", "BLOCK_ROLE")]
    confidence = _estimate_confidence(nl_summary, len(governed), len(blocks))

    return NLResult(
        summary=nl_summary,
        source="database",
        confidence=confidence,
        dept_tag=dept_tag,
        governance_log=governance_log,
    )


def _estimate_confidence(nl_summary: str, row_count: int, block_count: int) -> float:
    """Heuristic confidence based on result richness and blocks triggered."""
    if row_count == 0:
        return 0.2
    base = min(0.85, 0.5 + row_count * 0.03)
    penalty = block_count * 0.05
    return max(0.1, base - penalty)
