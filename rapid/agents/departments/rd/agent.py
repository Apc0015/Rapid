from __future__ import annotations
"""R&D Agent — handles research projects, experiments, IP registry, and research budgets."""

from agents.base_dept_agent import BaseDeptAgent
from models.nl_result import NLResult


class RDAgent(BaseDeptAgent):
    dept_tag = "rd"
    doc_folders = ["rd/project_briefs/", "rd/research_reports/", "rd/ip_documentation/"]
    permitted_tables = ["rd_projects", "experiments", "ip_registry", "research_budgets"]

    bid_keywords = [
        "research", "r&d", "experiment", "experiments", "prototype", "innovation",
        "ip", "intellectual property", "patent", "copyright", "invention",
        "project", "projects", "hypothesis", "discovery", "lab", "pilot",
        "proof of concept", "poc", "feasibility", "study", "trial",
        "research budget", "innovation budget", "rd spend", "rd project",
    ]
    partial_keywords = ["new product", "development", "explore", "investigate", "test"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.rd.employees import ResearchAgent, ProductDevAgent, InnovationAgent
        self._intra = IntraDeptOrchestrator("rd", [
            ResearchAgent(), ProductDevAgent(), InnovationAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    def _get_caveats(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ("patent", "ip", "intellectual property", "invention")):
            return "IP and patent details are provided at summary level only — full filings are accessible to Legal and R&D leads only."
        return ""
