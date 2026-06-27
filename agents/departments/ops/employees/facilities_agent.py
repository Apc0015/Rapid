"""Facilities Agent — office management, asset tracking, workspace planning."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class FacilitiesAgent(BaseEmployeeAgent):
    dept_tag        = "ops"
    role_title      = "Facilities Manager"
    specialization  = "Office management, asset tracking, workspace planning, facilities costs"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["ops/facilities/"]
    bid_keywords    = [
        "office", "facilities", "workspace", "asset", "equipment",
        "desk", "floor plan", "building", "maintenance", "utilities",
        "real estate", "lease", "occupancy",
    ]
