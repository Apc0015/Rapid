"""Innovation Agent — innovation pipeline, patent filings, competitive analysis."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class InnovationAgent(BaseEmployeeAgent):
    dept_tag        = "rd"
    role_title      = "Innovation Manager"
    specialization  = "Innovation pipeline, patent filings, competitive analysis, technology watch"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["rd/innovation/", "rd/competitive/"]
    bid_keywords    = [
        "innovation", "patent", "ip", "competitive analysis",
        "technology watch", "emerging technology", "disruptive",
        "poc", "proof of concept", "prototype", "ideation",
    ]
