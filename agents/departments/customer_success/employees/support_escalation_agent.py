"""Support Escalation Agent — ticket escalations, SLA management, critical issues."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class SupportEscalationAgent(BaseEmployeeAgent):
    dept_tag        = "customer_success"
    role_title      = "Support Escalation Manager"
    specialization  = "Ticket escalations, SLA management, critical customer issues, incident response"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = []
    doc_folders     = ["customer_success/playbooks/"]
    bid_keywords    = [
        "escalation", "critical issue", "sla breach", "p1", "p2",
        "support ticket", "open issue", "resolution", "incident",
        "customer complaint", "executive escalation", "downtime impact",
    ]
