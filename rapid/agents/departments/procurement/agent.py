from __future__ import annotations
"""Procurement Agent — handles supplier management, purchase orders, RFQs, vendor evaluations."""

from agents.base_dept_agent import BaseDeptAgent
from models.nl_result import NLResult


class ProcurementAgent(BaseDeptAgent):
    dept_tag = "procurement"
    doc_folders = ["procurement/policies/", "procurement/supplier_guides/", "procurement/rfq_templates/"]
    permitted_tables = ["purchase_orders", "suppliers", "rfq_records", "vendor_evaluations"]

    bid_keywords = [
        "supplier", "suppliers", "vendor", "vendors", "purchase order", "po",
        "rfq", "request for quotation", "procurement", "sourcing", "buying",
        "spend", "contract award", "tender", "bid", "quote", "quotation",
        "preferred supplier", "approved vendor", "supply chain",
        "purchase", "buying policy", "procurement policy", "supplier rating",
        "vendor evaluation", "due diligence", "onboard supplier",
    ]
    partial_keywords = ["order", "supply", "source", "spend", "cost saving"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.procurement.employees import VendorAgent, ContractingAgent, SpendAgent
        self._intra = IntraDeptOrchestrator("procurement", [
            VendorAgent(), ContractingAgent(), SpendAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    def _get_caveats(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ("contract", "pricing", "terms", "rate")):
            return "Vendor pricing terms and contract details are confidential — only summary-level data is returned."
        return ""
