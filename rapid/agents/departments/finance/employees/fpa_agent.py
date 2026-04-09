"""FP&A Agent — financial planning, scenario modelling, strategic forecasting."""
from agents.base.base_employee_agent import BaseEmployeeAgent

class FPAAgent(BaseEmployeeAgent):
    dept_tag        = "finance"
    role_title      = "FP&A Analyst"
    specialization  = "Financial planning, scenario modelling, long-range forecasting, strategic analysis"
    skills          = ["forecast_summary"]
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = ["financials", "budget_allocations"]
    doc_folders     = ["finance/quarterly_reports/", "finance/budget_plans/"]
    bid_keywords    = [
        "forecast", "projection", "scenario", "long-range", "strategic plan",
        "3-year", "5-year", "financial model", "sensitivity analysis",
        "planning cycle", "annual plan", "fpa", "outlook",
    ]
