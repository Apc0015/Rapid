"""
RAPID — FastAPI application entry point.
Production-hardened:
  - JWT Bearer auth on /query (no more user_id+token in body)
  - Rate limiting via slowapi
  - Request timeout (120s)
  - CORS restricted to configured origins
  - Secrets validation on startup
  - Periodic JWT cleanup
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

# ── Shared singletons ─────────────────────────────────────────────────────────
from shared import (
    AGENT_REGISTRY,
    orchestrator,
    spokesperson, planner, fusion, web_agent, supervisor,
    INTENT_TRIVIAL, INTENT_GENERAL, INTENT_AMBIGUOUS,
    mem,
)
from agents.system.audit_logger import get_audit
from agents.system.governance_filter import get_governance
from routers.deps import get_current_user
from infrastructure.jwt_manager import get_jwt_manager
from infrastructure.query_service import QueryRequest, QueryResponse, run_query

# ── Routers ───────────────────────────────────────────────────────────────────
from routers.auth           import router as auth_router
from routers.users          import router as users_router
from routers.admin          import router as admin_router
from routers.documents      import router as documents_router
from routers.database       import router as database_router
from routers.llm            import router as llm_router
from routers.monitoring     import router as monitoring_router
from routers.chat_sessions  import router as sessions_router
from routers.cloud_onedrive import router as onedrive_router
from routers.cloud_gmail    import router as gmail_router
from routers.cloud_gdrive   import router as gdrive_router
from routers.cloud_github   import router as github_router
from routers.admin_folders  import router as admin_folders_router
from routers.departments    import router as departments_router
from routers.backup         import router as backup_router

# ── Phase 1 + 2: Project intelligence routers ────────────────────────────────
from routers.projects       import router as projects_router
from routers.project_query  import router as project_query_router

# Phase 5: Human-in-the-Loop routers
from routers.actions        import router as actions_router

# Phase 6: Agent Skill Library
from routers.skills         import router as skills_router

# Phase 7: Universal Business Layer
from routers.people         import router as people_router
from routers.search         import router as search_router
from routers.library        import router as library_router

# Phase 8: Industry Packs
from routers.packs          import router as packs_router

# Phase 9: Dynamic Agent Management
from routers.custom_agents    import router as custom_agents_router
from routers.nl_agent_creator import router as nl_agent_creator_router
from routers.hr               import router as hr_router
from routers.it               import router as it_router
from routers.finance          import router as finance_router
from routers.marketing        import router as marketing_router
from orgos.api                import org_router
from routers.people_ops       import router as people_ops_router
from routers.organization     import router as organization_router
from routers.organization_data import router as organization_data_router
from routers.organization_integrations import router as organization_integrations_router
from routers.organization_structure import router as organization_structure_router
from routers.workspace import router as workspace_router
from routers.tenant_admin import router as tenant_admin_router
from routers.jobs import router as jobs_router
from routers.intelligence import router as intelligence_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("rapid")


# ── Secrets validation ────────────────────────────────────────────────────────

def _validate_secrets():
    """Validate secrets on startup. Hard-fails in production for weak JWT keys."""
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    if not jwt_secret or jwt_secret == "CHANGE_ME_IN_PRODUCTION":
        if os.getenv("RAPID_ENV", "development") == "production":
            raise RuntimeError(
                "JWT_SECRET_KEY must be set to a strong random value in production. "
                "Refusing to start."
            )
        else:
            logger.warning(
                "[SECURITY] JWT_SECRET_KEY is not set or is default — "
                "set a strong random key in .env"
            )
    if not os.getenv("SERPER_API_KEY"):
        logger.info("SERPER_API_KEY not set — web search will be disabled")


# ── Rate limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ── CORS origins ──────────────────────────────────────────────────────────────

def _get_cors_origins() -> list[str]:
    env = os.getenv("ALLOWED_ORIGINS", "")
    if env.strip():
        return [o.strip() for o in env.split(",") if o.strip()]
    is_production = os.getenv("RAPID_ENV", "development") == "production"
    if is_production:
        # In production: no default — ALLOWED_ORIGINS must be set explicitly.
        logger.warning(
            "[SECURITY] ALLOWED_ORIGINS not set in production — defaulting to empty list. "
            "Set ALLOWED_ORIGINS in .env to allow your frontend domain."
        )
        return []
    # Development: allow local frontend origins.
    # 'null' and file:// are intentionally excluded even in dev for security hygiene;
    # use http://localhost:<port> for local HTML frontends instead.
    return [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8080",
        "http://localhost:5500",   # VS Code Live Server
        "http://localhost:4173",   # RAPID static product preview
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5500",
        "http://127.0.0.1:4173",
    ]


def _get_cors_origin_regex() -> Optional[str]:
    """Return origin regex only in development (never in production)."""
    if os.getenv("RAPID_ENV", "development") == "production":
        return None
    # Allow file:// in dev only — VS Code Live Server and direct HTML opens
    return r"file://.*"


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_secrets()
    logger.info("RAPID starting up — loading Constitution and schemas…")
    get_governance()

    # Initialise the user DB (creates table + seeds from users.yaml on first run).
    # After this, all auth reads come from the DB — zero operator steps required.
    try:
        from infrastructure.user_registry import init_user_db, load_users
        init_user_db()
        app.state.users_cache = load_users()
        logger.info(f"User DB ready ({len(app.state.users_cache)} accounts cached)")
    except Exception as e:
        logger.warning(f"Could not initialise user DB: {e}")
        app.state.users_cache = {}

    # Phase 1: Initialize multi-tenancy and project platform tables
    try:
        from infrastructure.tenant_manager import get_tenant_manager
        from infrastructure.department_manager import get_department_manager
        from infrastructure.project_provisioner import get_project_provisioner
        get_tenant_manager()        # creates tenants table + default tenant
        get_department_manager()    # creates departments table + default 10 depts
        get_project_provisioner()   # creates all project platform tables
        logger.info("Phase 1 — Tenant, Department, and Project platform tables ready")
    except Exception as e:
        logger.warning(f"Phase 1 platform init warning (non-fatal): {e}")

    # Phase 2: Pre-warm the Dynamic Agent Factory
    try:
        from infrastructure.agent_factory import get_agent_factory
        factory = get_agent_factory()
        logger.info(
            f"Phase 2 — DynamicAgentFactory ready "
            f"({len(factory.list_available_depts())} dept agents available)"
        )
    except Exception as e:
        logger.warning(f"Phase 2 agent factory init warning (non-fatal): {e}")

    logger.info(f"Agents registered: {list(AGENT_REGISTRY.keys())}")

    # Periodic JWT cleanup (every 6 hours)
    async def _cleanup_loop():
        while True:
            await asyncio.sleep(6 * 3600)
            try:
                get_jwt_manager().cleanup_expired()
                logger.debug("JWT cleanup: expired tokens removed")
            except Exception as e:
                logger.warning(f"JWT cleanup failed: {e}")

    # Periodic AgentMemory stale-context cleanup (every 60 seconds)
    async def _memory_cleanup_loop():
        while True:
            await asyncio.sleep(60)
            try:
                removed = await mem.cleanup_stale(max_age=120)
                if removed:
                    logger.info(f"AgentMemory cleanup: removed {removed} stale query context(s)")
            except Exception as e:
                logger.warning(f"AgentMemory cleanup failed: {e}")

    cleanup_task = asyncio.create_task(_cleanup_loop())
    memory_cleanup_task = asyncio.create_task(_memory_cleanup_loop())

    # Schedule execution is opt-in because production deployments should assign
    # exactly one worker replica this responsibility.
    scheduler_task = None
    if os.getenv("RAPID_ENABLE_SCHEDULER", "false").lower() in {"1", "true", "yes"}:
        interval_seconds = max(30, int(os.getenv("RAPID_SCHEDULER_INTERVAL_SECONDS", "60")))

        async def _automation_scheduler_loop():
            from infrastructure.integration_hub import get_integration_hub
            while True:
                try:
                    results = get_integration_hub().dispatch_due_schedules()
                    if results:
                        logger.info("Organization scheduler dispatched %s run(s)", len(results))
                except Exception as e:
                    logger.warning(f"Organization scheduler failed: {e}")
                await asyncio.sleep(interval_seconds)

        scheduler_task = asyncio.create_task(_automation_scheduler_loop())
        logger.info("Organization scheduler started (interval=%ss)", interval_seconds)

    from infrastructure.job_handlers import register_default_job_handlers
    register_default_job_handlers()
    job_worker_task = None
    if os.getenv("RAPID_ENABLE_JOB_WORKER", "false").lower() in {"1", "true", "yes"}:
        from infrastructure.job_queue import run_worker
        job_worker_task = asyncio.create_task(run_worker(poll_seconds=float(os.getenv("RAPID_JOB_POLL_SECONDS", "1"))))
        logger.info("Durable job worker started")

    # Phase 5: Start background project monitor
    try:
        from infrastructure.monitoring_loop import get_background_monitor
        _monitor_task = asyncio.create_task(get_background_monitor().start())
        logger.info("Phase 5 — BackgroundMonitor started (project health monitoring active)")
    except Exception as e:
        logger.warning(f"Phase 5 monitor start warning (non-fatal): {e}")
        _monitor_task = None

    # Folder watchers: start any pre-configured watchers
    try:
        from infrastructure.folder_watcher import get_folder_watcher
        get_folder_watcher().start_all()
        logger.info("FolderWatcher — started all registered local folder watchers")
    except Exception as e:
        logger.warning(f"FolderWatcher start warning (non-fatal): {e}")

    yield

    # Graceful shutdown: stop all folder watchers
    try:
        from infrastructure.folder_watcher import get_folder_watcher
        await get_folder_watcher().stop_all()
        logger.info("FolderWatcher — all watchers stopped cleanly")
    except Exception as e:
        logger.warning(f"FolderWatcher shutdown warning: {e}")

    cleanup_task.cancel()
    memory_cleanup_task.cancel()

    if _monitor_task:
        _monitor_task.cancel()
    if scheduler_task:
        scheduler_task.cancel()
    if job_worker_task:
        job_worker_task.cancel()
    logger.info("RAPID shutting down")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="RAPID Organization OS",
    description="Governed autonomous workflows for organization-wide operations",
    version="3.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter

from infrastructure.security_middleware import RapidSecurityMiddleware
app.add_middleware(RapidSecurityMiddleware)


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 handler — gives a clear, actionable message on login; generic elsewhere."""
    if "/auth/login" in request.url.path:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many login attempts. Please wait 60 seconds and try again."},
        )
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Please slow down."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# CORS — restricted to configured origins; null/file:// blocked in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_origin_regex=_get_cors_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Idempotency-Key", "X-Rapid-Signature", "X-Rapid-Timestamp"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
if os.getenv("RAPID_ENV", "development") == "production":
    allowed_hosts = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()]
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# Register routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(documents_router)
app.include_router(database_router)
app.include_router(llm_router)
app.include_router(monitoring_router)
app.include_router(sessions_router)
app.include_router(onedrive_router)
app.include_router(gmail_router)
app.include_router(gdrive_router)
app.include_router(github_router)
app.include_router(admin_folders_router)
app.include_router(departments_router)
app.include_router(backup_router)

