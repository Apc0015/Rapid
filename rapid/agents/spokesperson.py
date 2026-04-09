from __future__ import annotations
"""
Spokesperson — Tier 2 Executive Agent.
The ONLY agent the user interacts with directly.
Authenticates users, classifies intent, routes to Master Planner or answers trivially.
~40% of enterprise queries are trivial and answered here without activating any other agent.
"""

import asyncio
import logging
import uuid
from typing import Optional
from pathlib import Path
import yaml

from models.nl_result import NLResult
from agents.governance_filter import get_governance
from infrastructure.llm_client import get_llm
from infrastructure.user_registry import (
    verify_password,
    get_user_division_head_of,
    DIVISION_DEPTS,
    AGGREGATE_ONLY_ROLES,
)

logger = logging.getLogger(__name__)

INTENT_TRIVIAL    = "TRIVIAL"
INTENT_GENERAL    = "GENERAL"
INTENT_SINGLE_DEPT = "SINGLE_DEPT"
INTENT_MULTI_DEPT  = "MULTI_DEPT"
INTENT_AMBIGUOUS   = "AMBIGUOUS"


class Spokesperson:
    """
    Entry point for every query. Handles auth, intent, and routing.
    """

    def __init__(self, users_file: str = "data/users.yaml"):
        self._users = self._load_users(users_file)

    # ── Authentication ────────────────────────────────────────────────────────

    def authenticate_user(self, user_id: str, credential: str) -> Optional[dict]:
        """
        Validate user credentials. Supports both:
        - New users: password_hash (PBKDF2)
        - Legacy dev accounts: plain token
        """
        user = self._users.get(user_id)
        if not user:
            logger.warning(f"Auth failed: unknown user '{user_id}'")
            return None
        if user.get("password_hash"):
            if not verify_password(credential, user["password_hash"]):
                logger.warning(f"Auth failed: wrong password for '{user_id}'")
                return None
        else:
            if user.get("token") != credential:
                logger.warning(f"Auth failed: invalid token for '{user_id}'")
                return None
        return user

    def load_permissions(self, user_id: str, role: str,
                         user_record: Optional[dict] = None) -> dict:
        """
        Read from Constitution which departments and columns this user may access.

        ``user_record`` — the raw entry from users.yaml.  When provided:
          - ``permitted_departments`` is taken directly from the record (already
            scoped by dept/division assignment at account-creation time).
          - For ``c_suite`` / ``division_head``, if no explicit dept list is
            stored we derive it from their division heading.
        """
        governance = get_governance()

        permitted_depts = None
        if user_record is not None:
            stored_depts = user_record.get("permitted_departments")
            if stored_depts:
                permitted_depts = stored_depts
            elif role in ("c_suite", "division_head"):
                # Derive from whichever division(s) they head
                my_divs = get_user_division_head_of(user_id)
                scoped: list[str] = []
                for div in my_divs:
                    scoped.extend(DIVISION_DEPTS.get(div, []))
                if scoped:
                    permitted_depts = list(dict.fromkeys(scoped))  # deduplicate, preserve order

        return governance.get_user_permissions(user_id, role, permitted_depts=permitted_depts)

    # ── Intent classification ─────────────────────────────────────────────────

    async def classify_intent(self, query: str, user_profile: dict, history_context: str = "") -> dict:
        """
        Classify query into TRIVIAL / SINGLE_DEPT / MULTI_DEPT / AMBIGUOUS.
        Uses a fast LLM call with a tight system prompt.
        Returns {intent: str, dept_hints: [str], reason: str}
        """
        llm = get_llm()
        permitted = user_profile.get("permitted_departments", [])
        system = (
            "You classify enterprise search queries for a company AI assistant. "
            "Return JSON with: "
            '{"intent": "TRIVIAL|GENERAL|SINGLE_DEPT|MULTI_DEPT|AMBIGUOUS", '
            '"dept_hints": ["list of relevant dept tags from: finance,legal,hr,sales,marketing,ops,it,procurement,rd,customer_success"], '
            '"reason": "one sentence explanation"}.\n'
            "Intent rules — pick the FIRST that matches:\n"
            "  TRIVIAL    = greetings, thanks, simple yes/no, follow-up chitchat (hi, thanks, what did you mean)\n"
            "  GENERAL    = questions answerable from world knowledge with NO company-specific data needed.\n"
            "               Examples: explain a concept, write code, draft an email template, translate text,\n"
            "               summarise an uploaded document the user attached, create a report/PPT outline,\n"
            "               math, general advice, coding help, writing help.\n"
            "  SINGLE_DEPT = needs THIS company's data from exactly one department database or document store.\n"
            "               Examples: 'What is our leave policy?', 'Show Q3 revenue', 'Who is the IT admin?'\n"
            "  MULTI_DEPT  = needs THIS company's data from multiple departments.\n"
            "  AMBIGUOUS   = genuinely unclear even with context — ask for clarification.\n"
            "IMPORTANT: If the question could be answered by any competent LLM without company data → GENERAL.\n"
            f"User has access to these departments: {permitted}. "
            "Do NOT include departments the user has no access to in dept_hints. "
            "Use conversation history for context on follow-up questions."
        )
        prompt = query
        if history_context:
            prompt = f"Conversation so far:\n{history_context}\n\nNew question: {query}"
        try:
            result = await asyncio.wait_for(
                llm.json_complete(prompt, system=system),
                timeout=15.0,
            )
            intent = result.get("intent", INTENT_SINGLE_DEPT)
            # Validate — LLM sometimes returns unexpected values
            valid_intents = {INTENT_TRIVIAL, INTENT_GENERAL, INTENT_SINGLE_DEPT, INTENT_MULTI_DEPT, INTENT_AMBIGUOUS}
            if intent not in valid_intents:
                result["intent"] = INTENT_SINGLE_DEPT
            return result
        except asyncio.TimeoutError:
            logger.warning("Intent classification timed out (>15s) — using keyword fallback")
            return _keyword_classify(query, permitted)
        except Exception as e:
            logger.warning(f"Intent classification failed: {e} — using keyword fallback")
            return _keyword_classify(query, permitted)

    # ── Query handling ────────────────────────────────────────────────────────

    async def handle_trivial(self, query: str, history_context: str = "") -> NLResult:
        """
        Answer trivial query directly without activating any dept agent.
        Token-saving path. Uses conversation history for follow-ups.
        """
        llm = get_llm()
        system = (
            "You are RAPID, a helpful enterprise AI assistant. "
            "Answer this question concisely and naturally. "
            "Use the conversation history for context on follow-up questions. "
            "If it requires company-specific data you don't have, say so politely."
        )
        prompt = query
        if history_context:
            prompt = f"Conversation so far:\n{history_context}\n\nUser: {query}"
        answer = await llm.complete(prompt, system=system)
        return NLResult(
            summary=answer,
            source="direct",
            confidence=0.90,
            dept_tag="spokesperson",
        )

    async def handle_general(
        self,
        query: str,
        history_context: str = "",
        attached_file_context: str = "",
    ) -> NLResult:
        """
        Answer a general question directly using the LLM — no dept routing, no RAG, no DB.
        This is the 'normal LLM' path: coding help, writing, explanations, uploaded-file Q&A, etc.
        Optionally incorporates an attached file's text as context.
        """
        llm = get_llm()
        system = (
            "You are RAPID, an intelligent AI assistant for a company. "
            "Answer the user's question fully and helpfully, exactly like a top-tier AI assistant would. "
            "You can write code, explain concepts, draft documents, summarise files, build report outlines, "
            "translate text, do math, give advice, and anything else a smart assistant can do. "
            "If the user attached a document, use its content to answer. "
            "If the question requires specific company data (like exact employee names, actual revenue figures, "
            "internal policies), let the user know they can ask and you will search the company database. "
            "Be concise, structured, and professional."
        )

        parts = []
        if history_context:
            parts.append(f"Conversation so far:\n{history_context}")
        if attached_file_context:
            parts.append(f"Attached document content:\n{attached_file_context}")
        parts.append(f"User: {query}")
        prompt = "\n\n".join(parts)

        answer = await llm.complete(prompt, system=system)
        return NLResult(
            summary=answer,
            source="general_llm",
            confidence=0.92,
            dept_tag="spokesperson",
        )

    async def clarify(self, query: str) -> NLResult:
        """Generate a clarifying question for ambiguous queries."""
        llm = get_llm()
        system = (
            "You are an enterprise assistant. The user's question is ambiguous. "
            "Ask ONE concise clarifying question to understand which department or data they need. "
            "Be specific and professional."
        )
        question = await llm.complete(query, system=system)
        return NLResult(
            summary=question,
            source="direct",
            confidence=1.0,
            dept_tag="spokesperson",
        )

    def route_to_planner(self, query: str, user_permissions: dict, intent_result: dict) -> dict:
        """Package query into a QueryObject for Master Planner."""
        return {
            "query_id": str(uuid.uuid4()),
            "query": query,
            "user_permissions": user_permissions,
            "intent": intent_result.get("intent"),
            "dept_hints": intent_result.get("dept_hints", []),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def reload_users(self):
        """Reload users.yaml into memory — called after any user store change."""
        self._users = self._load_users(self._users_file)
        logger.info(f"[spokesperson] User store reloaded ({len(self._users)} users)")

    def _load_users(self, users_file: str) -> dict:
        self._users_file = users_file
        p = Path(users_file)
        if not p.exists():
            logger.warning(f"Users file not found at {users_file} — using empty user store")
            return {}
        with open(p) as f:
            return yaml.safe_load(f) or {}


# ── Keyword fallback classifier ───────────────────────────────────────────────

_DEPT_KEYWORDS: dict[str, list[str]] = {
    "finance":          ["revenue", "budget", "invoice", "expense", "profit", "loss", "financial",
                         "cost", "payment", "salary", "payroll", "tax", "accounting", "cash"],
    "hr":               ["employee", "leave", "vacation", "holiday", "hiring", "onboard", "offboard",
                         "performance", "policy", "benefit", "headcount", "staff", "recruit"],
    "legal":            ["contract", "legal", "compliance", "regulation", "nda", "agreement",
                         "clause", "liability", "lawsuit", "ip", "patent", "gdpr"],
    "sales":            ["deal", "pipeline", "lead", "opportunity", "crm", "quota", "forecast",
                         "customer", "client", "account", "revenue", "close"],
    "marketing":        ["campaign", "brand", "ad", "advertisement", "seo", "content", "social",
                         "market", "promotion", "email marketing", "funnel", "lead generation"],
    "ops":              ["operation", "process", "workflow", "sla", "incident", "supply chain",
                         "logistics", "vendor", "procurement", "facility", "capacity"],
    "it":               ["server", "infrastructure", "network", "security", "software", "hardware",
                         "cloud", "devops", "ticket", "bug", "deployment", "access"],
    "procurement":      ["purchase", "supplier", "vendor", "rfp", "rfq", "order", "sourcing",
                         "contract", "spend", "catalog"],
    "rd":               ["research", "development", "prototype", "experiment", "innovation",
                         "patent", "roadmap", "sprint", "feature", "product"],
    "customer_success": ["customer", "support", "ticket", "churn", "nps", "satisfaction",
                         "onboarding", "renewal", "escalation", "feedback"],
}

_TRIVIAL_PATTERNS = ["hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "sure",
                     "yes", "no", "bye", "goodbye", "what did you mean", "can you clarify"]

_GENERAL_PATTERNS = ["explain", "what is", "how does", "define", "write", "draft", "translate",
                     "summarise", "summarize", "code", "script", "calculate", "convert",
                     "create a", "generate a", "help me with", "what are the steps"]


def _keyword_classify(query: str, permitted: list[str]) -> dict:
    """
    Fast keyword-based intent classifier — used when LLM classification times out.
    Scans for department keywords, trivial patterns, and general patterns.
    """
    q = query.lower()

    # Check trivial first
    for pat in _TRIVIAL_PATTERNS:
        if pat in q:
            return {"intent": INTENT_TRIVIAL, "dept_hints": [], "reason": "keyword: trivial pattern"}

    # Check general (world-knowledge) patterns
    for pat in _GENERAL_PATTERNS:
        if pat in q:
            return {"intent": INTENT_GENERAL, "dept_hints": [], "reason": "keyword: general pattern"}

    # Count dept keyword hits (only for permitted depts)
    hits: dict[str, int] = {}
    for dept, keywords in _DEPT_KEYWORDS.items():
        if permitted and dept not in permitted:
            continue
        score = sum(1 for kw in keywords if kw in q)
        if score > 0:
            hits[dept] = score

    if not hits:
        return {"intent": INTENT_SINGLE_DEPT, "dept_hints": permitted[:1] if permitted else [],
                "reason": "keyword: no dept match, defaulting to first permitted dept"}

    sorted_depts = sorted(hits, key=lambda d: hits[d], reverse=True)

    if len(sorted_depts) == 1 or hits[sorted_depts[0]] >= hits.get(sorted_depts[1], 0) * 2:
        return {
            "intent": INTENT_SINGLE_DEPT,
            "dept_hints": [sorted_depts[0]],
            "reason": f"keyword: strong match for '{sorted_depts[0]}'",
        }

    return {
        "intent": INTENT_MULTI_DEPT,
        "dept_hints": sorted_depts[:3],
        "reason": f"keyword: multi-dept match {sorted_depts[:3]}",
    }
