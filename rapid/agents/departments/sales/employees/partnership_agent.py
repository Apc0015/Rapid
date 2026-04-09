"""Partnership Agent — channel partners, alliances, co-sell programs."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class PartnershipAgent(BaseEmployeeAgent):
    dept_tag        = "sales"
    role_title      = "Partnership Manager"
    specialization  = "Channel partners, strategic alliances, co-sell programs, partner revenue"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = ["customers", "deals"]
    doc_folders     = ["sales/playbook/"]
    bid_keywords    = [
        "partner", "partnership", "channel", "alliance", "reseller",
        "co-sell", "referral", "partner revenue", "ecosystem",
    ]
