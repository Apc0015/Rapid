"""Tenant-scoped organization query service shared by API and product surfaces."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks
from pydantic import BaseModel

from agents.system.audit_logger import get_audit
from shared import (
    INTENT_AMBIGUOUS,
    INTENT_GENERAL,
    INTENT_TRIVIAL,
    fusion,
    orchestrator,
    spokesperson,
    supervisor,
    web_agent,
)


class ChatMessage(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []
    attached_file_b64: Optional[str] = None
    attached_file_name: Optional[str] = None
    use_web: bool = False
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    query_id: str
    answer: str
    confidence: float
    warning: Optional[str] = None
    sources: list[str] = []
    dept_tags: list[str] = []
    action_taken: str
    provider_used: Optional[str] = None


def save_to_history(session_id: str, user_query: str, answer: str, background_tasks: BackgroundTasks) -> None:
    from infrastructure.chat_history import ChatHistory

    history = ChatHistory()
    background_tasks.add_task(history.append_message, session_id, "user", user_query)
    background_tasks.add_task(history.append_message, session_id, "assistant", answer)
    background_tasks.add_task(history.auto_title, session_id, user_query)


async def run_query(req: QueryRequest, current_user: dict, background_tasks: BackgroundTasks) -> QueryResponse:
    """Run the governed organization query pipeline for one tenant and user."""
    query_id = str(uuid.uuid4())
    audit = get_audit()
    user_id = current_user["sub"]

    from infrastructure.db_master import set_current_tenant
    from infrastructure.llm_adapter import get_llm_for_tenant
    from infrastructure.llm_client import set_active_llm
    from infrastructure.tenant_manager import DEFAULT_TENANT_ID
    from infrastructure.user_registry import load_users

    tenant_id = current_user.get("tenant_id", DEFAULT_TENANT_ID)
    set_current_tenant(tenant_id)
    tenant_llm = await get_llm_for_tenant(tenant_id)
    set_active_llm(tenant_llm)
    provider_name = getattr(tenant_llm, "provider_id", "auto")
    query_event = {
        "query_id": query_id,
        "user_id": user_id,
        "raw_query": req.query,
        "timestamp": datetime.utcnow().isoformat(),
        "provider": provider_name,
    }

    user_record = load_users().get(user_id, {})
    user_permissions = spokesperson.load_permissions(user_id, current_user.get("role", "employee"), user_record=user_record)
    query_event["intent_class"] = "AUTH_OK"
    history_context = "\n".join(f"{message.role.upper()}: {message.content}" for message in req.history[-6:])
    attached_file_context = await _extract_attachment(req, query_id)
    user_profile = {"role": current_user.get("role", "employee"), "permitted_departments": current_user.get("depts", [])}
    intent = (await spokesperson.classify_intent(req.query, user_profile, history_context)).get("intent")
    query_event["intent_class"] = intent

    async def direct_answer(result, action_label: str) -> QueryResponse:
        query_event.update({"depts_activated": [], "agents_selected": [], "composite_confidence": result.confidence, "action_taken": action_label})
        audit.log_query(query_event)
        response = QueryResponse(
            query_id=query_id,
            answer=result.summary,
            confidence=result.confidence,
            action_taken=action_label,
            sources=list(set(result.citations)) if result.citations else [],
            provider_used=provider_name,
        )
        if req.session_id:
            save_to_history(req.session_id, req.query, response.answer, background_tasks)
        return response

    if intent == INTENT_TRIVIAL:
        return await direct_answer(await spokesperson.handle_trivial(req.query, history_context), "trivial_direct")
    if intent == INTENT_GENERAL:
        result = await spokesperson.handle_general(req.query, history_context, attached_file_context)
        if req.use_web:
            try:
                web_result = await web_agent.run(req.query, result.summary)
                if web_result.confidence > 0.1 and web_result.summary:
                    result.summary += "\n\n" + web_result.summary
                    result.citations = web_result.citations
                    result.confidence = max(result.confidence, web_result.confidence)
            except Exception:
                pass
        return await direct_answer(result, "general_llm_web" if req.use_web else "general_llm")
    if intent == INTENT_AMBIGUOUS:
        return await direct_answer(await spokesperson.clarify(req.query), "clarification")

    department_results, gaps = await orchestrator.handle(query_id, req.query, user_permissions, intent or "")
    if not department_results:
        return await direct_answer(await spokesperson.handle_general(req.query, history_context, attached_file_context), "general_llm_no_bid")
    for gap_query in gaps:
        background_tasks.add_task(supervisor.flag_gap, {"query": gap_query, "user_id": user_id, "query_id": query_id})
    query_event["depts_activated"] = [result.dept_tag for result in department_results]
    query_event["agents_selected"] = list({result.dept_tag for result in department_results})

    decision = await fusion.run(department_results)
    action = decision["action"]
    if req.use_web:
        try:
            web_result = await web_agent.run(req.query, decision.get("answer", ""))
            if web_result.summary and web_result.confidence > 0.1:
                decision["answer"] += "\n\n**Web sources:**\n" + web_result.summary
            action = "returned_with_web"
        except Exception:
            pass
    elif action == "fallback":
        result = await spokesperson.handle_general(req.query, history_context, attached_file_context)
        decision["answer"] = result.summary
        decision["confidence"] = result.confidence
        action = "general_llm_fallback"

    query_event.update({"composite_confidence": decision["confidence"], "action_taken": action})
    audit.log_query(query_event)
    for result in department_results:
        background_tasks.add_task(supervisor.rate_agent, result.dept_tag, query_id, result, req.query)
    if action == "gap_flagged":
        background_tasks.add_task(supervisor.detect_gaps, audit.query_audit_trail(limit=200))

    response = QueryResponse(
        query_id=query_id,
        answer=decision["answer"],
        confidence=decision["confidence"],
        warning=decision.get("warning"),
        sources=list({citation for result in department_results for citation in result.citations}),
        dept_tags=list({result.dept_tag for result in department_results}),
        action_taken=action,
        provider_used=provider_name,
    )
    if req.session_id:
        save_to_history(req.session_id, req.query, response.answer, background_tasks)
    return response


async def _extract_attachment(req: QueryRequest, query_id: str) -> str:
    if not req.attached_file_b64 or not req.attached_file_name:
        return ""
    try:
        import base64
        import tempfile
        from infrastructure.doc_master import get_doc_master

        file_bytes = base64.b64decode(req.attached_file_b64)
        suffix = os.path.splitext(req.attached_file_name)[1].lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(file_bytes)
            path = handle.name
        try:
            text = get_doc_master()._load_text(Path(path))
            return text[:8000] + ("\n\n[… document truncated …]" if len(text) > 8000 else "")
        finally:
            os.unlink(path)
    except Exception:
        return f"[Could not read attached file for query {query_id[:8]}]"
