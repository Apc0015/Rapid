from __future__ import annotations
"""
Agent Supervisor + Agent Representative — Tier 1 Meta Agents.

AgentSupervisor:
  Rates every agent after every task (async, never delays response).
  Detects gap patterns. Auto-forwards confirmed gaps to AgentRepresentative.

AgentRepresentative:
  Sole channel between the system and human admins.
  Persists gap requests to SQLite. Human approves/rejects via API.
  On approval: calls registry.register_dept() to onboard at runtime — no restart needed.
"""

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import config
from models.nl_result import NLResult

logger = logging.getLogger(__name__)

def _resolve_requests_db() -> str:
    try:
        p = Path("data/agent_requests.db")
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(p), timeout=3)
        c.execute("CREATE TABLE IF NOT EXISTS _probe (x INTEGER)")
        c.execute("INSERT INTO _probe VALUES (1)")
        c.commit()
        c.execute("DELETE FROM _probe")
        c.commit()
        c.close()
        return str(p)
    except sqlite3.OperationalError:
        return "/tmp/rapid_agent_requests.db"

_REQUESTS_DB = _resolve_requests_db()


# ── Approval DB helpers ───────────────────────────────────────────────────────

def _requests_conn() -> sqlite3.Connection:
    Path(_REQUESTS_DB).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_REQUESTS_DB)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_requests (
            request_id      TEXT PRIMARY KEY,
            gap_id          TEXT,
            query_pattern   TEXT NOT NULL,
            occurrences     INTEGER NOT NULL,
            suggested_dept  TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            created_at      TEXT NOT NULL,
            reviewed_at     TEXT,
            reviewed_by     TEXT,
            rejection_note  TEXT
        )
    """)
    c.commit()
    return c


# ─────────────────────────────────────────────────────────────────────────────

class AgentSupervisor:

    def __init__(self):
        self._gap_reports: List[dict] = []

    async def rate_agent(
        self,
        agent_id: str,
        task_id: str,
        result: NLResult,
        original_query: str = "",
    ) -> float:
        """
        Rate agent performance on three dimensions:
          - Answer relevance (0-1): LLM-judged relevance to the original query.
            Falls back to length heuristic if no original_query provided.
          - Confidence accuracy (0-1): 1 - |agent_confidence - measured_relevance|.
            Rewards agents whose self-reported confidence matches actual quality.
          - Token efficiency (0-1): 300/word_count (capped at 1.0).
            Rewards concise answers; optimal = 300 words.

        Composite: relevance*0.5 + conf_accuracy*0.3 + token_efficiency*0.2
        Returns composite score 0.0–1.0. Writes to audit log.
        """
        from agents.system.audit_logger import get_audit
        audit = get_audit()

        if result is None or not result.summary:
            score = 0.0
            dimensions = {"relevance": 0.0, "confidence_accuracy": 0.0, "token_efficiency": 0.5}
            audit.write_agent_score(agent_id, task_id, round(score, 3), dimensions)
            logger.debug(f"Supervisor rated {agent_id}: {score:.3f} (empty result)")
            return score

        # ── 1. Relevance ──────────────────────────────────────────────────────
        if original_query:
            try:
                from infrastructure.llm_client import get_llm
                llm = get_llm()
                llm_prompt = (
                    f"Question: {original_query}\n"
                    f"Answer: {result.summary[:500]}\n"
                    f"Score (0-1):"
                )
                llm_system = (
                    "You are an objective answer quality evaluator. Be strict. "
                    "On a scale of 0 to 1, how relevant and complete is this answer "
                    "to the question? Return only a decimal number."
                )
                raw = await llm.complete(llm_prompt, system=llm_system)
                # Parse the first float-like token from the response
                import re as _re
                match = _re.search(r"\d+\.?\d*", raw.strip())
                relevance = float(match.group()) if match else 0.5
                # Clamp to [0, 1]
                relevance = max(0.0, min(1.0, relevance))
            except Exception as e:
                logger.error(f"Supervisor LLM relevance call failed for {agent_id}: {e}")
                relevance = 0.5
        else:
            # Backward-compat heuristic — warns because it's inaccurate
            logger.warning(
                f"Supervisor rate_agent called without original_query for agent={agent_id}, "
                f"task={task_id}. Falling back to length heuristic (inaccurate)."
            )
            relevance = 0.8 if len(result.summary) > 50 else 0.3

        # ── 2. Confidence accuracy ────────────────────────────────────────────
        # How well did the agent's own confidence predict actual quality?
        conf_accuracy = 1.0 - abs(result.confidence - relevance)

        # ── 3. Token efficiency ───────────────────────────────────────────────
        # Optimal = 300 words; longer answers are penalised.
        word_count = max(1, len(result.summary.split()))
        token_efficiency = min(1.0, 300 / word_count)

        # ── Composite ─────────────────────────────────────────────────────────
        score = (
            relevance        * 0.5
            + conf_accuracy  * 0.3
            + token_efficiency * 0.2
        )

        dimensions = {
            "relevance":           round(relevance, 3),
            "confidence_accuracy": round(conf_accuracy, 3),
            "token_efficiency":    round(token_efficiency, 3),
        }

        audit.write_agent_score(agent_id, task_id, round(score, 3), dimensions)
        logger.debug(
            f"Supervisor rated {agent_id}: {score:.3f} "
            f"(rel={relevance:.2f}, conf_acc={conf_accuracy:.2f}, tok_eff={token_efficiency:.2f})"
        )
        return score

    async def detect_gaps(self, query_log: List[dict]) -> List[dict]:
        """
        Scan query log for patterns where no agent bid ≥ MIN_BID_CONF.
        Automatically forwards confirmed patterns (3+ hits) to AgentRepresentative.
        Returns list of newly confirmed gap dicts.
        """
        gap_queries = [q for q in query_log if q.get("action_taken") == "gap_flagged"]

        gap_counts: dict[str, int] = {}
        for q in gap_queries:
            key = q.get("raw_query", "")[:80]
            gap_counts[key] = gap_counts.get(key, 0) + 1

        confirmed = []
        rep = get_agent_representative()

        for query_pattern, count in gap_counts.items():
            if count >= config.GAP_PATTERN_THRESHOLD:
                gap = {
                    "gap_id":           str(uuid.uuid4()),
                    "query_pattern":    query_pattern,
                    "occurrence_count": count,
                }
                confirmed.append(gap)
                # ── Auto-forward confirmed gaps to AgentRepresentative ────────
                rep.receive_gap_report(gap)

        return confirmed

    async def flag_gap(self, gap_report: dict):
        """Flag a single gap and forward to AgentRepresentative."""
        self._gap_reports.append(gap_report)
        logger.warning(f"Gap flagged: {gap_report}")
        get_agent_representative().receive_gap_report(gap_report)

    def get_pending_gaps(self) -> List[dict]:
        gaps = list(self._gap_reports)
        self._gap_reports.clear()
        return gaps


# ─────────────────────────────────────────────────────────────────────────────

class AgentRepresentative:
    """
    Tier 1 Meta Agent — sole channel between system and human admins.

    Full workflow:
      1. receive_gap_report()   — ingest gap, create DB-persisted request
      2. list_requests()        — admin views pending requests via API
      3. approve() / reject()   — admin decision stored in DB
      4. onboard_agent()        — called on approval: registers stub at runtime
    """

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def receive_gap_report(self, gap_report: dict) -> dict:
        """
        Persist a confirmed gap as a new agent request.
        Returns the request record.
        """
        request_id = str(uuid.uuid4())
        now        = datetime.now(timezone.utc).isoformat()
        # Infer a dept name from the query pattern (simple keyword heuristic)
        suggested  = _infer_dept_from_pattern(gap_report.get("query_pattern", ""))

        record = {
            "request_id":     request_id,
            "gap_id":         gap_report.get("gap_id"),
            "query_pattern":  gap_report.get("query_pattern", ""),
            "occurrences":    gap_report.get("occurrence_count", 0),
            "suggested_dept": suggested,
            "status":         "pending",
            "created_at":     now,
        }
        try:
            c = _requests_conn()
            c.execute("""
                INSERT OR IGNORE INTO agent_requests
                    (request_id, gap_id, query_pattern, occurrences, suggested_dept,
                     status, created_at)
                VALUES (:request_id, :gap_id, :query_pattern, :occurrences,
                        :suggested_dept, :status, :created_at)
            """, record)
            c.commit()
            c.close()
            logger.info(f"[AgentRep] Request {request_id} created for pattern: "
                        f"'{record['query_pattern'][:60]}' (dept hint: {suggested})")
        except Exception as e:
            logger.error(f"[AgentRep] Failed to persist request: {e}")

        return record

    # ── Admin actions ─────────────────────────────────────────────────────────

    def list_requests(self, status: Optional[str] = None) -> List[dict]:
        """Return all agent requests, optionally filtered by status."""
        try:
            c = _requests_conn()
            if status:
                rows = c.execute(
                    "SELECT * FROM agent_requests WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM agent_requests ORDER BY created_at DESC"
                ).fetchall()
            c.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[AgentRep] list_requests failed: {e}")
            return []

    def track_approval(self, request_id: str) -> str:
        """Returns current status: pending / approved / rejected."""
        try:
            c = _requests_conn()
            row = c.execute(
                "SELECT status FROM agent_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            c.close()
            return row["status"] if row else "not_found"
        except Exception:
            return "not_found"

    def approve(self, request_id: str, reviewed_by: str = "admin") -> dict:
        """
        Admin approves a request. Triggers onboard_agent() immediately.
        Returns the request record with updated status.
        """
        return self._set_status(request_id, "approved", reviewed_by)

    def reject(self, request_id: str, reviewed_by: str = "admin",
               note: str = "") -> dict:
        """Admin rejects a request with an optional note."""
        return self._set_status(request_id, "rejected", reviewed_by, note)

    def _set_status(self, request_id: str, status: str,
                    reviewed_by: str, note: str = "") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        try:
            c = _requests_conn()
            c.execute("""
                UPDATE agent_requests
                SET status=?, reviewed_at=?, reviewed_by=?, rejection_note=?
                WHERE request_id=?
            """, (status, now, reviewed_by, note, request_id))
            c.commit()
            row = c.execute(
                "SELECT * FROM agent_requests WHERE request_id=?", (request_id,)
            ).fetchone()
            c.close()
            record = dict(row) if row else {}
        except Exception as e:
            logger.error(f"[AgentRep] _set_status failed: {e}")
            return {}

        if status == "approved" and record:
            self.onboard_agent(record)

        return record

    # ── Onboarding ────────────────────────────────────────────────────────────

    def onboard_agent(self, request: dict):
        """
        Register a new stub DeptAgent into the live AgentRegistry at runtime.
        No application restart required.

        The stub agent:
          - Has a dept_tag derived from suggested_dept or slugified query pattern
          - Uses keyword-based bidding with terms from the query pattern
          - Runs the standard RAG+DB execute() pipeline from BaseDeptAgent
        """
        from agents.base.base_dept_agent import BaseDeptAgent

        dept_tag = _slugify(request.get("suggested_dept") or
                            request.get("query_pattern", "unknown"))[:30]
        pattern  = request.get("query_pattern", "")

        # Build keyword list from the query pattern
        keywords = [w.lower() for w in pattern.split() if len(w) > 3][:10]

        # Dynamically create a concrete stub subclass
        stub_cls = type(
            f"Stub_{dept_tag.title().replace('_', '')}Agent",
            (BaseDeptAgent,),
            {
                "dept_tag":        dept_tag,
                "doc_folders":     [f"departments/{dept_tag}/docs"],
                "permitted_tables":[],
                "bid_keywords":    keywords,
                "partial_keywords":[],
            },
        )
        stub_instance = stub_cls()

        # Register into the live registry
        try:
            from shared import registry
            registry.register_dept(stub_instance)
            logger.info(
                f"[AgentRep] Stub agent '{dept_tag}' onboarded into live registry. "
                f"Keywords: {keywords}"
            )
        except Exception as e:
            logger.error(f"[AgentRep] onboard_agent failed to register: {e}")

        return stub_instance


# ── Helpers ───────────────────────────────────────────────────────────────────

_DEPT_HINT_KEYWORDS: dict[str, list[str]] = {
    "finance":          ["revenue", "budget", "invoice", "payroll", "financial", "cost"],
    "hr":               ["employee", "leave", "hiring", "headcount", "benefit", "salary"],
    "legal":            ["contract", "compliance", "regulation", "nda", "litigation", "ip"],
    "sales":            ["deal", "pipeline", "crm", "quota", "customer", "close"],
    "marketing":        ["campaign", "lead", "brand", "content", "seo", "advertising"],
    "ops":              ["process", "logistics", "sla", "vendor", "supply", "facility"],
    "it":               ["server", "infrastructure", "security", "access", "software", "cloud"],
    "procurement":      ["purchase", "supplier", "rfp", "sourcing", "spend", "order"],
    "rd":               ["research", "experiment", "patent", "prototype", "innovation"],
    "customer_success": ["churn", "nps", "onboarding", "renewal", "satisfaction", "ticket"],
}


def _infer_dept_from_pattern(pattern: str) -> str:
    """Best-effort dept hint from query pattern keywords."""
    q = pattern.lower()
    scores = {dept: sum(1 for kw in kws if kw in q)
              for dept, kws in _DEPT_HINT_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unknown"


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ── Singletons ────────────────────────────────────────────────────────────────

_supervisor:   Optional[AgentSupervisor]    = None
_representative: Optional[AgentRepresentative] = None


def get_agent_supervisor() -> AgentSupervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = AgentSupervisor()
    return _supervisor


def get_agent_representative() -> AgentRepresentative:
    global _representative
    if _representative is None:
        _representative = AgentRepresentative()
    return _representative