# Phase 1: Project intelligence
app.include_router(projects_router)
app.include_router(project_query_router)
app.include_router(actions_router)
app.include_router(skills_router)

# Phase 7: Universal Business Layer
app.include_router(people_router)
app.include_router(search_router)
app.include_router(library_router)

# Phase 8: Industry Packs
app.include_router(packs_router)

# Phase 9: Dynamic Agent Management
app.include_router(custom_agents_router)
app.include_router(nl_agent_creator_router)
app.include_router(people_ops_router)
app.include_router(organization_router)
app.include_router(organization_data_router)
app.include_router(organization_integrations_router)
app.include_router(organization_structure_router)
app.include_router(workspace_router)
app.include_router(tenant_admin_router)
app.include_router(jobs_router)
app.include_router(intelligence_router)

# Digital Organization — HR, IT, Finance, Marketing (built departments)
app.include_router(hr_router)
app.include_router(it_router)
app.include_router(finance_router)
app.include_router(marketing_router)
app.include_router(org_router)

# ── Product portal handoff ────────────────────────────────────────────────────
from fastapi.responses import RedirectResponse


def _portal_url() -> str:
    """Return the React portal origin for local development or deployment."""
    default = "/" if os.getenv("RAPID_ENV", "development") == "production" else "http://127.0.0.1:4173"
    return os.getenv("RAPID_PORTAL_URL", default).rstrip("/")


