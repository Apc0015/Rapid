"""Brand Agent — brand health, NPS, PR, brand guidelines."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class BrandAgent(BaseEmployeeAgent):
    dept_tag        = "marketing"
    role_title      = "Brand Manager"
    specialization  = "Brand health metrics, NPS, PR coverage, brand guidelines, reputation"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["marketing/brand/", "marketing/strategy/"]
    bid_keywords    = [
        "brand", "nps", "brand awareness", "sentiment", "pr",
        "public relations", "brand health", "brand guidelines",
        "reputation", "press", "media coverage", "brand equity",
    ]
