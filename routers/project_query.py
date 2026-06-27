"""
routers/project_query.py — Project-scoped LLM query endpoint.

POST /projects/{project_id}/query
POST /projects/portfolio/query   (cross-project portfolio queries)

This is the primary endpoint for project intelligence.
Unlike /query (which is department-scoped), this endpoint:
  1. Loads the ProjectContext for the user + project
  2. Routes through the ProjectCoordinatorAgent (Phase 2 agent pipeline)
  3. Grounds the query in project data (Tier 1 + Tier 2 + Tier 4 retrieval)
  4. Returns an answer with project-specific sources cited

Supports four modes:
  - query:     Answer a specific question from project data
  - analysis:  Surface patterns, trends, and risks
  - planning:  Generate a data-backed plan or forecast
  - reporting: Produce a structured document from project data
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.deps import get_current_user
from infrastructure.tenant_manager import DEFAULT_TENANT_ID
from infrastructure.project_context import get_project_context_manager, ProjectContext
from infrastructure.project_provisioner import get_project_provisioner

logger = logging.getLogger("rapid.project_query")

router = APIRouter(tags=["project-intelligence"])


# ── Request / Response models ─────────────────────────────────────────────────

class ProjectQueryRequest(BaseModel):
    query:      str
    mode:       str = "query"        # 'query' | 'analysis' | 'planning' | 'reporting'
    session_id: Optional[str] = None
    history:    list[dict] = []


class ProjectQueryResponse(BaseModel):
    query_id:      str
    project_id:    str
    mode:          str
    answer:        str
    confidence:    float
    sources:       list[str] = []
    data_gaps:     list[str] = []
    mode_used:     str
    duration_ms:   int
    agent_used:    str = "coordinator"
    domain_intent: str = "unknown"


class PortfolioQueryRequest(BaseModel):
    query:       str
    project_ids: list[str]           # Projects to include in portfolio view
    session_id:  Optional[str] = None


class PortfolioQueryResponse(BaseModel):
    query_id:      str
    answer:        str
    confidence:    float
    projects_used: list[str] = []
    data_gaps:     list[str] = []
    project_count: int = 0
    duration_ms:   int


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/query", response_model=ProjectQueryResponse)
async def project_query(
    project_id:   str,
    req:          ProjectQueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Project-scoped intelligence query.

    The agent answers from the project's own data, not the department database.
    Tier 1 context (metadata + KPIs) is always included.
    Tier 2 SQL retrieval fetches targeted data based on the query.
    """
    start_ms  = int(time.time() * 1000)
    query_id  = str(uuid.uuid4())
    tenant_id = current_user.get("tenant_id", DEFAULT_TENANT_ID)
    user_id   = current_user["sub"]

    if len(req.query) > 2000:
        raise HTTPException(status_code=400, detail="Query too long (max 2000 characters)")

    valid_modes = ("query", "analysis", "planning", "reporting")
    if req.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{req.mode}'. Must be one of: {valid_modes}",
        )

    # ── 1. Load project context ───────────────────────────────────────────────
    ctx_manager = get_project_context_manager()
    try:
        project_ctx = ctx_manager.load(
            project_id=project_id,
            user_id=user_id,
            tenant_id=tenant_id,
            mode=req.mode,
            session_id=req.session_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # ── 2. Build history context ──────────────────────────────────────────────
    history_context = ""
    if req.history:
        recent = req.history[-6:]
        history_context = "\n".join(
            f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
            for m in recent
        )

    # ── 3. Run the appropriate pipeline ──────────────────────────────────────
    try:
        result = await _dispatch(
            query_id=query_id,
            query=req.query,
            mode=req.mode,
            project_ctx=project_ctx,
            history_context=history_context,
            current_user=current_user,
        )
    except Exception as e:
        logger.error(f"[project_query] Pipeline error for {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query pipeline error: {e}")

    duration_ms = int(time.time() * 1000) - start_ms

    return ProjectQueryResponse(
        query_id=query_id,
        project_id=project_id,
        mode=req.mode,
        answer=result["answer"],
        confidence=result.get("confidence", 0.5),
        sources=result.get("sources", []),
        data_gaps=result.get("data_gaps", []),
        mode_used=result.get("mode_used", req.mode),
        duration_ms=duration_ms,
        agent_used=result.get("agent_used", "coordinator"),
        domain_intent=result.get("domain_intent", "unknown"),
    )


# ── Portfolio endpoint ────────────────────────────────────────────────────────

@router.post("/projects/portfolio/query", response_model=PortfolioQueryResponse)
async def portfolio_query(
    req:          PortfolioQueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Cross-project portfolio intelligence query.

    Accepts a list of project_ids and a question that spans all of them.
    Useful for managers asking: "Which of my projects is most at risk?"
    or "What are the common blockers across all Q3 initiatives?"
    """
    import time
    start_ms  = int(time.time() * 1000)
    query_id  = str(uuid.uuid4())
    tenant_id = current_user.get("tenant_id", DEFAULT_TENANT_ID)
    user_id   = current_user["sub"]

    if not req.project_ids:
        raise HTTPException(status_code=400, detail="At least one project_id required")
    if len(req.project_ids) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 projects per portfolio query")

    # Load contexts for all requested projects
    from agents.intelligence.portfolio_agent import get_portfolio_agent, load_portfolio_contexts
    contexts, failed = await load_portfolio_contexts(
        project_ids=req.project_ids,
        user_id=user_id,
        tenant_id=tenant_id,
        mode="query",
    )

    if not contexts:
        raise HTTPException(
            status_code=403,
            detail="No accessible projects found. Check project membership.",
        )

    portfolio_agent = get_portfolio_agent()
    try:
        result = await portfolio_agent.run(
            query=req.query,
            project_contexts=contexts,
            user_id=user_id,
        )
    except Exception as e:
        logger.error(f"[portfolio_query] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Portfolio query error: {e}")

    duration_ms = int(time.time() * 1000) - start_ms

    # Add failed projects to data_gaps
    gaps = result.data_gaps + [f"Could not load project: {pid}" for pid in failed]

    return PortfolioQueryResponse(
        query_id=query_id,
        answer=result.answer,
        confidence=result.confidence,
        projects_used=result.projects_used,
        data_gaps=gaps,
        project_count=result.project_count,
        duration_ms=duration_ms,
    )


# ── Dispatch logic ────────────────────────────────────────────────────────────

async def _dispatch(
    query_id:        str,
    query:           str,
    mode:            str,
    project_ctx:     ProjectContext,
    history_context: str,
    current_user:    dict,
) -> dict:
    """
    Route all project queries through the ProjectCoordinatorAgent (Phase 2).
    Falls back to raw-SQL pipeline if the coordinator fails to import.
    """
    try:
        from agents.intelligence.project_coordinator_agent import get_project_coordinator
        coordinator = get_project_coordinator()
        result = await coordinator.run(
            query=query,
            project_context=project_ctx,
            mode=mode,
            history=history_context,
        )
        return {
            "answer":        result.answer,
            "confidence":    result.confidence,
            "sources":       result.sources,
            "data_gaps":     result.data_gaps,
            "mode_used":     result.mode_used,
            "agent_used":    result.dept_agent_used,
            "domain_intent": result.domain_intent,
        }
    except ImportError as e:
        logger.warning(f"[dispatch] ProjectCoordinatorAgent unavailable, using legacy pipeline: {e}")

    # ── Legacy fallback (pre-Phase 2 raw SQL pipeline) ────────────────────────
    if mode == "query":
        return await _run_query_mode(query, project_ctx, history_context)
    elif mode == "analysis":
        return await _run_analysis_mode(query, project_ctx)
    elif mode in ("planning", "reporting"):
        return await _run_planning_mode(query, mode, project_ctx)
    else:
        return await _run_query_mode(query, project_ctx, history_context)


# ── Query mode ────────────────────────────────────────────────────────────────

async def _run_query_mode(
    query:          str,
    project_ctx:    ProjectContext,
    history_context: str,
) -> dict:
    """
    Tier 1 + Tier 2 retrieval → LLM generates natural language answer.
    """
    from infrastructure.llm_client import get_llm
    llm = get_llm()

    # Tier 1 is already in project_ctx.metadata and project_ctx.kpi_summary
    tier1_context = project_ctx.to_prompt_context()

    # Tier 2: fetch targeted data from project DB
    tier2_data, data_gaps, sources = await _tier2_retrieval(query, project_ctx)

    system_prompt = (
        "You are a project intelligence agent answering questions about a specific project. "
        "You have access to the project's data. Answer accurately and concisely. "
        "Always cite your data sources (which table the data came from). "
        "If data is missing or insufficient, say so explicitly — never guess. "
        "Do not expose raw row data or column names directly — convert to natural language."
    )

    user_prompt = (
        f"{tier1_context}\n"
        + (f"CONVERSATION HISTORY:\n{history_context}\n\n" if history_context else "")
        + f"PROJECT DATA (Tier 2 retrieval):\n{tier2_data}\n\n"
        + f"QUESTION: {query}"
    )

    try:
        answer = await llm.complete(user_prompt, system=system_prompt)
        confidence = _estimate_confidence(tier2_data, data_gaps)
    except Exception as e:
        logger.warning(f"[project_query] LLM call failed: {e}")
        answer = (
            f"I found some project data but could not generate a complete answer. "
            f"Here is what I retrieved:\n{tier2_data}"
        )
        confidence = 0.3

    return {
        "answer":     answer,
        "confidence": confidence,
        "sources":    sources,
        "data_gaps":  data_gaps,
        "mode_used":  "query",
    }


# ── Analysis mode ─────────────────────────────────────────────────────────────

async def _run_analysis_mode(query: str, project_ctx: ProjectContext) -> dict:
    """
    Tier 4 aggregated retrieval → LLM analyzes patterns and surfaces insights.
    Every claim must be grounded. Confidence scored. Data gaps flagged.
    """
    from infrastructure.llm_client import get_llm
    llm = get_llm()

    tier1_context = project_ctx.to_prompt_context()
    aggregated_data, data_gaps, sources = await _tier4_retrieval(project_ctx)

    system_prompt = (
        "You are a senior business analyst examining project data. "
        "Your job is to identify patterns, trends, anomalies, and risks. "
        "STRICT RULES:\n"
        "1. Every claim must cite which data it comes from.\n"
        "2. Flag any data gaps that limit your analysis.\n"
        "3. Express uncertainty when confidence is low.\n"
        "4. Do not invent data that is not in the provided context.\n"
        "5. Structure your response: Findings → Risks → Recommendations."
    )

    user_prompt = (
        f"{tier1_context}\n"
        f"AGGREGATED PROJECT DATA:\n{aggregated_data}\n\n"
        f"ANALYSIS REQUEST: {query}"
    )

    try:
        answer = await llm.complete(user_prompt, system=system_prompt)
        confidence = _estimate_confidence(aggregated_data, data_gaps)
    except Exception as e:
        logger.warning(f"[project_query] Analysis LLM call failed: {e}")
        answer = f"Analysis could not be completed: {e}"
        confidence = 0.1

    return {
        "answer":     answer,
        "confidence": confidence,
        "sources":    sources,
        "data_gaps":  data_gaps,
        "mode_used":  "analysis",
    }


# ── Planning mode ─────────────────────────────────────────────────────────────

async def _run_planning_mode(
    query: str, mode: str, project_ctx: ProjectContext
) -> dict:
    """
    Tier 2 + Tier 4 → LLM generates a structured plan grounded in current state.
    """
    from infrastructure.llm_client import get_llm
    llm = get_llm()

    tier1_context = project_ctx.to_prompt_context()
    tier2_data, data_gaps_2, sources_2 = await _tier2_retrieval(query, project_ctx)
    aggregated_data, data_gaps_4, sources_4 = await _tier4_retrieval(project_ctx)

    all_gaps = list(set(data_gaps_2 + data_gaps_4))
    all_sources = list(set(sources_2 + sources_4))

    action_word = "plan" if mode == "planning" else "report"

    system_prompt = (
        f"You are generating a project {action_word} grounded in real project data. "
        "STRICT RULES:\n"
        "1. Base every element of the plan on the actual data provided.\n"
        "2. Explicitly list your assumptions.\n"
        "3. Flag every data gap that could affect the plan's accuracy.\n"
        "4. Structure the output clearly with sections.\n"
        "5. Do not invent numbers or timelines not supported by the data."
    )

    user_prompt = (
        f"{tier1_context}\n"
        f"CURRENT PROJECT DATA:\n{tier2_data}\n\n"
        f"AGGREGATED METRICS:\n{aggregated_data}\n\n"
        f"REQUEST: {query}"
    )

    try:
        answer = await llm.complete(user_prompt, system=system_prompt)
        confidence = _estimate_confidence(tier2_data + aggregated_data, all_gaps)
    except Exception as e:
        logger.warning(f"[project_query] Planning LLM call failed: {e}")
        answer = f"Planning could not be completed: {e}"
        confidence = 0.1

    return {
        "answer":     answer,
        "confidence": confidence,
        "sources":    all_sources,
        "data_gaps":  all_gaps,
        "mode_used":  mode,
    }


# ── Data retrieval helpers ────────────────────────────────────────────────────

async def _tier2_retrieval(
    query: str,
    project_ctx: ProjectContext,
) -> tuple[str, list[str], list[str]]:
    """
    Tier 2: Focused SQL retrieval — query-aware, targets relevant tables.
    Returns (data_summary_str, data_gaps, sources).
    """
    import sqlite3 as _sqlite3
    db_path = project_ctx.db_path
    data_gaps, sources, sections = [], [], []

    if not Path(db_path).exists():
        return "No project data available yet.", ["project database not found"], []

    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = _sqlite3.Row

        query_lower = query.lower()

        # Always include milestones and risks for project queries
        milestones = conn.execute(
            "SELECT name, due_date, status, owner FROM project_milestones ORDER BY due_date LIMIT 10"
        ).fetchall()
        if milestones:
            sections.append("MILESTONES:\n" + "\n".join(
                f"  - {m['name']} | due: {m['due_date']} | status: {m['status']}"
                for m in milestones
            ))
            sources.append("project_milestones")
        else:
            data_gaps.append("No milestones recorded")

        # Risks if query is about risk/status/health
        risks = conn.execute(
            "SELECT title, probability, impact, status FROM project_risks WHERE status = 'open' LIMIT 5"
        ).fetchall()
        if risks:
            sections.append("OPEN RISKS:\n" + "\n".join(
                f"  - {r['title']} | prob: {r['probability']} | impact: {r['impact']}"
                for r in risks
            ))
            sources.append("project_risks")

        # Budget / finance related queries
        if any(w in query_lower for w in ["budget", "spend", "cost", "finance", "money", "invoice"]):
            try:
                budget_lines = conn.execute(
                    "SELECT category, allocated, spent, remaining FROM project_budget_lines LIMIT 20"
                ).fetchall()
                if budget_lines:
                    sections.append("BUDGET LINES:\n" + "\n".join(
                        f"  - {b['category']}: allocated={b['allocated']}, "
                        f"spent={b['spent']}, remaining={b['remaining']}"
                        for b in budget_lines
                    ))
                    sources.append("project_budget_lines")
            except Exception:
                data_gaps.append("Budget lines table not available for this project")

        # Task / progress related queries
        if any(w in query_lower for w in ["task", "progress", "done", "complete", "sprint", "todo"]):
            try:
                tasks = conn.execute(
                    """
                    SELECT title, assignee, status, priority, due_date
                    FROM project_tasks
                    WHERE status != 'done'
                    ORDER BY priority DESC, due_date
                    LIMIT 15
                    """
                ).fetchall()
                if tasks:
                    sections.append("OPEN TASKS:\n" + "\n".join(
                        f"  - [{t['status']}] {t['title']} | {t['assignee'] or 'unassigned'} | due: {t['due_date'] or 'N/A'}"
                        for t in tasks
                    ))
                    sources.append("project_tasks")
            except Exception:
                data_gaps.append("Tasks table not available for this project type")

        # Pipeline / sales related queries
        if any(w in query_lower for w in ["pipeline", "deal", "sales", "revenue", "close"]):
            try:
                deals = conn.execute(
                    """
                    SELECT customer_name, stage, value, close_date, probability
                    FROM project_pipeline
                    ORDER BY value DESC
                    LIMIT 15
                    """
                ).fetchall()
                if deals:
                    sections.append("SALES PIPELINE:\n" + "\n".join(
                        f"  - {d['customer_name']} | stage: {d['stage']} | "
                        f"value: {d['value']} | close: {d['close_date']}"
                        for d in deals
                    ))
                    sources.append("project_pipeline")
            except Exception:
                data_gaps.append("Pipeline table not available for this project type")

        conn.close()

    except Exception as e:
        logger.warning(f"[Tier2] DB read failed: {e}")
        data_gaps.append(f"Could not read project database: {e}")

    data_str = "\n\n".join(sections) if sections else "No specific data found for this query."
    return data_str, data_gaps, sources


async def _tier4_retrieval(project_ctx: ProjectContext) -> tuple[str, list[str], list[str]]:
    """
    Tier 4: Pre-aggregated data retrieval.
    Returns (aggregated_summary_str, data_gaps, sources).
    Pulls summary statistics — not raw rows.
    """
    import sqlite3 as _sqlite3
    db_path = project_ctx.db_path
    data_gaps, sources, sections = [], [], []

    if not Path(db_path).exists():
        return "No data available.", ["project database not found"], []

    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = _sqlite3.Row

        # Milestone completion stats
        ms_total = conn.execute("SELECT COUNT(*) as n FROM project_milestones").fetchone()["n"]
        ms_done  = conn.execute("SELECT COUNT(*) as n FROM project_milestones WHERE status = 'completed'").fetchone()["n"]
        ms_late  = conn.execute(
            "SELECT COUNT(*) as n FROM project_milestones WHERE status != 'completed' AND due_date < date('now')"
        ).fetchone()["n"]
        if ms_total > 0:
            sections.append(
                f"MILESTONE SUMMARY: {ms_done}/{ms_total} complete, {ms_late} overdue"
            )
            sources.append("project_milestones (aggregated)")
        else:
            data_gaps.append("No milestones defined")

        # KPI status distribution
        kpi_rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM project_kpis GROUP BY status"
        ).fetchall()
        if kpi_rows:
            kpi_summary = ", ".join(f"{r['status']}: {r['n']}" for r in kpi_rows)
            sections.append(f"KPI STATUS: {kpi_summary}")
            sources.append("project_kpis (aggregated)")

        # Risk profile
        risk_rows = conn.execute(
            "SELECT impact, COUNT(*) as n FROM project_risks WHERE status = 'open' GROUP BY impact"
        ).fetchall()
        if risk_rows:
            risk_summary = ", ".join(f"{r['impact']} impact: {r['n']}" for r in risk_rows)
            sections.append(f"OPEN RISK PROFILE: {risk_summary}")
            sources.append("project_risks (aggregated)")

        # Budget utilization (if available)
        try:
            budget_agg = conn.execute(
                "SELECT SUM(allocated) as total_alloc, SUM(spent) as total_spent FROM project_budget_lines"
            ).fetchone()
            if budget_agg and budget_agg["total_alloc"]:
                pct = (budget_agg["total_spent"] or 0) / budget_agg["total_alloc"] * 100
                sections.append(
                    f"BUDGET UTILIZATION: {pct:.1f}% spent "
                    f"({budget_agg['total_spent'] or 0:.0f} of {budget_agg['total_alloc']:.0f})"
                )
                sources.append("project_budget_lines (aggregated)")
        except Exception:
            pass

        conn.close()

    except Exception as e:
        logger.warning(f"[Tier4] Aggregation failed: {e}")
        data_gaps.append(f"Aggregation error: {e}")

    data_str = "\n".join(sections) if sections else "No aggregate data available."
    return data_str, data_gaps, sources


def _estimate_confidence(data_str: str, gaps: list) -> float:
    """Simple confidence estimate based on data richness and gaps."""
    base = 0.7
    if not data_str or data_str.strip() in ("", "No project data available yet."):
        base = 0.2
    elif len(data_str) < 100:
        base = 0.4
    penalty = len(gaps) * 0.05
    return max(0.1, min(0.95, base - penalty))
