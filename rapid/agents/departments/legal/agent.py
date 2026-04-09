"""Legal Agent — compliance, GDPR, contracts, regulatory risk, litigation."""

from agents.base_dept_agent import BaseDeptAgent
from models.nl_result import NLResult


class LegalAgent(BaseDeptAgent):
    dept_tag = "legal"
    doc_folders = ["legal/compliance/", "legal/contracts/", "legal/regulations/", "legal/gdpr_policies/"]
    permitted_tables = ["cases", "contracts_db", "compliance_records", "regulatory_filings"]

    bid_keywords = [
        "gdpr", "compliance", "contract", "regulatory", "regulation", "legal",
        "litigation", "lawsuit", "risk", "policy", "law", "statute",
        "data protection", "privacy", "breach", "liability", "clause",
        "agreement", "terms", "audit", "fine", "penalty",
    ]
    partial_keywords = ["legal", "rule", "requirement", "obligation"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.legal.employees import (
            ContractsAgent, ComplianceAgent, IPAgent,
        )
        self._intra = IntraDeptOrchestrator("legal", [
            ContractsAgent(), ComplianceAgent(), IPAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    def _get_caveats(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ("litigation", "lawsuit", "settlement", "case")):
            return "Active litigation details are protected by attorney-client privilege and may not be fully disclosed."
        return ""

    async def apply_privilege_filter(self, results: NLResult) -> NLResult:
        """
        Extra governance layer specific to Legal.
        Checks for attorney-client privileged content markers.
        """
        privilege_markers = ["litigation_details", "settlement_amount", "opposing_counsel"]
        if any(m in results.summary.lower() for m in privilege_markers):
            results.summary = (
                results.summary + "\n\n⚠️ Note: Some details are protected by attorney-client privilege. "
                "Contact the Legal department directly for full information."
            )
        return results
