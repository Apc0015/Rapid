"""Sales Agent — deals, pipeline, CRM, customer history, win/loss analysis."""

from agents.base.base_dept_agent import BaseDeptAgent
from models.nl_result import NLResult


class SalesAgent(BaseDeptAgent):
    dept_tag = "sales"
    doc_folders = ["sales/playbook/", "sales/case_studies/", "sales/territory_plans/"]
    permitted_tables = ["customers", "deals", "sales_pipeline", "customer_interactions"]

    bid_keywords = [
        "deal", "pipeline", "customer", "revenue", "quota", "win rate",
        "crm", "sales", "close", "opportunity", "prospect", "account",
        "forecast", "attainment", "conversion", "churn", "arr", "mrr",
    ]
    partial_keywords = ["sale", "client", "lead", "contract value"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.sales.employees import (
            AccountExecutiveAgent, SalesOpsAgent, RevOpsAgent, PartnershipAgent,
        )
        self._intra = IntraDeptOrchestrator("sales", [
            AccountExecutiveAgent(), SalesOpsAgent(),
            RevOpsAgent(), PartnershipAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    async def resolve_crm_query(self, query: str, user_permissions: dict) -> NLResult:
        """
        Handle queries that mix document (case studies) and CRM data.
        Routes both pipelines and merges the results.
        """
        from pipelines.rag_pipeline import run_rag_pipeline
        from pipelines.db_pipeline import run_db_pipeline
        from agents.system.governance_filter import get_governance
        import asyncio

        governance = get_governance()
        dept_permissions = governance.enrich_permissions_for_dept(user_permissions, self.dept_tag)

        rag_result, db_result = await asyncio.gather(
            run_rag_pipeline(query, self.dept_tag, dept_permissions),
            run_db_pipeline(query, self.dept_tag, dept_permissions),
        )
        return await self.merge_sources(rag_result, db_result, query)
