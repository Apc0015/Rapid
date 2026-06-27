"""Controller — GL, AP/AR, invoice reconciliation, month-end close."""
from agents.base.base_employee_agent import BaseEmployeeAgent

class ControllerAgent(BaseEmployeeAgent):
    dept_tag        = "finance"
    role_title      = "Controller"
    specialization  = "General ledger, accounts payable/receivable, invoice reconciliation, month-end close"
    skills          = []
    tools_available = ["query_database", "search_documents"]
    permitted_tables = ["invoices", "expense_claims", "financials"]
    doc_folders     = ["finance/expense_reports/"]
    bid_keywords    = [
        "invoice", "accounts payable", "accounts receivable", "ap", "ar",
        "reconciliation", "month-end", "journal entry", "ledger",
        "expense claim", "reimbursement", "overdue", "outstanding",
    ]
