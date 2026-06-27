"""Vendor Agent — vendor performance, sourcing, supplier management."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class VendorAgent(BaseEmployeeAgent):
    dept_tag        = "procurement"
    role_title      = "Vendor Manager"
    specialization  = "Vendor performance, sourcing strategy, supplier relationships, RFP management"
    skills          = []
    tools_available = ["query_database", "search_documents"]
    permitted_tables = []
    doc_folders     = ["procurement/vendors/", "procurement/rfps/"]
    bid_keywords    = [
        "vendor", "supplier", "sourcing", "rfp", "rfq",
        "vendor performance", "supplier scorecard", "preferred vendor",
        "vendor risk", "due diligence", "shortlisting",
    ]
