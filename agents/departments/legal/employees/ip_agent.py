"""IP Agent — intellectual property, patents, trademarks, licensing."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class IPAgent(BaseEmployeeAgent):
    dept_tag        = "legal"
    role_title      = "IP Counsel"
    specialization  = "Intellectual property, patents, trademarks, licensing agreements"
    skills          = []
    tools_available = ["search_documents"]
    permitted_tables = []
    doc_folders     = ["legal/ip/", "legal/contracts/"]
    bid_keywords    = [
        "patent", "trademark", "copyright", "ip", "intellectual property",
        "license", "licensing", "trade secret", "invention", "filing",
    ]
