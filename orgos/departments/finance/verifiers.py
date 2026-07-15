"""
orgos/departments/finance/verifiers.py — Finance verification checks (Tier 4).
"""

from __future__ import annotations

from orgos.registry import StepContext, VerifyResult


def _fail(detail: str) -> VerifyResult:
    return VerifyResult(ok=False, detail=detail)


def _ok(detail: str, found: dict) -> VerifyResult:
    return VerifyResult(ok=True, detail=detail, found=found)


def v_invoice_checked(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("invoice")
    if not rec or not rec["data"].get("match_status"):
        return _fail("Invoice not checked against a PO.")
    return _ok(f"Invoice check on file: {rec['data']['match_status']}.",
               {"match_status": rec["data"]["match_status"]})


def v_reconciliation_ready(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("reconciliation")
    if not rec or not rec["data"].get("status"):
        return _fail("Reconciliation report not prepared.")
    return _ok("Reconciliation report on file.", {"status": rec["data"]["status"]})


def v_expense_validated(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("expense_claim")
    if not rec or rec["data"].get("policy_check") != "within_policy":
        return _fail("Expense claim not validated against policy.")
    return _ok("Expense claim validated against policy.", {"amount": rec["data"].get("amount")})


def v_reimbursement_scheduled(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("expense_claim")
    if not rec or rec["data"].get("status") != "approved_and_scheduled":
        return _fail("Reimbursement not approved/scheduled.")
    return _ok("Reimbursement confirmed approved and scheduled.", {"status": rec["data"]["status"]})


def v_budget_checked(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("budget_request")
    if not rec or not rec["data"].get("availability_check"):
        return _fail("Budget availability not checked.")
    return _ok(f"Budget check: {rec['data']['availability_check']}.",
               {"amount": rec["data"].get("amount")})


def v_budget_allocated(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("budget_request")
    if not rec or rec["data"].get("status") != "allocated":
        return _fail("Budget not allocated.")
    return _ok("Budget allocation confirmed.", {"status": "allocated"})


def v_payroll_entry_drafted(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("payroll_entry")
    if not rec or rec["data"].get("status") not in ("drafted", "added_to_next_run"):
        return _fail("Payroll entry not drafted.")
    return _ok(f"Payroll entry on file, starting {rec['data'].get('start_date')}.",
               {"start_date": rec["data"].get("start_date")})


def v_payroll_confirmed(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("payroll_entry")
    if not rec or rec["data"].get("status") != "added_to_next_run":
        return _fail("Not confirmed added to next payroll run.")
    return _ok("Confirmed added to next payroll run.", {"status": "added_to_next_run"})