@app.get("/", include_in_schema=False)
async def _root():
    return RedirectResponse(url=f"{_portal_url()}/login")


@app.get("/app/{legacy_path:path}", include_in_schema=False)
async def _legacy_product_redirect(legacy_path: str):
    """Retire the original static department consoles in favor of one portal."""
    return RedirectResponse(url=f"{_portal_url()}/workspace/overview")


# ── Main query endpoint ───────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse, deprecated=True)
@limiter.limit("30/minute")
async def query(
    request:          Request,
    req:              QueryRequest,
    background_tasks: BackgroundTasks,
    current_user:     dict = Depends(get_current_user),
):
    """
    Backward-compatible raw agent query endpoint — JWT Bearer auth required.
    Product surfaces use /intelligence/ask, which resolves shared scope,
    permissions, evidence, and specialist routing first.
    Rate limited: 30 queries/minute per IP.
    Times out after 120 seconds.
    """
    # Enforce max query length
    if len(req.query) > 2000:
        raise HTTPException(status_code=400, detail="Query too long (max 2000 characters)")

    try:
        return await asyncio.wait_for(
            run_query(req, current_user, background_tasks),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"Query timed out for user={current_user['sub']}: '{req.query[:60]}'")
        raise HTTPException(status_code=504, detail="Query timed out — try a simpler question")
