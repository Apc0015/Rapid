"""Account Executive Agent — deal tracking, customer accounts, CRM data."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class AccountExecutiveAgent(BaseEmployeeAgent):
    dept_tag        = "sales"
    role_title      = "Account Executive"
    specialization  = "Deal tracking, customer accounts, CRM data, opportunity management"
    skills          = []
    tools_available = ["query_database", "search_documents"]
    permitted_tables = ["customers", "deals", "customer_interactions"]
    doc_folders     = ["sales/case_studies/"]
    bid_keywords    = [
        "deal", "opportunity", "customer", "account", "close",
        "prospect", "crm", "pipeline stage", "contract value",
        "win", "loss", "churn", "renewal", "upsell", "cross-sell",
    ]
