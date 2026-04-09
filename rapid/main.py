from __future__ import annotations
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
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── Shared singletons ─────────────────────────────────────────────────────────
from shared import (
    AGENT_REGISTRY,
    orchestrator,
    spokesperson, planner, fusion, web_agent, supervisor,
    INTENT_TRIVIAL, INTENT_GENERAL, INTENT_AMBIGUOUS,
)
from agents.audit_logger import get_audit
from agents.governance_filter import get_governance
from routers.deps import get_current_user
from infrastructure.jwt_manager import get_jwt_manager

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
from routers.departments    import router as departments_router
from routers.backup         import router as backup_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("rapid")


# ── Secrets validation ────────────────────────────────────────────────────────

def _validate_secrets():
    """Warn on startup about missing or default secrets."""
    issues = []
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    if not jwt_secret or jwt_secret == "CHANGE_ME_IN_PRODUCTION":
        issues.append("JWT_SECRET_KEY is not set or is default — set a strong random key in .env")
    if not os.getenv("SERPER_API_KEY"):
        logger.info("SERPER_API_KEY not set — web search will be disabled")
    for issue in issues:
        logger.warning(f"[SECURITY] {issue}")
    if issues:
        logger.warning("[SECURITY] Fix the above before deploying to production")


# ── Rate limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ── CORS origins ──────────────────────────────────────────────────────────────

def _get_cors_origins() -> list[str]:
    env = os.getenv("ALLOWED_ORIGINS", "")
    if env.strip():
        return [o.strip() for o in env.split(",") if o.strip()]
    # Default: allow Flutter web dev server + localhost
    return [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ]


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_secrets()
    logger.info("RAPID starting up — loading Constitution and schemas…")
    get_governance()
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

    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    cleanup_task.cancel()
    logger.info("RAPID shutting down")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="RAPID",
    description="RAG Application for Private Instant Deployment",
    version="2.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — restricted
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

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
app.include_router(departments_router)
app.include_router(backup_router)


# ── Request / Response models ─────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role:    str
    content: str


class QueryRequest(BaseModel):
    query:              str
    history:            list[ChatMessage] = []
    attached_file_b64:  Optional[str] = None
    attached_file_name: Optional[str] = None
    use_web:            bool = False
    session_id:         Optional[str] = None


class QueryResponse(BaseModel):
    query_id:     str
    answer:       str
    confidence:   float
    warning:      Optional[str] = None
    sources:      list[str] = []
    dept_tags:    list[str] = []
    action_taken: str


# ── Main query endpoint ───────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
@limiter.limit("30/minute")
async def query(
    request:          Request,
    req:              QueryRequest,
    background_tasks: BackgroundTasks,
    current_user:     dict = Depends(get_current_user),
):
    """
    Full query pipeline — JWT Bearer auth required.
    Rate limited: 30 queries/minute per IP.
    Times out after 120 seconds.
    """
    # Enforce max query length
    if len(req.query) > 2000:
        raise HTTPException(status_code=400, detail="Query too long (max 2000 characters)")

    try:
        return await asyncio.wait_for(
            _run_query(req, current_user, background_tasks),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"Query timed out for user={current_user['sub']}: '{req.query[:60]}'")
        raise HTTPException(status_code=504, detail="Query timed out — try a simpler question")


