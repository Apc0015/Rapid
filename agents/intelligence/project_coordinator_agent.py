"""
agents/intelligence/project_coordinator_agent.py — Project Coordinator Agent.

The ProjectCoordinatorAgent is the primary entry point for all project-scoped
queries in RAPID. It:

  1. Accepts a query + ProjectContext
  2. Uses the DynamicAgentFactory to load the right intelligence agent for the
     project's department (sales, finance, hr, ...)
  3. Delegates intent classification + skill planning to the dept intelligence agent
  4. Performs tiered data retrieval from the project's own SQLite database
  5. Assembles a rich LLM prompt: project context (Tier 1) + retrieved data
     (Tier 2 / Tier 4) + domain-specific system instructions
  6. Calls the LLM via get_llm() and returns a structured CoordinatorResult

This agent does NOT modify data — it is read-only by design.
Write actions are queued to agent_action_queue and require human approval.

Usage (from project_query.py):
    coordinator = get_project_coordinator()
    result = await coordinator.run(
        query="What is our pipeline health?",
        project_context=ctx,
        mode="query",
        history="...",
    )
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agents.base.project_aware_mixin import ProjectAwareMixin
from infrastructure.project_context import ProjectContext

logger = logging.getLogger(__name__)


# ── Response dataclass ────────────────────────────────────────────────────────

@dataclass
class CoordinatorResult:
    """Structured result from the ProjectCoordinatorAgent."""
    answer:          str
    confidence:      float
    sources:         list[str]   = field(default_factory=list)
    data_gaps:       list[str]   = field(default_factory=list)
    domain_intent:   str         = "unknown"
    mode_used:       str         = "query"
    dept_agent_used: str         = "none"
    duration_ms:     int         = 0
    action_queued:   bool        = False
    action_id:       Optional[str] = None


# ── ProjectCoordinatorAgent ───────────────────────────────────────────────────

class ProjectCoordinatorAgent(ProjectAwareMixin):
    """
    Coordinates project-scoped LLM queries by:
      - Selecting the right dept intelligence agent
      - Performing tiered data retrieval from the project DB
      - Assembling the LLM prompt with full project context
      - Returning a structured CoordinatorResult
    """

    # System prompt templates per mode
    _SYSTEM_PROMPTS = {
        "query": (
            "You are RAPID, an expert project intelligence assistant. "
            "Answer the user's question using ONLY the project data provided. "
            "Be specific, cite numbers when available, and flag any gaps. "
            "Do not fabricate data. If you are uncertain, say so clearly."
        ),
        "analysis": (
            "You are RAPID, an expert project analyst. "
            "Analyze the provided project data deeply: identify patterns, risks, "
            "bottlenecks, and improvement opportunities. "
            "Structure your analysis with clear sections. Be data-driven."
        ),
        "planning": (
            "You are RAPID, an expert project planning advisor. "
            "Generate a concrete, time-bound action plan grounded in the project data. "
            "Prioritize by impact and urgency. Flag dependencies and blockers. "
            "Every recommendation must be traceable to the data provided."
        ),
        "reporting": (
            "You are RAPID, an expert project reporter. "
            "Generate a clear, executive-ready status summary of this project. "
            "Cover: progress vs target, KPI status, risks, next milestones. "
            "Be concise, professional, and honest about gaps."
        ),
    }

    def __init__(self) -> None:
        self._factory = None   # Lazy — loaded on first call

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(
        self,
        query:           str,
        project_context: ProjectContext,
        mode:            str = "query",
        history:         str = "",
    ) -> CoordinatorResult:
        """
        Main entry point. Runs the full coordinator pipeline.

        Args:
            query:           The user's natural-language question
            project_context: Loaded ProjectContext (Tier 1 already populated)
            mode:            'query' | 'analysis' | 'planning' | 'reporting'
            history:         Serialized prior chat history (optional)

        Returns:
            CoordinatorResult with answer, confidence, sources, gaps
        """
        t_start = time.monotonic()

        # 1. Select intelligence agent for this project's department
        dept_id = project_context.dept_id
        intel_agent = self._get_intel_agent(dept_id)
        dept_agent_name = type(intel_agent).__name__ if intel_agent else "generic"

        # 2. Classify intent (via dept intelligence agent if available)
        domain_intent = await self._classify_intent(query, intel_agent)

        # 3. Tiered data retrieval from project DB
        tier2_data, data_gaps_t2, sources_t2 = await self._tier2_retrieval(
            query, project_context, domain_intent
        )

        if mode in ("analysis", "reporting"):
            tier4_data, data_gaps_t4, sources_t4 = await self._tier4_retrieval(project_context)
            tier5_data, sources_t5 = await self._tier5_retrieval(query, project_context)
            retrieved_data = "\n\n".join(
                part for part in [tier2_data, tier4_data, tier5_data] if part.strip()
            )
            sources   = list(dict.fromkeys(sources_t2 + sources_t4 + sources_t5))
            data_gaps = list(dict.fromkeys(data_gaps_t2 + data_gaps_t4))
        else:
            # For query/planning: add Tier 5 graph context if relationship keywords present
            tier5_data, sources_t5 = await self._tier5_retrieval(query, project_context)
            if tier5_data.strip():
                retrieved_data = f"{tier2_data}\n\n{tier5_data}".strip()
                sources   = list(dict.fromkeys(sources_t2 + sources_t5))
            else:
                retrieved_data = tier2_data
                sources   = sources_t2
            data_gaps = data_gaps_t2

        # 4. Build LLM prompt
        system_prompt = self._build_system_prompt(mode, intel_agent, dept_id)
        user_prompt = self._build_user_prompt(
            query, project_context, retrieved_data, history, domain_intent, mode
        )

        # 5. Call LLM — use tenant-configured provider/model
        try:
            llm = await self._get_llm(project_context.tenant_id)
            answer = await llm.complete(user_prompt, system=system_prompt)
        except Exception as e:
            logger.warning(f"[ProjectCoordinator] LLM call failed: {e}")
            answer = (
                f"I retrieved the following project data but could not generate a full answer "
                f"due to an LLM error. Raw data:\n\n{retrieved_data[:800]}"
            )

        # 6. Log activity in project DB
        self.log_project_activity(
            project_context,
            event_type="query",
            description=f"[{mode}] {query[:120]}",
            related_entity="project_coordinator",
        )

        # 7. Build result
        confidence = self._estimate_confidence(
            data_gaps, sources, domain_intent
        )
        duration_ms = int((time.monotonic() - t_start) * 1000)

        return CoordinatorResult(
            answer=answer,
            confidence=confidence,
            sources=sources,
            data_gaps=data_gaps,
            domain_intent=domain_intent,
            mode_used=mode,
            dept_agent_used=dept_agent_name,
            duration_ms=duration_ms,
        )

    # ── Intent classification ─────────────────────────────────────────────────

    async def _classify_intent(self, query: str, intel_agent) -> str:
        """
        Ask the dept intelligence agent to classify the query's domain intent.
        Falls back to keyword-based generic classification if no agent available.
        """
        if intel_agent and hasattr(intel_agent, "analyze_query"):
            try:
                analysis = await intel_agent.analyze_query(query)
                return analysis.domain_intent.value
            except Exception as e:
                logger.debug(f"[ProjectCoordinator] Intent classification failed: {e}")

        # Keyword-based fallback
        q = query.lower()
        if any(w in q for w in ["revenue", "pipeline", "deal", "sales", "quota"]):
            return "deal_analysis"
        if any(w in q for w in ["budget", "spend", "cost", "expense", "burn"]):
            return "budget_planning"
        if any(w in q for w in ["risk", "blocker", "issue", "problem", "threat"]):
            return "risk_assessment"
        if any(w in q for w in ["milestone", "timeline", "deadline", "schedule", "progress"]):
            return "progress_tracking"
        if any(w in q for w in ["kpi", "metric", "target", "goal", "performance"]):
            return "kpi_review"
        if any(w in q for w in ["plan", "next step", "action", "priorit", "roadmap"]):
            return "planning"
        return "general_query"

    # ── Tiered retrieval ──────────────────────────────────────────────────────

    async def _tier2_retrieval(
        self,
        query:           str,
        project_context: ProjectContext,
        domain_intent:   str,
    ) -> tuple[str, list[str], list[str]]:
        """
        Tier 2: focused SQL retrieval from the project database.
        Returns (data_string, data_gaps, sources).
        """
        db_path = self.get_project_db_path(project_context)
        if not db_path or not Path(db_path).exists():
            return "No project data available yet.", ["project database not found"], []

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15)
            conn.row_factory = sqlite3.Row
            schema = project_context.schema
            q_lower = query.lower()

            sections: list[str] = []
            sources:  list[str] = []
            gaps:     list[str] = []

            # Always fetch milestones
            try:
                rows = conn.execute(
                    """
                    SELECT name, due_date, status, priority
                    FROM project_milestones
                    ORDER BY due_date
                    LIMIT 10
                    """
                ).fetchall()
                if rows:
                    lines = [
                        f"  - {r['name']} | due: {r['due_date']} "
                        f"| status: {r['status']} | priority: {r['priority'] if 'priority' in r.keys() else '?'}"
                        for r in rows
                    ]
                    sections.append("MILESTONES:\n" + "\n".join(lines))
                    sources.append("project_milestones")
                else:
                    gaps.append("no milestones recorded")
            except Exception as e:
                logger.debug(f"[Coordinator] milestones retrieval failed: {e}")
                gaps.append("milestones table unavailable")

            # Always fetch open risks
            try:
                rows = conn.execute(
                    """
                    SELECT title, probability, impact, status, mitigation_plan
                    FROM project_risks
                    WHERE status = 'open'
                    ORDER BY risk_score DESC
                    LIMIT 8
                    """
                ).fetchall()
                if rows:
                    lines = [
                        f"  - {r['title']} | prob: {r['probability']} "
                        f"| impact: {r['impact']}"
                        + (f" | mitigation: {r['mitigation_plan']}" if r['mitigation_plan'] else "")
                        for r in rows
                    ]
                    sections.append("OPEN RISKS:\n" + "\n".join(lines))
                    sources.append("project_risks")
                else:
                    gaps.append("no open risks recorded")
            except Exception as e:
                logger.debug(f"[Coordinator] risks retrieval failed: {e}")
                gaps.append("risks table unavailable")

            # Pipeline / deals (sales-relevant)
            if any(w in q_lower for w in [
                "pipeline", "deal", "revenue", "sales", "customer", "account",
                "win", "close", "quota", "crm"
            ]) or "project_pipeline" in schema:
                try:
                    rows = conn.execute(
                        """
                        SELECT customer_name, stage, value, close_date,
                               owner, probability
                        FROM project_pipeline
                        ORDER BY value DESC
                        LIMIT 10
                        """
                    ).fetchall()
                    if rows:
                        lines = [
                            f"  - {r['customer_name']} | stage: {r['stage']} "
                            f"| value: {r['value']:,.0f} | prob: {r['probability']}% "
                            f"| close: {r['close_date']}"
                            for r in rows
                        ]
                        sections.append("SALES PIPELINE:\n" + "\n".join(lines))
                        sources.append("project_pipeline")
                    else:
                        gaps.append("no pipeline deals recorded")
                except Exception:
                    pass

            # Budget lines / financial data
            if any(w in q_lower for w in [
                "budget", "spend", "cost", "expense", "financial",
                "burn", "remaining", "allocation"
            ]):
                # Use Tier 1 metadata (budget_total, budget_spent, budget_remaining)
                meta = project_context.metadata
                if meta:
                    budget_str = (
                        f"  - Total budget : {meta.get('budget_total', 'N/A')}\n"
                        f"  - Spent        : {meta.get('budget_spent', 'N/A')}\n"
                        f"  - Remaining    : {meta.get('budget_remaining', 'N/A')}\n"
                        f"  - Completion   : {meta.get('completion_pct', 0):.0f}%"
                    )
                    sections.append("BUDGET SUMMARY (from project metadata):\n" + budget_str)
                    sources.append("project_metadata (budget)")

            # Activities / tasks
            if any(w in q_lower for w in [
                "task", "activit", "action item", "todo", "work done",
                "completed", "what was done"
            ]):
                try:
                    rows = conn.execute(
                        """
                        SELECT activity_type, outcome, owner, activity_date, notes
                        FROM project_activities
                        ORDER BY activity_date DESC
                        LIMIT 10
                        """
                    ).fetchall()
                    if rows:
                        lines = [
                            f"  - [{r['activity_date']}] {r['activity_type']} "
                            f"| outcome: {r['outcome']} | owner: {r['owner']}"
                            for r in rows
                        ]
                        sections.append("RECENT ACTIVITIES:\n" + "\n".join(lines))
                        sources.append("project_activities")
                    else:
                        gaps.append("no activities recorded")
                except Exception:
                    pass

            # Targets
            if any(w in q_lower for w in [
                "target", "goal", "objective", "kpi", "metric", "performance"
            ]):
                try:
                    rows = conn.execute(
                        "SELECT metric, target_value, current_value, period, status FROM project_targets LIMIT 8"
                    ).fetchall()
                    if rows:
                        lines = [
                            f"  - {r['metric']}: {r['current_value']} / {r['target_value']} [{r['status']}]"
                            for r in rows
                        ]
                        sections.append("TARGETS:\n" + "\n".join(lines))
                        sources.append("project_targets")
                except Exception:
                    pass

            conn.close()

            if not sections:
                return "No relevant data found in the project database.", gaps, sources

            return "\n\n".join(sections), gaps, sources

        except Exception as e:
            logger.error(f"[ProjectCoordinator] Tier 2 retrieval failed: {e}")
            return "Error reading project database.", [str(e)], []

    async def _tier4_retrieval(
        self,
        project_context: ProjectContext,
    ) -> tuple[str, list[str], list[str]]:
        """
        Tier 4: pre-aggregated statistics — fast, always runs for analysis/reporting.
        Returns (stats_string, data_gaps, sources).
        """
        db_path = self.get_project_db_path(project_context)
        if not db_path or not Path(db_path).exists():
            return "No data available.", ["project database not found"], []

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            sections: list[str] = []
            sources:  list[str] = []
            gaps:     list[str] = []

            # Milestone completion %
            try:
                r = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS done,
                        SUM(CASE WHEN status IN ('pending','in_progress')
                                  AND due_date < date('now') THEN 1 ELSE 0 END) AS overdue
                    FROM project_milestones
                    """
                ).fetchone()
                if r and r["total"] > 0:
                    sections.append(
                        f"MILESTONE SUMMARY: {r['done']}/{r['total']} complete, "
                        f"{r['overdue']} overdue"
                    )
                    sources.append("project_milestones (aggregated)")
                else:
                    gaps.append("no milestone data")
            except Exception:
                gaps.append("milestone aggregation failed")

            # KPI status distribution
            try:
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS cnt FROM project_kpis GROUP BY status"
                ).fetchall()
                if rows:
                    dist = ", ".join(f"{r['status']}: {r['cnt']}" for r in rows)
                    sections.append(f"KPI STATUS: {dist}")
                    sources.append("project_kpis (aggregated)")
                else:
                    gaps.append("no KPI data")
            except Exception:
                gaps.append("KPI aggregation failed")

            # Risk profile
            try:
                rows = conn.execute(
                    """
                    SELECT impact, COUNT(*) AS cnt
                    FROM project_risks WHERE status='open'
                    GROUP BY impact
                    """
                ).fetchall()
                if rows:
                    risk_dist = ", ".join(f"{r['impact']} impact: {r['cnt']}" for r in rows)
                    sections.append(f"OPEN RISK PROFILE: {risk_dist}")
                    sources.append("project_risks (aggregated)")
                else:
                    gaps.append("no open risks")
            except Exception:
                gaps.append("risk aggregation failed")

            # Pipeline value summary (if applicable)
            try:
                r = conn.execute(
                    """
                    SELECT COUNT(*) AS deals,
                           SUM(value) AS total_value,
                           AVG(probability) AS avg_prob
                    FROM project_pipeline
                    """
                ).fetchone()
                if r and r["deals"] and r["deals"] > 0:
                    weighted = (r["total_value"] or 0) * (r["avg_prob"] or 0) / 100
                    sections.append(
                        f"PIPELINE SUMMARY: {r['deals']} deals | "
                        f"total value: {r['total_value']:,.0f} | "
                        f"avg probability: {r['avg_prob']:.0f}% | "
                        f"weighted value: {weighted:,.0f}"
                    )
                    sources.append("project_pipeline (aggregated)")
            except Exception:
                pass

            # Budget utilization
            meta = project_context.metadata
            if meta and meta.get("budget_total"):
                bt = float(meta.get("budget_total", 0))
                bs = float(meta.get("budget_spent", 0))
                if bt > 0:
                    util_pct = bs / bt * 100
                    sections.append(
                        f"BUDGET UTILIZATION: {util_pct:.1f}% spent | "
                        f"completion: {meta.get('completion_pct', 0):.0f}% | "
                        f"health: {meta.get('health_status', 'unknown')}"
                    )
                    sources.append("project_metadata (aggregated)")

            conn.close()

            return "\n".join(sections), gaps, sources

        except Exception as e:
            logger.error(f"[ProjectCoordinator] Tier 4 retrieval failed: {e}")
            return "Aggregation error.", [str(e)], []

    # ── Tier 5: Knowledge graph retrieval ────────────────────────────────────

    async def _tier5_retrieval(
        self,
        query:           str,
        project_context: ProjectContext,
    ) -> tuple[str, list[str]]:
        """
        Tier 5: Knowledge graph traversal — relationship-aware context.

        Activates when the query contains relationship keywords:
          "connected to", "linked", "blocking", "caused by", "related",
          "impacts", "depends on", "what leads to", "which risks affect"

        Process:
          1. Search graph nodes matching key query terms
          2. Get subgraph (1-2 hops) around matched nodes
          3. Return LLM-readable relationship context

        Returns (graph_context_str, sources).
        Falls back silently to ("", []) if graph is empty or not initialized.
        """
        # Only activate for relationship-oriented queries
        q_lower = query.lower()
        relationship_keywords = [
            "connect", "link", "block", "caus", "related", "impact",
            "depend", "affect", "lead to", "because of", "due to",
            "which risks", "which deals", "why is", "how does",
        ]
        if not any(kw in q_lower for kw in relationship_keywords):
            return "", []

        db_path = self.get_project_db_path(project_context)
        if not db_path or not Path(db_path).exists():
            return "", []

        try:
            from infrastructure.graph_store import get_graph_store
            from infrastructure.graph_schema import NodeType

            store = get_graph_store(db_path, project_context.project_id, project_context.tenant_id)

            # Check if graph has been populated
            stats = store.stats()
            if stats["total_nodes"] == 0:
                return "", []

            # Extract search terms from the query (words > 3 chars, skip stopwords)
            STOPWORDS = {"what", "which", "that", "this", "with", "from", "have",
                         "does", "when", "where", "their", "about", "show", "tell",
                         "give", "list", "find", "are", "the", "and", "for"}
            words = [w.strip("?.,!") for w in q_lower.split() if len(w) > 3 and w not in STOPWORDS]

            # Search graph nodes for each key term
            matched_nodes = []
            seen_ids = set()
            for word in words[:5]:
                results = store.search_nodes(word, limit=3)
                for node in results:
                    if node.node_id not in seen_ids:
                        seen_ids.add(node.node_id)
                        matched_nodes.append(node)

            if not matched_nodes:
                return "", []

            # Get subgraph around matched nodes (depth 2)
            all_node_ids = [n.node_id for n in matched_nodes[:3]]
            graph_ctx = store.get_graph_context(all_node_ids, include_neighbors=True)

            # Add traversal info for the most relevant node
            root = matched_nodes[0]
            subgraph = store.get_subgraph(root.node_id, depth=2)
            if len(subgraph.nodes) > 1:
                graph_ctx += f"\n\nSUBGRAPH around '{root.label}' ({len(subgraph.nodes)} connected nodes):"
                for node in subgraph.nodes[:8]:
                    if node.node_id != root.node_id:
                        graph_ctx += f"\n  {node.summary()}"

            return f"KNOWLEDGE GRAPH:\n{graph_ctx}", ["knowledge_graph (Tier 5)"]

        except Exception as e:
            logger.debug(f"[ProjectCoordinator] Tier 5 retrieval failed (non-critical): {e}")
            return "", []

    # ── Prompt assembly ───────────────────────────────────────────────────────

    def _build_system_prompt(
        self,
        mode:        str,
        intel_agent,
        dept_id:     str,
    ) -> str:
        """
        Combine mode-based system prompt with department domain context.
        """
        base = self._SYSTEM_PROMPTS.get(mode, self._SYSTEM_PROMPTS["query"])

        # Add dept-specific domain knowledge to the system prompt
        if intel_agent and hasattr(intel_agent, "domain_knowledge"):
            dk = intel_agent.domain_knowledge
            concepts = ", ".join(dk.key_concepts[:10])
            dept_context = (
                f"\n\nYou are specialized in the {dept_id.upper()} department. "
                f"Key domain concepts: {concepts}. "
                f"Apply {dept_id} domain expertise when interpreting the data."
            )
            return base + dept_context

        return base

    def _build_user_prompt(
        self,
        query:           str,
        project_context: ProjectContext,
        retrieved_data:  str,
        history:         str,
        domain_intent:   str,
        mode:            str,
    ) -> str:
        """
        Assemble the full user-turn prompt sent to the LLM.

        Structure:
          [PROJECT CONTEXT — Tier 1]
          [PRIOR CONVERSATION — optional]
          [RETRIEVED DATA — Tier 2 + Tier 4]
          [USER QUESTION]
        """
        parts: list[str] = []

        # Tier 1: Project context prefix
        parts.append(self.build_project_prompt_prefix(project_context))

        # Prior conversation
        if history and history.strip():
            parts.append(f"PRIOR CONVERSATION:\n{history.strip()}\n")

        # Retrieved data
        if retrieved_data and retrieved_data.strip():
            parts.append(f"PROJECT DATA:\n{retrieved_data.strip()}\n")
        else:
            parts.append("PROJECT DATA: No relevant data found in the project database.\n")

        # Domain intent hint
        parts.append(f"DETECTED INTENT: {domain_intent}")

        # User question
        parts.append(f"\nUSER QUESTION ({mode.upper()} MODE):\n{query}")

        # Mode-specific instructions
        if mode == "query":
            parts.append(
                "\nAnswer the question directly. Cite specific numbers from the data. "
                "If data is missing, state what is unknown."
            )
        elif mode == "analysis":
            parts.append(
                "\nProvide a structured analysis with: Summary, Key Findings, "
                "Risks & Issues, and Recommendations."
            )
        elif mode == "planning":
            parts.append(
                "\nCreate a prioritized action plan with: Immediate Actions (this week), "
                "Short-term (30 days), Medium-term (60-90 days). "
                "Each action must reference specific data."
            )
        elif mode == "reporting":
            parts.append(
                "\nGenerate an executive status report with: Overall Health, "
                "Progress Summary, KPI Status, Risks, Next Milestones."
            )

        return "\n".join(parts)

    # ── Confidence scoring ────────────────────────────────────────────────────

    def _estimate_confidence(
        self,
        data_gaps:     list[str],
        sources:       list[str],
        domain_intent: str,
    ) -> float:
        """
        Estimate answer confidence based on data availability.
        Base: 0.75. Penalise for gaps. Bonus for multiple sources.
        """
        base = 0.75
        penalty = min(0.05 * len(data_gaps), 0.30)
        bonus   = min(0.02 * len(sources), 0.10)
        return round(max(0.1, min(0.95, base - penalty + bonus)), 2)

    # ── Lazy singletons ───────────────────────────────────────────────────────

    def _get_intel_agent(self, dept_id: str):
        if self._factory is None:
            from infrastructure.agent_factory import get_agent_factory
            self._factory = get_agent_factory()
        return self._factory.get_intelligence_agent(dept_id)

    async def _get_llm(self, tenant_id: str = "default"):
        """Return the LLM client configured for this tenant (cached by adapter layer)."""
        try:
            from infrastructure.llm_adapter import get_llm_for_tenant
            return await get_llm_for_tenant(tenant_id)
        except Exception as e:
            logger.warning(f"[ProjectCoordinator] Tenant LLM load failed ({e}), using global")
            from infrastructure.llm_client import get_llm
            return get_llm()


# ── Singleton ─────────────────────────────────────────────────────────────────

_coordinator: Optional[ProjectCoordinatorAgent] = None


def get_project_coordinator() -> ProjectCoordinatorAgent:
    global _coordinator
    if _coordinator is None:
        _coordinator = ProjectCoordinatorAgent()
    return _coordinator
