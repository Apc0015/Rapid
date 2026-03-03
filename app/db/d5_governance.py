"""
D5 — Governance Filter + NL Writer

THE most critical component in the system.
Applies column-level governance rules, then converts the governed data
to a natural language paragraph. Raw rows are consumed and discarded here.

After this function returns, no raw data exists anywhere above this layer.
"""

import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.d2_schema import SchemaMapping
from app.db.d4_verifier import VerifiedResult
from app.governance.rules import GovernanceRules
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)


@dataclass
class SourceCitation:
    conn_id: str
    tables_used: List[str]
    columns_used: List[str]         # column names only — never values
    row_count: int
    query_timestamp: str
    governance_log: List[str] = field(default_factory=list)   # what was allowed/blocked


@dataclass
class GovernanceResult:
    nl_summary: str                         # NL paragraph — the ONLY data output
    sources: SourceCitation
    governance_actions: List[Dict]          # audit: {column, action, stat_used}
    confidence: float = 0.8
    # NOTE: raw_rows intentionally NOT stored here — structural privacy guarantee


@dataclass
class _GovernedColumn:
    name: str
    state: str          # "allowed" | "anonymize" | "block"
    stat_used: Optional[str] = None


class GovernanceFilter:
    """
    D5 — information firewall for the DB track.

    Applies governance rules and writes NL summary.
    Raw rows are held briefly in memory during conversion, then discarded.
    """

    def __init__(self, governance_rules: GovernanceRules, llm_manager: LLMManager):
        self.gov = governance_rules
        self.llm = llm_manager

    async def filter_and_narrate(
        self,
        result: VerifiedResult,
        mapping: SchemaMapping,
        raw_query: str,
        department: str,
        role: str,
    ) -> GovernanceResult:
        governance_actions: List[Dict] = []
        governed_columns: List[_GovernedColumn] = []

        # Determine table for each column (best-effort from mapping)
        col_table_map = self._build_col_table_map(mapping)

        # Apply governance to each column
        for col_name in result.columns:
            table = col_table_map.get(col_name, mapping.relevant_tables[0] if mapping.relevant_tables else "")
            state = self.gov.get_state(table, col_name, department, role)
            governed_columns.append(_GovernedColumn(name=col_name, state=state))

        # Build governed data representation — NEVER includes blocked values
        nl_input: Dict[str, Any] = {}
        columns_used_in_output: List[str] = []

        for gc in governed_columns:
            if gc.state == "block":
                governance_actions.append({
                    "column": gc.name,
                    "action": "blocked",
                    "stat_used": None,
                })
                logger.info("D5: column %s BLOCKED", gc.name)
                # Column does not appear in nl_input at all

            elif gc.state == "anonymize":
                # Only aggregate statistics — never individual values
                stats = self._compute_stats(result.rows, gc.name)
                if stats:
                    nl_input[f"{gc.name}_stats"] = stats
                    gc.stat_used = ",".join(stats.keys())
                    columns_used_in_output.append(gc.name)
                governance_actions.append({
                    "column": gc.name,
                    "action": "anonymized",
                    "stat_used": gc.stat_used,
                })
                logger.info("D5: column %s ANONYMIZED (stats: %s)", gc.name, gc.stat_used)

            else:  # allowed
                values = [r.get(gc.name) for r in result.rows if r.get(gc.name) is not None]
                if values:
                    nl_input[gc.name] = values
                    columns_used_in_output.append(gc.name)
                governance_actions.append({
                    "column": gc.name,
                    "action": "allowed",
                    "stat_used": None,
                })

        # Handle empty result
        if result.row_count == 0 or not nl_input:
            nl_summary = self._empty_result_summary(raw_query, result.quality_flags)
            confidence = 0.3
        else:
            nl_summary = await self._write_nl_summary(
                raw_query=raw_query,
                nl_input=nl_input,
                row_count=result.row_count,
                quality_flags=result.quality_flags,
            )
            confidence = 0.85 if "empty_result" not in result.quality_flags else 0.3

        # Build source citation — columns only, never values
        gov_log = [
            f"{a['column']}:{a['action']}" + (f"({a['stat_used']})" if a.get("stat_used") else "")
            for a in governance_actions
        ]
        sources = SourceCitation(
            conn_id=result.conn_id,
            tables_used=mapping.relevant_tables,
            columns_used=columns_used_in_output,
            row_count=result.row_count,
            query_timestamp=datetime.now(timezone.utc).isoformat(),
            governance_log=gov_log,
        )

        # Raw rows are not stored in the return value — structural guarantee
        return GovernanceResult(
            nl_summary=nl_summary,
            sources=sources,
            governance_actions=governance_actions,
            confidence=confidence,
        )

    async def _write_nl_summary(
        self,
        raw_query: str,
        nl_input: Dict[str, Any],
        row_count: int,
        quality_flags: List[str],
    ) -> str:
        """Call LLM with governed (sanitized) data to produce NL paragraph."""
        data_summary = json.dumps(nl_input, indent=2, default=str)
        flags_note = ""
        if "row_limit_hit" in quality_flags:
            flags_note = f"Note: results are limited to the first {row_count} rows."

        prompt = f"""Write a clear, concise natural language paragraph answering the following question.

Question: {raw_query}

Data (rows: {row_count}):
{data_summary}

{flags_note}

Rules:
- Write in natural prose only (no tables, no code, no raw data dumps)
- Preserve exact figures for allowed values
- Use aggregates (average, total, range, count) for anonymized values — never list individual values
- Keep it concise: 2-5 sentences
- Do not mention SQL, databases, or technical details"""

        try:
            return await self.llm.chat(prompt, max_tokens=500, temperature=0.0)
        except Exception as e:
            logger.error("D5 NL writing failed: %s", e)
            return f"The query returned {row_count} records, but the summary could not be generated."

    @staticmethod
    def _compute_stats(rows: List[Dict], col_name: str) -> Dict[str, Any]:
        """Compute aggregate statistics for anonymized columns."""
        values = [r.get(col_name) for r in rows if r.get(col_name) is not None]
        if not values:
            return {}

        stats: Dict[str, Any] = {"count": len(values)}

        # Try numeric stats
        try:
            nums = [float(v) for v in values]
            stats["average"] = round(statistics.mean(nums), 2)
            stats["min"] = min(nums)
            stats["max"] = max(nums)
            if len(nums) > 1:
                stats["std_dev"] = round(statistics.stdev(nums), 2)
        except (TypeError, ValueError):
            # Non-numeric: count distinct values only
            distinct = len(set(str(v) for v in values))
            stats["distinct_values"] = distinct

        return stats

    @staticmethod
    def _build_col_table_map(mapping: SchemaMapping) -> Dict[str, str]:
        """Build col_name → table_name mapping from column_mappings."""
        result: Dict[str, str] = {}
        for concept, col_refs in mapping.column_mappings.items():
            for ref in col_refs:
                if "." in ref:
                    table, col = ref.split(".", 1)
                    result[col] = table
        return result

    @staticmethod
    def _empty_result_summary(raw_query: str, quality_flags: List[str]) -> str:
        if "empty_result" in quality_flags:
            return (
                "The query returned no results. The database does not appear to contain "
                "data matching the specified criteria."
            )
        return "The query could not return a result for this question."
