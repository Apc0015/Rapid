"""Sales Ops Agent — pipeline analytics, quota attainment, win rates."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class SalesOpsAgent(BaseEmployeeAgent):
    dept_tag        = "sales"
    role_title      = "Sales Operations Analyst"
    specialization  = "Pipeline analytics, quota attainment, win/loss rates, sales velocity"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = ["deals", "sales_pipeline", "customers"]
    doc_folders     = ["sales/playbook/", "sales/territory_plans/"]
    bid_keywords    = [
        "pipeline", "quota", "attainment", "win rate", "loss rate",
        "sales velocity", "average deal size", "sales cycle",
        "conversion", "funnel", "stage", "territory",
    ]
