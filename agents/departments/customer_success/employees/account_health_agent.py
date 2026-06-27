"""Account Health Agent — NPS, CSAT, churn risk, health scores."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class AccountHealthAgent(BaseEmployeeAgent):
    dept_tag        = "customer_success"
    role_title      = "Account Health Manager"
    specialization  = "NPS, CSAT, churn risk scoring, customer health scores, retention"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = []
    doc_folders     = ["customer_success/playbooks/", "customer_success/reports/"]
    bid_keywords    = [
        "nps", "csat", "churn", "health score", "customer health",
        "at risk", "retention", "account health", "red account",
        "renewal risk", "customer satisfaction", "loyalty",
    ]
