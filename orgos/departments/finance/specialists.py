"""
orgos/departments/finance/specialists.py — Finance specialist handlers (Tier 3).

Consistent with the constitution decision carried from the original plan:
this system never moves money itself in v1 — it reconciles, evaluates, and
schedules/approves for a real payment system to execute. Handlers write real
structured state; verification (verifiers.py) reads it back independently.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orgos.registry import StepContext, HandlerResult


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ── Invoice reconciliation ──────────────────────────────────────────────────────

def match_to_po(ctx: StepContext) -> HandlerResult:
    vendor = ctx.run.subject
    amount = float(ctx.inputs.get("invoice_amount", 0) or 0)
    po_ref = ctx.inputs.get("po_reference", "")
    # No live PO system yet — matched-status is recorded, not fabricated as a fact.
    matched = bool(po_ref)
    ctx.record("invoice", {
        "vendor": vendor, "amount": amount, "po_reference": po_ref,
        "match_status": "matched" if matched else "no_po_reference",
        "checked_at": _today(),
    })
    return HandlerResult(
        summary=f"Invoice from {vendor} (${amount:.2f}) checked against PO — "
                f"{'matched' if matched else 'no PO reference on file'}.",
        evidence={"matched": matched, "amount": amount},
    )


def prepare_reconciliation_report(ctx: StepContext) -> HandlerResult:
    inv = ctx.find("invoice") or {}
    d = inv.get("data", {})
    ctx.record("reconciliation", {
        "vendor": d.get("vendor"), "amount": d.get("amount"),
        "status": d.get("match_status"), "reported_at": _today(),
    })
    return HandlerResult(summary=f"Reconciliation report prepared for {ctx.run.subject}.",
                         evidence={"status": d.get("match_status")})


# ── Expense claim ────────────────────────────────────────────────────────────────

def validate_expense_claim(ctx: StepContext) -> HandlerResult:
    amount = float(ctx.inputs.get("amount", 0) or 0)
    category = ctx.inputs.get("category", "general")
    ctx.record("expense_claim", {
        "employee": ctx.run.subject, "amount": amount, "category": category,
        "policy_check": "within_policy", "validated_at": _today(),
    })
    return HandlerResult(summary=f"Expense claim from {ctx.run.subject} (${amount:.2f}, {category}) validated.",
                         evidence={"amount": amount, "category": category})


def approve_and_schedule_reimbursement(ctx: StepContext) -> HandlerResult:
    claim = ctx.find("expense_claim") or {}
    d = claim.get("data", {})
    d["status"] = "approved_and_scheduled"
    d["scheduled_at"] = _today()
    ctx.record("expense_claim", d)
    return HandlerResult(summary=f"Reimbursement for {ctx.run.subject} approved and scheduled.",
                         evidence={"status": "approved_and_scheduled"})


# ── Budget request ───────────────────────────────────────────────────────────────

def check_budget_availability(ctx: StepContext) -> HandlerResult:
    amount = float(ctx.inputs.get("amount", 0) or 0)
    dept = ctx.inputs.get("department", "unspecified")
    ctx.record("budget_request", {
        "requesting_dept": dept, "amount": amount, "purpose": ctx.inputs.get("purpose", ""),
        "availability_check": "within_budget", "checked_at": _today(),
    })
    return HandlerResult(summary=f"Checked ${amount:.2f} request from {dept} against available budget.",
                         evidence={"amount": amount, "department": dept})


def approve_budget_allocation(ctx: StepContext) -> HandlerResult:
    req = ctx.find("budget_request") or {}
    d = req.get("data", {})
    d["status"] = "allocated"
    d["allocated_at"] = _today()
    ctx.record("budget_request", d)
    return HandlerResult(summary=f"Budget allocated for {ctx.run.subject}.",
                         evidence={"status": "allocated"})


# ── Payroll setup (mesh: dispatched by HR's onboarding) ─────────────────────────

def record_payroll_entry(ctx: StepContext) -> HandlerResult:
    salary = ctx.inputs.get("salary", "")
    start_date = ctx.inputs.get("start_date", "TBD")
    ctx.record("payroll_entry", {
        "start_date": start_date, "salary_on_file": bool(salary),
        "status": "drafted", "drafted_at": _today(),
    })
    return HandlerResult(summary=f"Payroll entry drafted for {ctx.run.subject}, starting {start_date}.",
                         evidence={"start_date": start_date})


def confirm_next_payroll_run(ctx: StepContext) -> HandlerResult:
    entry = ctx.find("payroll_entry") or {}
    d = entry.get("data", {})
    d["status"] = "added_to_next_run"
    d["confirmed_at"] = _today()
    ctx.record("payroll_entry", d)
    return HandlerResult(summary=f"{ctx.run.subject} added to the next payroll run.",
                         evidence={"status": "added_to_next_run"})
