"""Contracting Agent — procurement contracts, T&Cs, renewals, SLAs."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class ContractingAgent(BaseEmployeeAgent):
    dept_tag        = "procurement"
    role_title      = "Procurement Contracts Specialist"
    specialization  = "Procurement contracts, terms and conditions, renewals, SLA management"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["procurement/contracts/", "procurement/vendors/"]
    bid_keywords    = [
        "procurement contract", "purchase order", "po", "terms",
        "renewal", "contract expiry", "sla", "penalty clause",
        "payment terms", "warranty", "indemnity",
    ]
