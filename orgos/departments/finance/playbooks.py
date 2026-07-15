"""
orgos/departments/finance/playbooks.py — what the Finance department knows
how to do.

Never moves money itself (constitution carried over from the original plan):
handlers reconcile, validate, and schedule/allocate for a real payment
system to execute. Expense and budget approval gates are dynamically
classified by amount — cheap and reversible runs unattended, anything
consequential needs sign-off.
"""

from __future__ import annotations

from orgos.models import Playbook, StepSpec, Autonomy

A = Autonomy.A_AUTO


INVOICE_RECONCILIATION = Playbook(
    key="invoice_reconciliation",
    department="finance",
    title="Invoice Reconciliation",
    description="A vendor invoice arrives; matched against its PO and folded "
                "into the reconciliation report before month-end.",
    required_inputs=[
        {"name": "invoice_amount", "label": "Invoice amount (USD)", "type": "number", "required": True},
        {"name": "po_reference", "label": "PO reference (if any)", "type": "text", "required": False},
    ],
    steps=[
        StepSpec("match_to_po", "Matched against PO", "finance", A,
                 "match_to_po", "v_invoice_checked"),
        StepSpec("prepare_report", "Reconciliation report prepared", "finance", A,
                 "prepare_reconciliation_report", "v_reconciliation_ready"),
    ],
)


EXPENSE_CLAIM = Playbook(
    key="expense_claim",
    department="finance",
    title="Expense Claim",
    description="An employee submits an expense. Small claims are validated "
                "and reimbursed automatically; larger ones need your sign-off.",
    required_inputs=[
        {"name": "amount", "label": "Amount (USD)", "type": "number", "required": True},
        {"name": "category", "label": "Category", "type": "text", "required": False},
    ],
    steps=[
        StepSpec("validate_claim", "Claim validated against policy", "finance", A,
                 "validate_expense_claim", "v_expense_validated"),
        StepSpec("approve_reimbursement", "Reimbursement approved & scheduled", "finance", A,
                 "approve_and_schedule_reimbursement", "v_reimbursement_scheduled",
                 classify="classify_expense_amount"),
    ],
)


BUDGET_REQUEST = Playbook(
    key="budget_request",
    department="finance",
    title="Budget Request",
    description="A department asks to spend against budget. Small requests "
                "clear automatically; larger ones need your sign-off.",
    required_inputs=[
        {"name": "department", "label": "Requesting department", "type": "text", "required": True},
        {"name": "purpose", "label": "Purpose", "type": "text", "required": True},
        {"name": "amount", "label": "Amount (USD)", "type": "number", "required": True},
    ],
    steps=[
        StepSpec("check_availability", "Budget availability checked", "finance", A,
                 "check_budget_availability", "v_budget_checked"),
        StepSpec("approve_allocation", "Budget allocated", "finance", A,
                 "approve_budget_allocation", "v_budget_allocated",
                 classify="classify_budget_amount"),
    ],
)


PAYROLL_SETUP = Playbook(
    key="payroll_setup",
    department="finance",
    title="Payroll Setup",
    description="A new hire needs to be added to payroll. Normally dispatched "
                "automatically by HR's onboarding — Finance's part of the "
                "cross-department mesh, not something you trigger by hand.",
    required_inputs=[
        {"name": "salary", "label": "Salary", "type": "text", "required": False},
        {"name": "start_date", "label": "Start date", "type": "date", "required": True},
    ],
    steps=[
        StepSpec("record_entry", "Payroll entry drafted", "finance", A,
                 "record_payroll_entry", "v_payroll_entry_drafted"),
        StepSpec("confirm_next_run", "Added to next payroll run", "finance", A,
                 "confirm_next_payroll_run", "v_payroll_confirmed"),
    ],
)


ALL_PLAYBOOKS = [INVOICE_RECONCILIATION, EXPENSE_CLAIM, BUDGET_REQUEST, PAYROLL_SETUP]
