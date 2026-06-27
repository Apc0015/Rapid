"""RevOps Agent — ARR, MRR, revenue operations metrics, forecasting."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class RevOpsAgent(BaseEmployeeAgent):
    dept_tag        = "sales"
    role_title      = "Revenue Operations Analyst"
    specialization  = "ARR, MRR, revenue forecasting, cohort analysis, revenue metrics"
    skills          = []
    tools_available = ["query_database", "calculate"]
    permitted_tables = ["customers", "deals", "sales_pipeline"]
    doc_folders     = []
    bid_keywords    = [
        "arr", "mrr", "revenue", "recurring revenue", "forecast",
        "rev ops", "cohort", "expansion revenue", "contraction",
        "net revenue retention", "nrr", "gross revenue retention",
    ]
