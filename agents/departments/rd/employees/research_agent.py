"""Research Agent — research projects, publications, academic partnerships."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class ResearchAgent(BaseEmployeeAgent):
    dept_tag        = "rd"
    role_title      = "Research Scientist"
    specialization  = "Research projects, publications, academic partnerships, grant tracking"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["rd/research/", "rd/publications/"]
    bid_keywords    = [
        "research", "study", "publication", "paper", "academic",
        "grant", "experiment", "hypothesis", "finding", "literature",
        "peer review", "citation", "research project",
    ]
