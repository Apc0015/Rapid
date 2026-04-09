"""Process Agent — operational efficiency, SLAs, KPIs, process improvement."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class ProcessAgent(BaseEmployeeAgent):
    dept_tag        = "ops"
    role_title      = "Process Improvement Analyst"
    specialization  = "Operational efficiency, SLA tracking, KPI monitoring, process improvement"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = []
    doc_folders     = ["ops/processes/", "ops/reports/"]
    bid_keywords    = [
        "sla", "kpi", "process", "efficiency", "operational",
        "throughput", "cycle time", "bottleneck", "incident",
        "escalation", "resolution time", "process improvement", "lean",
    ]
