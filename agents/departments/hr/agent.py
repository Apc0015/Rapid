from __future__ import annotations
"""HR Agent — built first. Handles policies, benefits, leave, headcount, org structure."""

from agents.base.base_dept_agent import BaseDeptAgent
from models.nl_result import NLResult


class HRAgent(BaseDeptAgent):
    dept_tag = "hr"
    doc_folders = ["hr/policies/", "hr/handbooks/", "hr/onboarding/", "hr/training/"]
    permitted_tables = ["employees", "benefits_enrollment", "leave_records", "org_structure"]

    bid_keywords = [
        "policy", "policies", "benefit", "benefits", "leave", "pto", "vacation",
        "onboarding", "headcount", "org chart", "org structure", "employee",
        "handbook", "training", "parental", "maternity", "paternity",
        "reimbursement", "wfh", "remote", "salary", "pay", "compensation",
        "performance review", "promotion", "hiring",
    ]
    partial_keywords = ["team", "department", "staff", "people", "hr"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.hr.employees import (
            RecruitmentAgent, CompensationAgent, LearningDevAgent, EmployeeRelationsAgent,
        )
        self._intra = IntraDeptOrchestrator("hr", [
            RecruitmentAgent(), CompensationAgent(),
            LearningDevAgent(), EmployeeRelationsAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    def _get_caveats(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ("salary", "pay", "compensation", "wage")):
            return "Salary data will be provided as team/department averages only — individual salaries are not disclosed."
        return ""

    async def enforce_salary_aggregation(self, query: str, results: list) -> list:
        """
        Detect any attempt to retrieve individual salary data.
        Force aggregation — individual queries → team/department average.
        Logs the aggregation event. Never blocks the query entirely.
        """
        import logging
        logger = logging.getLogger(__name__)
        q = query.lower()
        if not any(w in q for w in ("salary", "pay", "compensation", "wage")):
            return results

        # Replace any individual salary values with an aggregation marker
        aggregated = []
        for row in results:
            new_row = dict(row)
            if "salary" in new_row:
                new_row["salary"] = "[TEAM_AVERAGE_ONLY]"
                logger.info("HR salary aggregation enforced — individual value replaced")
            aggregated.append(new_row)
        return aggregated
