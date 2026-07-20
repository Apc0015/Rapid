"""Backward-compatible project intelligence endpoints backed by the shared gateway.

POST /projects/{project_id}/query
POST /projects/portfolio/query   (cross-project portfolio queries)

These endpoints preserve the original project API response models while routing
through the product-wide intelligence gateway. That gateway applies scope,
permissions, evidence, fallback behavior, and audit logging consistently.

Supports four modes:
  - query:     Answer a specific question from project data
  - analysis:  Surface patterns, trends, and risks
  - planning:  Generate a data-backed plan or forecast
  - reporting: Produce a structured document from project data
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from routers.deps import get_current_user

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
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Project-scoped intelligence query.

    The gateway validates project membership before dispatching to the project
    specialist with governed project and organization evidence.
    """
    if len(req.query) > 2000:
        raise HTTPException(status_code=400, detail="Query too long (max 2000 characters)")

    valid_modes = ("query", "analysis", "planning", "reporting")
    if req.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{req.mode}'. Must be one of: {valid_modes}",
        )

    try:
        from infrastructure.intelligence_gateway import IntelligenceRequest, get_intelligence_gateway

        response = await get_intelligence_gateway().ask(
            IntelligenceRequest(
                question=req.query,
                project_id=project_id,
                mode=req.mode,
                history=req.history,
            ),
            current_user,
            background_tasks,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        logger.error(f"[project_query] Pipeline error for {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query pipeline error: {e}")

    return ProjectQueryResponse(
        query_id=response.id,
        project_id=project_id,
        mode=req.mode,
        answer=response.answer,
        confidence=response.confidence,
        sources=response.sources,
        data_gaps=response.data_gaps,
        mode_used=response.mode,
        duration_ms=response.duration_ms or 0,
        agent_used=response.agent or "coordinator",
        domain_intent="unified_intelligence",
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
    try:
        from infrastructure.intelligence_gateway import get_intelligence_gateway
        response = await get_intelligence_gateway().ask_portfolio(req.query, req.project_ids, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        logger.error(f"[portfolio_query] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Portfolio query error: {e}")

    return PortfolioQueryResponse(
        query_id=response.id,
        answer=response.answer,
        confidence=response.confidence,
        projects_used=response.sources,
        data_gaps=response.data_gaps,
        project_count=len(response.sources),
        duration_ms=response.duration_ms or 0,
    )
