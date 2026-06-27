"""Employee Relations Agent — performance reviews, policies, disciplinary, engagement."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class EmployeeRelationsAgent(BaseEmployeeAgent):
    dept_tag        = "hr"
    role_title      = "Employee Relations Advisor"
    specialization  = "Performance reviews, HR policies, employee engagement, disciplinary processes"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = ["employees", "leave_records"]
    doc_folders     = ["hr/policies/", "hr/handbooks/"]
    bid_keywords    = [
        "performance review", "pip", "disciplinary", "grievance",
        "employee engagement", "hr policy", "leave", "absence",
        "remote work", "wfh", "flexible working", "parental leave",
        "maternity", "paternity", "code of conduct",
    ]
