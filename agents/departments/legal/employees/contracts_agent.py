"""Contracts Agent — contract review, NDAs, MSAs, SLAs, renewals."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class ContractsAgent(BaseEmployeeAgent):
    dept_tag        = "legal"
    role_title      = "Contracts Specialist"
    specialization  = "Contract review, NDAs, MSAs, SLAs, contract renewals and expiry tracking"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["legal/contracts/", "legal/templates/"]
    bid_keywords    = [
        "contract", "nda", "msa", "sla", "agreement", "clause",
        "renewal", "expiry", "termination", "vendor contract",
        "service agreement", "master agreement", "contract review",
    ]
