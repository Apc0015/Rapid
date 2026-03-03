"""
DB Master Agent — Brain 3

Coordinates D1→D2→D3→D4→D5 sequentially.
The only component with direct database access.
Returns ONLY a natural language summary + citation metadata.
Raw data never leaves this module.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.db.d1_extractor import InformationExtractor
from app.db.d2_schema import SchemaAnalyzer
from app.db.d3_writer import QueryWriter, QuerySafetyError
from app.db.d4_verifier import ResultVerifier
from app.db.d5_governance import GovernanceFilter, GovernanceResult, SourceCitation
from app.services.database_service import DatabaseService
from app.governance.rules import GovernanceRules
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
AUDIT_LOG_PATH = os.path.join(DATA_DIR, "audit.log")


@dataclass
class UserContext:
    username: str
    department: str
    role: str


@dataclass
class AuditEntry:
    timestamp: str
    username: str
    department: str
    query_hash: str
    tables_accessed: List[str]
    columns_used: List[str]
    governance_actions: List[str]
    row_count: int
    execution_ms: int


@dataclass
class DBMasterResult:
    nl_summary: str                     # NL paragraph — the ONLY data output
    sources: SourceCitation             # metadata only
    audit_entry: AuditEntry
    confidence: float
    activated: bool = True
    error: Optional[str] = None
    # No raw rows, no schema, no SQL — structural privacy guarantee


class DBMasterAgent:
    """
    Brain 3 — coordinates the DB track.

    Pipeline: Department Gate → D1 → D2 → D3 → D4 → D5 → Audit
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

        # Instantiate sub-agents
        self.d1 = InformationExtractor(llm_manager)
        self.d2 = SchemaAnalyzer(db_service, governance_rules, llm_manager)
        self.d3 = QueryWriter(llm_manager)
        self.d4 = ResultVerifier(db_service)
        self.d5 = GovernanceFilter(governance_rules, llm_manager)

    async def process(
        self,
        raw_query: str,
        user_ctx: UserContext,
        conn_id: Optional[str] = None,
    ) -> DBMasterResult:
        import time
        start = time.monotonic()

        # Resolve connection
        if not conn_id:
            user_conns = self.db.get_user_connections(user_ctx.username)
            if not user_conns:
                return self._no_connection_result(user_ctx, raw_query)
            conn_id = user_conns[0]

        logger.info(
            "DB Master: processing query for %s/%s via %s",
            user_ctx.username, user_ctx.department, conn_id,
        )

        try:
            # D1 — Information Extractor (no DB access)
            requirements = await self.d1.extract(raw_query)
            logger.debug("D1 requirements: %s", requirements)

            # D2 — Schema Analyzer (metadata only)
            mapping = await self.d2.analyze(
                requirements, conn_id,
                department=user_ctx.department,
                role=user_ctx.role,
            )
            if not mapping.relevant_tables:
                return self._no_relevant_data_result(user_ctx, raw_query, start)

            # D3 — Query Writer (SELECT-only, AST enforcement)
            sql_plan = await self.d3.write(mapping, requirements)
            logger.debug("D3 SQL: %s", sql_plan.sql[:200])

            # D4 — Result Verifier (executes query)
            verified = await self.d4.verify(sql_plan, conn_id)
            elapsed_d4_ms = int((time.monotonic() - start) * 1000)

            # D5 — Governance Filter + NL Writer (data firewall)
            gov_result = await self.d5.filter_and_narrate(
                result=verified,
                mapping=mapping,
                raw_query=raw_query,
                department=user_ctx.department,
                role=user_ctx.role,
            )

            total_ms = int((time.monotonic() - start) * 1000)

            audit = AuditEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                username=user_ctx.username,
                department=user_ctx.department,
                query_hash=str(hash(raw_query)),
                tables_accessed=gov_result.sources.tables_used,
                columns_used=gov_result.sources.columns_used,
                governance_actions=gov_result.sources.governance_log,
                row_count=verified.row_count,
                execution_ms=total_ms,
            )
            self._write_audit(audit)

            return DBMasterResult(
                nl_summary=gov_result.nl_summary,
                sources=gov_result.sources,
                audit_entry=audit,
                confidence=gov_result.confidence,
                activated=True,
            )

        except QuerySafetyError as e:
            logger.error("DB Master: query safety violation: %s", e)
            return self._error_result(user_ctx, raw_query, f"Query safety check failed: {e}", start)

        except Exception as e:
            logger.error("DB Master: pipeline error: %s", e, exc_info=True)
            return self._error_result(user_ctx, raw_query, str(e), start)

    def _no_connection_result(self, user_ctx: UserContext, raw_query: str) -> DBMasterResult:
        from app.db.d5_governance import SourceCitation
        return DBMasterResult(
            nl_summary="No database connection is configured. Please connect a database to enable data queries.",
            sources=SourceCitation(
                conn_id="none", tables_used=[], columns_used=[],
                row_count=0, query_timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            audit_entry=AuditEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                username=user_ctx.username, department=user_ctx.department,
                query_hash=str(hash(raw_query)), tables_accessed=[], columns_used=[],
                governance_actions=[], row_count=0, execution_ms=0,
            ),
            confidence=0.0,
            activated=False,
            error="no_connection",
        )

    def _no_relevant_data_result(
        self, user_ctx: UserContext, raw_query: str, start: float
    ) -> DBMasterResult:
        import time
        from app.db.d5_governance import SourceCitation
        elapsed = int((time.monotonic() - start) * 1000)
        return DBMasterResult(
            nl_summary="The database does not appear to contain data relevant to this question.",
            sources=SourceCitation(
                conn_id="", tables_used=[], columns_used=[],
                row_count=0, query_timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            audit_entry=AuditEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                username=user_ctx.username, department=user_ctx.department,
                query_hash=str(hash(raw_query)), tables_accessed=[], columns_used=[],
                governance_actions=[], row_count=0, execution_ms=elapsed,
            ),
            confidence=0.2,
            activated=True,
        )

    def _error_result(
        self, user_ctx: UserContext, raw_query: str, error: str, start: float
    ) -> DBMasterResult:
        import time
        from app.db.d5_governance import SourceCitation
        elapsed = int((time.monotonic() - start) * 1000)
        return DBMasterResult(
            nl_summary="The database query could not be completed due to a technical error.",
            sources=SourceCitation(
                conn_id="", tables_used=[], columns_used=[],
                row_count=0, query_timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            audit_entry=AuditEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                username=user_ctx.username, department=user_ctx.department,
                query_hash=str(hash(raw_query)), tables_accessed=[], columns_used=[],
                governance_actions=[f"error:{error[:100]}"], row_count=0, execution_ms=elapsed,
            ),
            confidence=0.0,
            activated=True,
            error=error,
        )

    def _write_audit(self, entry: AuditEntry):
        os.makedirs(DATA_DIR, exist_ok=True)
        record = {
            "timestamp": entry.timestamp,
            "user": entry.username,
            "dept": entry.department,
            "query_hash": entry.query_hash,
            "tables": entry.tables_accessed,
            "columns": entry.columns_used,
            "governance": entry.governance_actions,
            "rows": entry.row_count,
            "ms": entry.execution_ms,
        }
        try:
            with open(AUDIT_LOG_PATH, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning("Audit log write failed: %s", e)