async def _run_query(
    req:              QueryRequest,
    current_user:     dict,
    background_tasks: BackgroundTasks,
) -> QueryResponse:
    query_id = str(uuid.uuid4())
    audit    = get_audit()
    user_id  = current_user["sub"]

    query_event = {
        "query_id":  query_id,
        "user_id":   user_id,
        "raw_query": req.query,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # ── 1. Load permissions from JWT payload ──────────────────────────────────
    # No DB lookup needed — permissions are embedded in the token
    import yaml as _yaml
    users_path = Path("data/users.yaml")
    users      = _yaml.safe_load(users_path.read_text()) if users_path.exists() else {}
    user_record = users.get(user_id, {})

    user_permissions = spokesperson.load_permissions(
        user_id,
        current_user.get("role", "employee"),
        user_record=user_record,
    )
    query_event["intent_class"] = "AUTH_OK"

    # ── 2. Build history context ──────────────────────────────────────────────
    history_context = ""
    if req.history:
        recent = req.history[-6:]
        history_context = "\n".join(f"{m.role.upper()}: {m.content}" for m in recent)

    # ── 3. Extract attached file ──────────────────────────────────────────────
    attached_file_context = ""
    if req.attached_file_b64 and req.attached_file_name:
        try:
            import base64, tempfile
            from infrastructure.doc_master import get_doc_master
            file_bytes = base64.b64decode(req.attached_file_b64)
            suffix = os.path.splitext(req.attached_file_name)[1].lower()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                doc = get_doc_master()
                attached_file_context = doc._load_text(Path(tmp_path))
                if len(attached_file_context) > 8000:
                    attached_file_context = attached_file_context[:8000] + "\n\n[… document truncated …]"
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.warning(f"[{query_id[:8]}] Failed to extract attached file: {e}")
            attached_file_context = f"[Could not read attached file: {e}]"

    # ── 4. Classify intent ────────────────────────────────────────────────────
    # Build a minimal user_profile dict for spokesperson compatibility
    user_profile = {
        "role": current_user.get("role", "employee"),
        "permitted_departments": current_user.get("depts", []),
    }
    intent_result = await spokesperson.classify_intent(req.query, user_profile, history_context)
    intent = intent_result.get("intent")
    query_event["intent_class"] = intent
    logger.info(f"[{query_id[:8]}] user={user_id} intent={intent} query='{req.query[:60]}'")

    # ── 5. Direct-answer helper ───────────────────────────────────────────────
    async def _direct_answer(result, action_label: str) -> QueryResponse:
        query_event.update({
            "depts_activated":      [],
            "agents_selected":      [],
            "composite_confidence": result.confidence,
            "action_taken":         action_label,
        })
        audit.log_query(query_event)
        resp = QueryResponse(
            query_id=query_id,
            answer=result.summary,
            confidence=result.confidence,
            action_taken=action_label,
            sources=list(set(result.citations)) if result.citations else [],
        )
        if req.session_id:
            _save_to_history(req.session_id, req.query, resp.answer, background_tasks)
        return resp

    if intent == INTENT_TRIVIAL:
        return await _direct_answer(
            await spokesperson.handle_trivial(req.query, history_context), "trivial_direct"
        )
    if intent == INTENT_GENERAL:
        llm_result = await spokesperson.handle_general(req.query, history_context, attached_file_context)
        if req.use_web:
            try:
                web_result = await web_agent.run(req.query, llm_result.summary)
                if web_result.confidence > 0.1 and web_result.summary:
                    llm_result.summary    += "\n\n" + web_result.summary
                    llm_result.citations   = web_result.citations
                    llm_result.confidence  = max(llm_result.confidence, web_result.confidence)
            except Exception as e:
                logger.warning(f"Web augmentation failed: {e}")
        return await _direct_answer(llm_result, "general_llm_web" if req.use_web else "general_llm")

    if intent == INTENT_AMBIGUOUS:
        return await _direct_answer(
            await spokesperson.clarify(req.query), "clarification"
        )

    # ── 6. Orchestrate → hierarchy-aware dispatch + escalation ────────────────
    dept_results, gaps = await orchestrator.handle(
        query_id, req.query, user_permissions, intent_result.get("intent", "")
    )

    if not dept_results:
        return await _direct_answer(
            await spokesperson.handle_general(req.query, history_context, attached_file_context),
            "general_llm_no_bid",
        )

    if gaps:
        for gap_query in gaps:
            background_tasks.add_task(
                supervisor.flag_gap,
                {"query": gap_query, "user_id": user_id, "query_id": query_id},
            )

    query_event["depts_activated"] = [r.dept_tag for r in dept_results]
    query_event["agents_selected"] = list({r.dept_tag for r in dept_results})

    # ── 7. Fusion ─────────────────────────────────────────────────────────────
    decision = await fusion.run(dept_results)

    # ── 8. Web augmentation / LLM fallback ───────────────────────────────────
    action = decision["action"]
    if req.use_web:
        try:
            web_result = await web_agent.run(req.query, decision.get("answer", ""))
            if web_result.summary and web_result.confidence > 0.1:
                decision["answer"] += "\n\n**Web sources:**\n" + web_result.summary
            action = "returned_with_web"
        except Exception as e:
            logger.warning(f"Web agent failed: {e}")
    elif action == "fallback":
        result = await spokesperson.handle_general(req.query, history_context, attached_file_context)
        decision["answer"]     = result.summary
        decision["confidence"] = result.confidence
        action = "general_llm_fallback"

    # ── 9. Audit + agent rating ───────────────────────────────────────────────
    query_event.update({
        "composite_confidence": decision["confidence"],
        "action_taken":         action,
    })
    audit.log_query(query_event)
    for result in dept_results:
        background_tasks.add_task(supervisor.rate_agent, result.dept_tag, query_id, result)

    # ── 10. Response ──────────────────────────────────────────────────────────
    all_citations = [c for r in dept_results for c in r.citations]
    response = QueryResponse(
        query_id=query_id,
        answer=decision["answer"],
        confidence=decision["confidence"],
        warning=decision.get("warning"),
        sources=list(set(all_citations)),
        dept_tags=list({r.dept_tag for r in dept_results}),
        action_taken=action,
    )
    if req.session_id:
        _save_to_history(req.session_id, req.query, response.answer, background_tasks)
    return response


# ── History helper ────────────────────────────────────────────────────────────

def _save_to_history(session_id, user_query, answer, background_tasks):
    from infrastructure.chat_history import ChatHistory
    ch = ChatHistory()
    background_tasks.add_task(ch.append_message, session_id, "user",      user_query)
    background_tasks.add_task(ch.append_message, session_id, "assistant", answer)
    background_tasks.add_task(ch.auto_title,     session_id, user_query)
