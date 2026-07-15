"""orgos/departments/finance — the Finance department, as a plug-in to the org core."""

from __future__ import annotations

from orgos.departments.finance import specialists as S
from orgos.departments.finance import verifiers as V
from orgos.departments.finance import classifiers as C
from orgos.departments.finance.playbooks import ALL_PLAYBOOKS


def register(reg) -> None:
    for pb in ALL_PLAYBOOKS:
        reg.register_playbook(pb)

    handlers = {
        "match_to_po": S.match_to_po,
        "prepare_reconciliation_report": S.prepare_reconciliation_report,
        "validate_expense_claim": S.validate_expense_claim,
        "approve_and_schedule_reimbursement": S.approve_and_schedule_reimbursement,
        "check_budget_availability": S.check_budget_availability,
        "approve_budget_allocation": S.approve_budget_allocation,
        "record_payroll_entry": S.record_payroll_entry,
        "confirm_next_payroll_run": S.confirm_next_payroll_run,
    }
    for name, fn in handlers.items():
        reg.register_handler(name, fn)

    verifies = {
        "v_invoice_checked": V.v_invoice_checked,
        "v_reconciliation_ready": V.v_reconciliation_ready,
        "v_expense_validated": V.v_expense_validated,
        "v_reimbursement_scheduled": V.v_reimbursement_scheduled,
        "v_budget_checked": V.v_budget_checked,
        "v_budget_allocated": V.v_budget_allocated,
        "v_payroll_entry_drafted": V.v_payroll_entry_drafted,
        "v_payroll_confirmed": V.v_payroll_confirmed,
    }
    for name, fn in verifies.items():
        reg.register_verify(name, fn)

    reg.register_classifier("classify_expense_amount", C.classify_expense_amount)
    reg.register_classifier("classify_budget_amount", C.classify_budget_amount)
