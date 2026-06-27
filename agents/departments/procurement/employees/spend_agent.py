"""Spend Agent — spend analytics, cost optimisation, category management."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class SpendAgent(BaseEmployeeAgent):
    dept_tag        = "procurement"
    role_title      = "Spend Analyst"
    specialization  = "Spend analytics, cost optimisation, category management, savings tracking"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = []
    doc_folders     = ["procurement/reports/"]
    bid_keywords    = [
        "spend", "spend analysis", "cost saving", "category",
        "managed spend", "tail spend", "maverick spend",
        "savings", "cost reduction", "procurement spend",
    ]
