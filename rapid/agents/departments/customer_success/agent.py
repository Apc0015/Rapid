from __future__ import annotations
"""Customer Success Agent — handles account health, NPS, support tickets, and renewals."""

from agents.base_dept_agent import BaseDeptAgent
from models.nl_result import NLResult


class CustomerSuccessAgent(BaseDeptAgent):
    dept_tag = "customer_success"
    doc_folders = ["customer_success/playbooks/", "customer_success/onboarding/", "customer_success/escalation_guides/"]
    permitted_tables = ["cs_accounts", "nps_scores", "support_tickets", "renewal_pipeline"]

    bid_keywords = [
        "customer success", "cs", "csm", "account health", "health score",
        "nps", "net promoter score", "churn", "at risk", "renewal", "renewals",
        "support ticket", "ticket", "tickets", "csat", "customer satisfaction",
        "onboarding", "qbr", "business review", "account review",
        "expansion", "upsell", "cross-sell", "arr", "retention", "churn risk",
        "customer feedback", "escalation", "account manager",
    ]
    partial_keywords = ["customer", "account", "client", "satisfaction", "retain"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.customer_success.employees import (
            AccountHealthAgent, OnboardingAgent, SupportEscalationAgent,
        )
        self._intra = IntraDeptOrchestrator("customer_success", [
            AccountHealthAgent(), OnboardingAgent(), SupportEscalationAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    def _get_caveats(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ("nps", "feedback", "verbatim", "comment")):
            return "Customer feedback verbatim responses are paraphrased — individual identifiers are anonymised per GDPR policy."
        if any(w in q for w in ("renewal", "arr", "revenue")):
            return "Renewal pipeline figures are indicative — final values subject to negotiation. Finance holds the authoritative ARR record."
        return ""
