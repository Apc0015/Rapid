from __future__ import annotations
"""
QueryRewriter — rewrites each sub-query for the specific department that won the bid.

Runs AFTER select_winners, BEFORE dispatch_parallel.
For each (sub_query, dept_agent) pair it produces a department-aware rewrite that:
  - Uses the dept's domain vocabulary
  - References the exact tables and document folders available to that dept
  - Strips cross-department noise
  - Adds implicit retrieval hints so RAG + DB pipelines surface better results

The LLM never sees raw data — it only rewrites the *question*, not the answer.
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Dict, Optional

from infrastructure.llm_client import get_llm

if TYPE_CHECKING:
    from agents.base.base_dept_agent import BaseDeptAgent

logger = logging.getLogger(__name__)

# Dept-level context hints injected into the rewrite prompt.
# Keeps the prompt grounded without leaking data.
_DEPT_CONTEXT: Dict[str, str] = {
    "hr": (
        "HR handles employee records, leave & PTO, benefits enrolment, compensation, "
        "performance reviews, onboarding, org structure, and workplace policies."
    ),
    "finance": (
        "Finance handles budgets, actuals, forecasts, P&L, cost centres, invoices, "
        "accounts payable/receivable, payroll cost aggregates, and financial reports."
    ),
    "legal": (
        "Legal handles contracts, NDAs, compliance obligations, regulatory filings, "
        "IP registrations, litigation records, and policy review."
    ),
    "sales": (
        "Sales handles pipeline opportunities, CRM records, deal stages, quotas, "
        "revenue targets, win/loss analysis, and customer accounts."
    ),
    "marketing": (
        "Marketing handles campaigns, content assets, lead generation metrics, "
        "brand guidelines, event materials, and market research."
    ),
    "ops": (
        "Operations handles process workflows, project timelines, vendor SLAs, "
        "facility management, supply chain, and operational KPIs."
    ),
    "it": (
        "IT handles infrastructure, system incidents, SLAs, asset inventory, "
        "security policies, access management, and software licences."
    ),
    "procurement": (
        "Procurement handles purchase orders, approved vendor lists, RFPs, "
        "contract renewals, spend analysis, and supplier evaluations."
    ),
    "rd": (
        "R&D handles research projects, patents, prototypes, experiment logs, "
        "technical specifications, and innovation pipelines."
    ),
    "customer_success": (
        "Customer Success handles support tickets, NPS scores, churn risk, "
        "onboarding health, renewal status, and customer feedback."
    ),
}


# SQL detection — if a sub-query looks like SQL it should not be rewritten,
# it should be returned as-is (the DB pipeline will handle it).
_SQL_PATTERN = re.compile(
    r"^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER|DROP)\b",
    re.IGNORECASE,
)
_SQL_KEYWORDS_DENSITY = re.compile(
    r"\b(SELECT|FROM|WHERE|JOIN|GROUP BY|ORDER BY|HAVING|LIMIT|UNION|INSERT|UPDATE|DELETE)\b",
    re.IGNORECASE,
)


def _looks_like_sql(text: str) -> bool:
    """Return True if the text appears to be a raw SQL query rather than NL."""
    if _SQL_PATTERN.match(text):
        return True
    keyword_hits = len(_SQL_KEYWORDS_DENSITY.findall(text))
    # 3+ SQL keywords in a short text → treat as SQL
    return keyword_hits >= 3


class QueryRewriter:
    """
    Rewrites sub-queries to be department-specific before agent dispatch.
    All rewrites run in parallel via asyncio.gather.
    SQL-like sub-queries are returned unchanged so the DB pipeline can handle them directly.
    """

    async def rewrite(
        self,
        query: str,
        dept_tag: str,
        agent: Optional["BaseDeptAgent"] = None,
    ) -> str:
        """
        Rewrite `query` for `dept_tag`.
        Falls back to the original query on any error so the pipeline never stalls.
        """
        logger.info(f"QueryRewriter: rewriting query='{query[:60]}'")

        # Guard: pass SQL straight through — do not ask the LLM to rewrite SQL
        if _looks_like_sql(query):
            logger.info(f"[QueryRewriter] {dept_tag}: SQL detected — skipping rewrite")
            return query

        llm = get_llm()
        dept_context = _DEPT_CONTEXT.get(dept_tag, f"{dept_tag.upper()} department data.")

        tables = getattr(agent, "permitted_tables", []) if agent else []
        folders = getattr(agent, "doc_folders", []) if agent else []

        resources = []
        if tables:
            resources.append(f"Database tables: {', '.join(tables)}")
        if folders:
            resources.append(f"Document folders: {', '.join(folders)}")
        resources_text = "\n".join(resources) if resources else "No specific resources listed."

        system = (
            f"You are a query optimisation assistant for the {dept_tag.upper()} department.\n"
            f"Department scope: {dept_context}\n"
            f"Available resources:\n{resources_text}\n\n"
            "Rewrite the user's question so it is maximally specific to this department. "
            "Keep the original intent intact. "
            "Use precise terminology that will match documents and database columns in this department. "
            "Add implicit retrieval hints (e.g. relevant table names or document types) where helpful. "
            "Remove references to other departments. "
            "Output ONLY the rewritten question — no explanation, no preamble."
        )

        try:
            rewritten = await llm.complete(query, system=system)
            rewritten = rewritten.strip()
            if not rewritten:
                return query
            logger.info(f"QueryRewriter: '{query[:40]}' → '{rewritten[:40]}'")
            return rewritten
        except Exception as exc:
            logger.warning(
                f"QueryRewriter: rewrite failed for query='{query[:60]}' — using original. Error: {exc!r}"
            )
            return query

    async def rewrite_batch(
        self,
        sub_queries: list,
        assignments: Dict[str, Optional[str]],
        registry: dict,
    ) -> Dict[str, str]:
        """
        Rewrite all assigned sub-queries concurrently.

        Args:
            sub_queries: list of {dept, sub_query} dicts from decompose_query
            assignments: {sub_query_text: winning_agent_id or None}
            registry:    {agent_id: BaseDeptAgent instance}

        Returns:
            {original_sub_query: rewritten_query}
            Unassigned queries map to themselves (pass-through).
        """
        tasks: Dict[str, asyncio.Task] = {}
        loop = asyncio.get_event_loop()

        for sq in sub_queries:
            key = sq["sub_query"]
            agent_id = assignments.get(key)
            if agent_id is None:
                continue
            agent = registry.get(agent_id)
            tasks[key] = asyncio.ensure_future(
                self.rewrite(key, agent_id, agent)
            )

        rewrites: Dict[str, str] = {}

        if tasks:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for original, result in zip(tasks.keys(), results):
                if isinstance(result, Exception):
                    logger.warning(f"[QueryRewriter] gather error for '{original[:50]}': {result}")
                    rewrites[original] = original
                else:
                    rewrites[original] = result

        # Pass-through for unassigned sub-queries
        for sq in sub_queries:
            key = sq["sub_query"]
            if key not in rewrites:
                rewrites[key] = key

        return rewrites
