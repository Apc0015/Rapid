"""
agents/intelligence/portfolio_agent.py — Portfolio Agent.

The PortfolioAgent provides cross-project intelligence. It can:
  - Compare KPIs, milestones, and risks across multiple projects
  - Surface the highest-risk or worst-performing projects in a portfolio
  - Answer questions like "Which of my projects is most behind?" or
    "What are the common blockers across all active projects?"
  - Generate portfolio-level status summaries for managers

It works by:
  1. Accepting a list of ProjectContexts (one per project)
  2. Loading Tier 1 data from each context (already populated)
  3. Running lightweight Tier 4 aggregation SQL on each project DB
  4. Synthesizing a cross-project view and sending to LLM

The PortfolioAgent is read-only and never writes to any project DB.

Usage (from portfolio router or project_query with mode='portfolio'):
    portfolio_agent = get_portfolio_agent()
    result = await portfolio_agent.run(
        query="Which projects are at risk of missing deadline?",
        project_contexts=list_of_ctx,
        user_id="user_ayush",
    )
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents.base.project_aware_mixin import ProjectAwareMixin
from infrastructure.project_context import ProjectContext

logger = logging.getLogger(__name__)


# ── Response dataclass ────────────────────────────────────────────────────────

@dataclass
class PortfolioResult:
    """Structured result from the PortfolioAgent."""
    answer:         str
    confidence:     float
    projects_used:  list[str]   = field(default_factory=list)
    data_gaps:      list[str]   = field(default_factory=list)
    project_count:  int         = 0
    duration_ms:    int         = 0


# ── PortfolioAgent ────────────────────────────────────────────────────────────

class PortfolioAgent(ProjectAwareMixin):
    """
    Cross-project intelligence agent. Operates on a list of ProjectContexts.
    Aggregates data across projects and uses LLM to produce portfolio insights.
    """

    _SYSTEM_PROMPT = (
        "You are RAPID Portfolio Intelligence. You have data from multiple projects "
        "and must answer questions that span across them. "
        "Compare, rank, and synthesize — always cite project names and numbers. "
        "Identify cross-project patterns, common blockers, and portfolio-level risks. "
        "Be direct and data-driven. Flag missing data clearly."
    )

    async def run(
        self,
        query:            str,
        project_contexts: list[ProjectContext],
        user_id:          str = "unknown",
    ) -> PortfolioResult:
        """
        Run a cross-project portfolio query.

        Args:
            query:            The user's question spanning multiple projects
            project_contexts: List of fully-loaded ProjectContexts
            user_id:          User making the query (for logging)

        Returns:
            PortfolioResult with answer and per-project sourcing
        """
        import time
        t_start = time.monotonic()

        if not project_contexts:
            return PortfolioResult(
                answer="No projects provided for portfolio analysis.",
                confidence=0.0,
                project_count=0,
            )

        # 1. Collect Tier 1 summaries from all projects (already in context)
        tier1_summaries = self._build_tier1_summaries(project_contexts)

        # 2. Run Tier 4 aggregation on each project DB
        project_stats, data_gaps = await self._collect_tier4_all(project_contexts)

        # 3. Build LLM prompt
        user_prompt = self._build_portfolio_prompt(
            query, tier1_summaries, project_stats, user_id
        )

        # 4. Call LLM — use tenant from first project context
        tenant_id = project_contexts[0].tenant_id if project_contexts else "default"
        try:
            llm = await self._get_llm(tenant_id)
            answer = await llm.complete(user_prompt, system=self._SYSTEM_PROMPT)
        except Exception as e:
            logger.warning(f"[PortfolioAgent] LLM call failed: {e}")
            answer = (
                f"Portfolio data collected across {len(project_contexts)} projects "
                f"but LLM unavailable. Raw summary:\n\n{tier1_summaries}"
            )

        # 5. Confidence = average of per-project data availability
        projects_used = [ctx.project_name for ctx in project_contexts]
        confidence = max(0.1, min(0.9, 0.6 + 0.05 * len(project_contexts) - 0.05 * len(data_gaps)))
        duration_ms = int((time.monotonic() - t_start) * 1000)

        return PortfolioResult(
            answer=answer,
            confidence=confidence,
            projects_used=projects_used,
            data_gaps=data_gaps,
            project_count=len(project_contexts),
            duration_ms=duration_ms,
        )

    # ── Data collection ───────────────────────────────────────────────────────

    def _build_tier1_summaries(self, contexts: list[ProjectContext]) -> str:
        """
        Serialize Tier 1 data (metadata + KPIs) from all project contexts.
        These are already loaded — no DB access needed.
        """
        lines: list[str] = []
        for ctx in contexts:
            meta = ctx.metadata
            kpi_summary = ""
            if ctx.kpi_summary:
                kpi_lines = [
                    f"      {k['kpi_name']}: {k['current_value']}/{k['target_value']} "
                    f"{k['unit']} [{k['status']}]"
                    for k in ctx.kpi_summary[:6]
                ]
                kpi_summary = "\n    KPIs:\n" + "\n".join(kpi_lines)

            lines.append(
                f"PROJECT: {ctx.project_name} (dept: {ctx.dept_id})\n"
                f"  Status: {meta.get('health_status', ctx.project_status)} | "
                f"Completion: {meta.get('completion_pct', 0):.0f}% | "
                f"Budget used: {meta.get('budget_spent', 0)}/{meta.get('budget_total', 'N/A')} | "
                f"Target end: {meta.get('target_end_date', 'N/A')}"
                + kpi_summary
            )

        return "\n\n".join(lines)

    async def _collect_tier4_all(
        self,
        contexts: list[ProjectContext],
    ) -> tuple[str, list[str]]:
        """
        Run Tier 4 aggregation SQL on each project DB and collect results.
        Returns (combined_stats_string, list_of_gaps).
        """
        sections: list[str] = []
        all_gaps: list[str] = []

        for ctx in contexts:
            db_path = self.get_project_db_path(ctx)
            if not db_path or not Path(db_path).exists():
                all_gaps.append(f"{ctx.project_name}: database not found")
                continue

            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
                conn.row_factory = sqlite3.Row
                stats: list[str] = []

                # Milestones
                try:
                    r = conn.execute(
                        """
                        SELECT COUNT(*) total,
                               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) done,
                               SUM(CASE WHEN status IN ('pending','in_progress')
                                         AND due_date < date('now') THEN 1 ELSE 0 END) overdue
                        FROM project_milestones
                        """
                    ).fetchone()
                    if r and r["total"] > 0:
                        stats.append(
                            f"Milestones: {r['done']}/{r['total']} complete, "
                            f"{r['overdue']} overdue"
                        )
                except Exception:
                    pass

                # KPI below-target count
                try:
                    r = conn.execute(
                        "SELECT COUNT(*) cnt FROM project_kpis WHERE status != 'on_track'"
                    ).fetchone()
                    total_kpi = conn.execute("SELECT COUNT(*) cnt FROM project_kpis").fetchone()
                    if total_kpi and total_kpi["cnt"] > 0:
                        stats.append(
                            f"KPIs off-track: {r['cnt']}/{total_kpi['cnt']}"
                        )
                except Exception:
                    pass

                # Open risks (high-impact)
                try:
                    r = conn.execute(
                        "SELECT COUNT(*) cnt FROM project_risks WHERE status='open' AND impact='high'"
                    ).fetchone()
                    stats.append(f"High-impact open risks: {r['cnt']}")
                except Exception:
                    pass

                conn.close()

                if stats:
                    project_block = f"{ctx.project_name}:\n" + "\n".join(f"  {s}" for s in stats)
                    sections.append(project_block)

            except Exception as e:
                all_gaps.append(f"{ctx.project_name}: {e}")

        return "\n\n".join(sections), all_gaps

    # ── Prompt assembly ───────────────────────────────────────────────────────

    def _build_portfolio_prompt(
        self,
        query:        str,
        tier1:        str,
        tier4:        str,
        user_id:      str,
    ) -> str:
        parts = [
            f"PORTFOLIO OVERVIEW ({len(tier1.split('PROJECT:'))-1} projects)\n"
            f"User: {user_id}\n",
            "=== TIER 1: PROJECT SUMMARIES ===",
            tier1,
            "=== TIER 4: AGGREGATED STATS PER PROJECT ===",
            tier4 if tier4.strip() else "(No aggregated data available)",
            f"\nPORTFOLIO QUESTION:\n{query}",
            "\nAnswer in a structured format. Rank or compare projects where relevant. "
            "Highlight the most critical issues across the portfolio.",
        ]
        return "\n\n".join(parts)

    # ── Lazy helpers ──────────────────────────────────────────────────────────

    async def _get_llm(self, tenant_id: str = "default"):
        """Return the LLM client configured for this tenant."""
        try:
            from infrastructure.llm_adapter import get_llm_for_tenant
            return await get_llm_for_tenant(tenant_id)
        except Exception as e:
            logger.warning(f"[PortfolioAgent] Tenant LLM load failed ({e}), using global")
            from infrastructure.llm_client import get_llm
            return get_llm()


# ── Helper: load multiple project contexts ────────────────────────────────────

async def load_portfolio_contexts(
    project_ids: list[str],
    user_id:     str,
    tenant_id:   str,
    mode:        str = "query",
) -> tuple[list[ProjectContext], list[str]]:
    """
    Convenience helper: load ProjectContext for each project_id.
    Returns (loaded_contexts, failed_project_ids).
    Projects the user cannot access are silently skipped with a warning.
    """
    from infrastructure.project_context import get_project_context_manager
    ctx_mgr = get_project_context_manager()

    contexts: list[ProjectContext] = []
    failed:   list[str] = []

    for pid in project_ids:
        try:
            ctx = ctx_mgr.load(
                project_id=pid,
                user_id=user_id,
                tenant_id=tenant_id,
                mode=mode,
            )
            contexts.append(ctx)
        except Exception as e:
            logger.warning(f"[PortfolioAgent] Could not load context for {pid}: {e}")
            failed.append(pid)

    return contexts, failed


# ── Singleton ─────────────────────────────────────────────────────────────────

_portfolio_agent: Optional[PortfolioAgent] = None


def get_portfolio_agent() -> PortfolioAgent:
    global _portfolio_agent
    if _portfolio_agent is None:
        _portfolio_agent = PortfolioAgent()
    return _portfolio_agent
