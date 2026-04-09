"""Compliance Agent — regulatory compliance, GDPR, SOC2, audit readiness."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class ComplianceAgent(BaseEmployeeAgent):
    dept_tag        = "legal"
    role_title      = "Compliance Officer"
    specialization  = "Regulatory compliance, GDPR, SOC2, audit readiness, risk assessment"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["legal/compliance/", "legal/policies/"]
    bid_keywords    = [
        "compliance", "gdpr", "soc2", "regulation", "audit",
        "data protection", "privacy", "regulatory", "risk assessment",
        "iso", "certif", "legal risk", "breach", "incident",
    ]
