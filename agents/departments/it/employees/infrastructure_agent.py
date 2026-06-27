"""Infrastructure Agent — servers, cloud costs, networking, uptime, capacity."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class InfrastructureAgent(BaseEmployeeAgent):
    dept_tag        = "it"
    role_title      = "Infrastructure Engineer"
    specialization  = "Servers, cloud infrastructure, networking, uptime, capacity planning"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = []
    doc_folders     = ["it/infrastructure/", "it/runbooks/"]
    bid_keywords    = [
        "server", "cloud", "infrastructure", "uptime", "availability",
        "capacity", "network", "bandwidth", "latency", "hosting",
        "aws", "azure", "gcp", "compute", "storage",
    ]