# ── Lean grounded Q&A (Ask RAPID) ─────────────────────────────────────────────
# The full /query pipeline fans out to the whole multi-agent org — dozens of
# LLM calls, built for cloud providers. /ask is the lean complement the console
# uses: one query embedding, retrieval scores pick the department, then the
# proven RAG pipeline produces ONE grounded, cited answer. Works well on a
# local Ollama model.

@app.post("/ask", response_model=QueryResponse)
@limiter.limit("30/minute")
async def ask(
    request:      Request,
    req:          QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    if len(req.query) > 2000:
        raise HTTPException(status_code=400, detail="Query too long (max 2000 characters)")

    from infrastructure.embedding_service import get_embedder
    from infrastructure.faiss_store import get_dept_index
    from infrastructure.dept_config import get_dept_config
    from pipelines.rag_pipeline import run_rag_pipeline
    from infrastructure.llm_client import get_llm

    query_id = str(uuid.uuid4())

    # Departments this user may search: from the JWT depts claim; privileged
    # roles (and users with no dept restriction) search everything indexed.
    # Indexes are tenant-scoped on disk: data/faiss/{tenant}/{dept}.
    tenant_id = current_user.get("tenant_id", "default")
    faiss_root = Path("data/faiss") / tenant_id
    indexed = sorted(d.name for d in faiss_root.iterdir() if d.is_dir()) if faiss_root.exists() else []
    role  = current_user.get("role", "employee")
    depts = current_user.get("depts") or []
    if role in ("admin", "ceo", "board_member") or not depts:
        candidates = indexed
    else:
        candidates = [d for d in indexed if d in depts]
    if not candidates:
        return QueryResponse(
            query_id=query_id, answer="No document knowledge base is available for your departments yet.",
            confidence=0.1, action_taken="ask_no_index")

    # Route by retrieval: embed once, take the department whose index scores
    # highest for this query.
    embedder = get_embedder()
    cfg_all  = get_dept_config()
    emb_cache: dict = {}
    best_dept, best_score = None, 0.0
    for d in candidates:
        model = cfg_all.get_rag(d).get("embedding_model", "nomic-embed-text")
        if model not in emb_cache:
            emb_cache[model] = await embedder.embed(req.query, model=model)
        idx = get_dept_index(d, dim=embedder.dim_for_model(model), tenant_id=tenant_id)
        if idx.doc_count == 0:
            continue
        hits = await idx.vector_search(emb_cache[model], top_k=1)
        if hits and hits[0][1] > best_score:
            best_dept, best_score = d, hits[0][1]

    if best_dept is None:
        return QueryResponse(
            query_id=query_id,
            answer="Nothing in the indexed company documents matches this question.",
            confidence=0.1, action_taken="ask_no_match")

    logger.info(f"[{query_id[:8]}] /ask routed to dept={best_dept} (score {best_score:.3f})")
    try:
        result = await asyncio.wait_for(
            run_rag_pipeline(req.query, best_dept, {}), timeout=180.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Answer timed out — try a simpler question")

    get_audit().log_query({
        "query_id": query_id, "user_id": current_user["sub"],
        "raw_query": req.query, "timestamp": datetime.utcnow().isoformat(),
        "intent_class": "ASK_RAG", "depts_activated": [best_dept],
        "composite_confidence": result.confidence, "action_taken": "ask_rag",
    })
    return QueryResponse(
        query_id=query_id,
        answer=result.summary,
        confidence=result.confidence,
        warning=None if result.confidence >= 0.7 else
            f"⚠️ Confidence moderate ({result.confidence:.0%}). Please verify this answer if it is critical to a decision.",
        sources=list(result.citations or []),
        dept_tags=[best_dept],
        action_taken="ask_rag",
        provider_used=getattr(get_llm(), "provider_id", "auto"),
    )
