"""Compensation Agent — payroll, benefits, salary bands (aggregated only)."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class CompensationAgent(BaseEmployeeAgent):
    dept_tag        = "hr"
    role_title      = "Compensation Analyst"
    specialization  = "Payroll totals, benefits enrollment, salary band benchmarking (team averages only)"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = ["employees", "benefits_enrollment"]
    doc_folders     = ["hr/handbooks/", "hr/policies/"]
    bid_keywords    = [
        "payroll", "salary", "compensation", "benefits", "pay",
        "salary band", "pay equity", "total comp", "bonus",
        "benefits enrollment", "health insurance", "pension",
    ]
