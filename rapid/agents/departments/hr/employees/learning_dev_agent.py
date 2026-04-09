"""L&D Agent — training programs, skills development, certifications."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class LearningDevAgent(BaseEmployeeAgent):
    dept_tag        = "hr"
    role_title      = "L&D Specialist"
    specialization  = "Training programs, skills development, learning pathways, certifications"
    skills          = []
    tools_available = ["query_database", "search_documents"]
    permitted_tables = ["employees"]
    doc_folders     = ["hr/training/", "hr/handbooks/"]
    bid_keywords    = [
        "training", "learning", "development", "l&d", "certification",
        "course", "upskilling", "reskilling", "leadership program",
        "mentoring", "coaching", "skill gap", "learning pathway",
    ]
