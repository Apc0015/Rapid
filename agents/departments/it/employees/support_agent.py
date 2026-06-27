"""Support Agent — helpdesk tickets, resolution times, SLAs, user issues."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class SupportAgent(BaseEmployeeAgent):
    dept_tag        = "it"
    role_title      = "IT Support Specialist"
    specialization  = "Helpdesk tickets, resolution times, SLA adherence, user issue tracking"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = []
    doc_folders     = ["it/runbooks/", "it/policies/"]
    bid_keywords    = [
        "helpdesk", "ticket", "support", "resolution", "user issue",
        "it support", "sla", "first response", "mttr",
        "open tickets", "backlog", "priority", "escalation",
    ]
