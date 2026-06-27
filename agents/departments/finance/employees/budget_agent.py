"""Budget Agent — budget planning, cost centre management, allocation."""
from agents.base.base_employee_agent import BaseEmployeeAgent

class BudgetAgent(BaseEmployeeAgent):
    dept_tag        = "finance"
    role_title      = "Budget Manager"
    specialization  = "Budget planning, cost centre management, spend allocation, reforecast"
    skills          = ["budget_variance", "cost_centre_analysis"]
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = ["budget_allocations", "financials"]
    doc_folders     = ["finance/budget_plans/"]
    bid_keywords    = [
        "budget", "cost centre", "allocation", "reforecast", "headroom",
        "overspend", "underspend", "approved budget", "remaining budget",
        "capex", "opex", "spend limit",
    ]
