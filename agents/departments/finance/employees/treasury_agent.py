"""Treasury Agent — cash flow, liquidity, FX exposure, working capital."""
from agents.base.base_employee_agent import BaseEmployeeAgent

class TreasuryAgent(BaseEmployeeAgent):
    dept_tag        = "finance"
    role_title      = "Treasury Analyst"
    specialization  = "Cash flow management, liquidity position, FX exposure, working capital"
    skills          = ["cash_flow_report"]
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = ["financials"]
    doc_folders     = ["finance/quarterly_reports/"]
    bid_keywords    = [
        "cash flow", "liquidity", "working capital", "fx", "foreign exchange",
        "cash position", "cash runway", "treasury", "bank balance",
        "days sales outstanding", "dso", "payment terms",
    ]
