"""Security Agent — cybersecurity, access control, vulnerabilities, incidents."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class SecurityAgent(BaseEmployeeAgent):
    dept_tag        = "it"
    role_title      = "Security Analyst"
    specialization  = "Cybersecurity incidents, access control, vulnerability management, compliance"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["it/security/", "it/policies/"]
    bid_keywords    = [
        "security", "cybersecurity", "vulnerability", "access control",
        "breach", "incident", "threat", "patch", "pen test",
        "firewall", "mfa", "zero trust", "soc", "siem",
    ]
