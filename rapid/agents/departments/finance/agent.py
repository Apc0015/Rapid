"""Finance Agent — revenue, budgets, costs, invoices, P&L, cash flow."""

from agents.base_dept_agent import BaseDeptAgent


class FinanceAgent(BaseDeptAgent):
    dept_tag = "finance"
    doc_folders = ["finance/quarterly_reports/", "finance/budget_plans/", "finance/expense_reports/"]
    permitted_tables = ["financials", "orders", "invoices", "budget_allocations", "expense_claims"]

    bid_keywords = [
        "revenue", "budget", "cost", "invoice", "expense", "profit", "loss",
        "p&l", "cash flow", "margin", "quarterly", "annual", "financial",
        "spend", "spending", "forecast", "ytd", "q1", "q2", "q3", "q4",
        "income", "ebitda", "gross", "net", "operating",
    ]
    partial_keywords = ["money", "finance", "dollar", "payment", "bill"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.finance.employees import (
            FinancialAnalystAgent, ControllerAgent, BudgetAgent, TreasuryAgent, FPAAgent,
        )
        self._intra = IntraDeptOrchestrator("finance", [
            FinancialAnalystAgent(), ControllerAgent(),
            BudgetAgent(), TreasuryAgent(), FPAAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    def _get_caveats(self, query: str) -> str:
        q = query.lower()
        if "margin" in q:
            return "Margin data visibility depends on your role — some details may be restricted."
        return ""

    async def rewrite_for_finance(self, query: str) -> str:
        """Rewrite vague queries into finance-specific form."""
        from infrastructure.llm_client import get_llm
        llm = get_llm()
        system = (
            "You rewrite vague business queries into precise financial questions. "
            "Example: 'How are we doing this quarter?' → "
            "'What is Q3 2026 revenue vs Q3 2025 revenue and current YTD budget status?' "
            "Return only the rewritten question, nothing else."
        )
        return await llm.complete(query, system=system)
