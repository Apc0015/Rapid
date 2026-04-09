"""Recruitment Agent — hiring, headcount planning, talent pipeline, open roles."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class RecruitmentAgent(BaseEmployeeAgent):
    dept_tag        = "hr"
    role_title      = "Recruitment Specialist"
    specialization  = "Hiring, headcount planning, talent pipeline, open roles, time-to-hire"
    skills          = ["headcount_report"]
    tools_available = ["query_database", "search_documents"]
    permitted_tables = ["employees", "org_structure"]
    doc_folders     = ["hr/onboarding/"]
    bid_keywords    = [
        "hiring", "recruitment", "headcount", "open role", "vacancy",
        "time to hire", "candidate", "offer", "onboarding", "new hire",
        "attrition", "turnover", "talent pipeline", "job opening",
    ]
