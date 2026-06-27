"""Supply Chain Agent — vendor management, logistics, procurement ops, inventory."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class SupplyChainAgent(BaseEmployeeAgent):
    dept_tag        = "ops"
    role_title      = "Supply Chain Manager"
    specialization  = "Vendor management, logistics, procurement operations, inventory tracking"
    skills          = []
    tools_available = ["query_database", "search_documents"]
    permitted_tables = []
    doc_folders     = ["ops/vendors/", "ops/logistics/"]
    bid_keywords    = [
        "supply chain", "vendor", "logistics", "inventory", "stock",
        "lead time", "delivery", "supplier", "procurement ops",
        "warehouse", "fulfilment", "shipping", "distribution",
    ]
