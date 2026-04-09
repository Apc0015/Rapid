"""Operations Agent — processes, SOPs, KPIs, SLA compliance, logistics."""

from agents.base_dept_agent import BaseDeptAgent
from models.nl_result import NLResult


class OperationsAgent(BaseDeptAgent):
    dept_tag = "ops"
    doc_folders = ["ops/processes/", "ops/sops/", "ops/kpi_reports/"]
    permitted_tables = ["operations", "logistics", "kpis", "sla_records", "vendor_contracts"]

    bid_keywords = [
        "process", "sop", "procedure", "logistics", "kpi", "sla",
        "operations", "metric", "performance", "capacity", "supply chain",
        "vendor", "shipment", "delivery", "uptime", "availability",
    ]
    partial_keywords = ["ops", "operational", "efficiency", "workflow"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.ops.employees import SupplyChainAgent, ProcessAgent, FacilitiesAgent
        self._intra = IntraDeptOrchestrator("ops", [
            SupplyChainAgent(), ProcessAgent(), FacilitiesAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    async def resolve_sla_query(self, query: str, user_permissions: dict) -> NLResult:
        """
        SLA queries need both document (contract terms) and DB (actual performance).
        Clearly distinguishes 'contracted terms' from 'actual performance' in output.
        """
        from pipelines.rag_pipeline import run_rag_pipeline
        from pipelines.db_pipeline import run_db_pipeline
        from agents.governance_filter import get_governance
        from infrastructure.llm_client import get_llm
        import asyncio

        governance = get_governance()
        dept_permissions = governance.enrich_permissions_for_dept(user_permissions, self.dept_tag)

        rag_result, db_result = await asyncio.gather(
            run_rag_pipeline(query, self.dept_tag, dept_permissions),
            run_db_pipeline(query, self.dept_tag, dept_permissions),
        )

        # Merge with explicit label separation
        llm = get_llm()
        system = (
            "You are an Operations AI assistant. Combine the SLA information below. "
            "Clearly label: '**Contracted Terms** (from SLA document):' and "
            "'**Actual Performance** (from database):'. "
            "If there is a gap between contracted and actual, flag it explicitly."
        )
        prompt = (
            f"Question: {query}\n\n"
            f"SLA contract terms (from documents):\n{rag_result.summary}\n\n"
            f"Actual performance data (from database):\n{db_result.summary}"
        )
        merged = await llm.complete(prompt, system=system)

        conf = (rag_result.confidence + db_result.confidence) / 2
        return NLResult(
            summary=merged,
            source="merged",
            confidence=conf,
            citations=rag_result.citations,
            dept_tag=self.dept_tag,
        )
