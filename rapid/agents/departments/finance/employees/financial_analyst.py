"""Financial Analyst — P&L, variance analysis, trend detection, YoY comparison."""
from agents.base.base_employee_agent import BaseEmployeeAgent

class FinancialAnalystAgent(BaseEmployeeAgent):
    dept_tag        = "finance"
    role_title      = "Financial Analyst"
    specialization  = "P&L analysis, budget variance, trend detection, YoY comparison"
    skills          = ["pnl_report", "budget_variance", "forecast_summary"]
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = ["financials", "budget_allocations"]
    doc_folders     = ["finance/quarterly_reports/", "finance/budget_plans/"]
    bid_keywords    = [
        "p&l", "profit", "loss", "variance", "ytd", "ebitda",
        "revenue trend", "quarterly performance", "annual comparison",
        "budget vs actual", "income statement", "gross margin",
    ]
