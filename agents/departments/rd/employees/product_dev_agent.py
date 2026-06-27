"""Product Dev Agent — product development pipeline, feature delivery, roadmap."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class ProductDevAgent(BaseEmployeeAgent):
    dept_tag        = "rd"
    role_title      = "Product Developer"
    specialization  = "Product development pipeline, feature delivery, sprint velocity, roadmap"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["rd/product/", "rd/roadmap/"]
    bid_keywords    = [
        "product", "feature", "roadmap", "sprint", "velocity",
        "development", "product pipeline", "delivery", "backlog",
        "mvp", "release", "product milestone", "engineering",
    ]
