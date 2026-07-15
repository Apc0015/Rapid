"""
orgos/departments/hr/specialists.py — HR specialist handlers (Tier 3).

Each function is one specialist doing one job. A handler does real work:
it writes structured state into the organization's system of record (via
ctx.record / ctx.find). It never decides whether its own work is correct —
that is the Verifier's job (see verifiers.py), wired separately.

There is no live Slack/DocuSign/Workspace in v1, so the database is the system
of record: provisioning an account means writing an 'accounts' record that the
IT admin console would later mirror. Verification reads that record back. When
those integrations land, only these handlers change — the loop, the verifier,
and the UI do not.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orgos.registry import StepContext, HandlerResult


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _mask_salary(value) -> str:
    """HR holds real comp, but we never echo a raw number back into summaries."""
    return "[on file]" if value not in (None, "") else "[not provided]"


# ── Onboarding specialist ───────────────────────────────────────────────────────

def generate_offer(ctx: StepContext) -> HandlerResult:
    inp = ctx.inputs
    name = ctx.run.subject
    role = inp.get("role", "New Hire")
    start = inp.get("start_date", "TBD")
    salary = inp.get("salary", "")
    letter = (
        f"Dear {name},\n\n"
        f"We are delighted to offer you the position of {role} at the company, "
        f"starting {start}. Your compensation and full terms are set out in the "
        f"attached agreement.\n\nWelcome aboard,\nPeople Ops"
    )
    # Provisional employee record + the offer artifact.
    ctx.record("employee", {
        "name": name, "role": role, "start_date": start,
        "salary_on_file": bool(salary), "status": "offer_extended",
    })
    ctx.record("offer", {
        "name": name, "role": role, "start_date": start,
        "salary": _mask_salary(salary), "letter": letter, "status": "drafted",
    })
    return HandlerResult(
        summary=f"Offer letter generated for {name} ({role}), start {start}.",
        evidence={"role": role, "start_date": start, "salary": _mask_salary(salary)},
    )


def send_for_signature(ctx: StepContext) -> HandlerResult:
    offer = ctx.find("offer") or {}
    ctx.record("esign", {"provider": "e-sign", "status": "sent", "sent_at": _today()})
    return HandlerResult(
        summary=f"Offer sent to {ctx.run.subject} for e-signature.",
        evidence={"provider": "e-sign", "status": "sent"},
    )


def confirm_signed(ctx: StepContext) -> HandlerResult:
    esign = ctx.find("esign") or {}
    esign.update({"status": "signed", "signed_at": _today()})
    ctx.record("esign", esign)
    emp = ctx.find("employee") or {}
    emp["status"] = "offer_signed"
    ctx.record("employee", emp)
    return HandlerResult(
        summary=f"Signed offer received from {ctx.run.subject}.",
        evidence={"status": "signed"},
    )


def dispatch_it_and_finance(ctx: StepContext) -> HandlerResult:
    """
    The mesh in action: onboarding isn't an HR-only job, so HR doesn't fake
    provisioning accounts itself — it dispatches IT's real device_provisioning
    playbook and Finance's real payroll_setup playbook, in parallel, and
    records both child run IDs. close_onboarding's verify (below) checks that
    BOTH actually finished before HR is allowed to call this done.
    """
    name = ctx.run.subject
    role = ctx.inputs.get("role", "New Hire")

    it_run = ctx.trigger_department(
        "it", "device_provisioning", subject=name,
        inputs={"role": role, "equipment": "laptop"},
    )
    finance_run = ctx.trigger_department(
        "finance", "payroll_setup", subject=name,
        inputs={"salary": ctx.inputs.get("salary", ""),
                "start_date": ctx.inputs.get("start_date", "")},
    )

    ctx.record("mesh_dispatch", {
        "it_run_id": it_run.run_id, "it_status": it_run.status,
        "finance_run_id": finance_run.run_id, "finance_status": finance_run.status,
        "dispatched_at": _today(),
    })
    return HandlerResult(
        summary=f"Dispatched IT (device provisioning) and Finance (payroll setup) for {name}.",
        evidence={"it_run_id": it_run.run_id, "finance_run_id": finance_run.run_id},
    )


def create_day1_schedule(ctx: StepContext) -> HandlerResult:
    start = ctx.inputs.get("start_date", "day 1")
    agenda = [
        {"time": "09:30", "item": "Welcome + workspace setup"},
        {"time": "11:00", "item": "Team intro & role expectations"},
        {"time": "14:00", "item": "Systems access walkthrough"},
        {"time": "16:00", "item": "1:1 with manager"},
    ]
    ctx.record("schedule", {"start_date": start, "agenda": agenda})
    return HandlerResult(
        summary=f"Day-1 schedule drafted for {ctx.run.subject} ({len(agenda)} items).",
        evidence={"items": len(agenda)},
    )


def send_welcome(ctx: StepContext) -> HandlerResult:
    name = ctx.run.subject
    docs = ["Employee handbook", "Code of conduct", "Benefits guide", "IT policy"]
    msg = (f"Hi {name.split()[0]}, welcome to the team! Your first-day schedule and "
           f"the documents below are attached. Reply here with any questions.")
    ctx.record("welcome", {"message": msg, "documents": docs, "sent_at": _today()})
    return HandlerResult(
        summary=f"Welcome message + {len(docs)} documents sent to {name}.",
        evidence={"documents": docs},
    )


def collect_forms(ctx: StepContext) -> HandlerResult:
    required = ["ID proof", "Tax form", "Bank details", "Emergency contact"]
    # New hire hasn't returned them yet — HR will chase daily until complete.
    ctx.record("forms", {
        "required": required,
        "received": [],
        "status": "chasing",
        "requested_at": _today(),
    })
    return HandlerResult(
        summary=f"Requested {len(required)} onboarding forms from {ctx.run.subject}; "
                f"will chase daily until returned.",
        evidence={"required": required, "received": 0},
    )


def close_onboarding(ctx: StepContext) -> HandlerResult:
    emp = ctx.find("employee") or {}
    emp["status"] = "onboarded"
    ctx.record("employee", emp)
    return HandlerResult(
        summary=f"{ctx.run.subject} marked active in the people record.",
        evidence={"status": "onboarded"},
    )


# ── Offboarding / termination specialist ────────────────────────────────────────

def record_departure(ctx: StepContext) -> HandlerResult:
    last_day = ctx.inputs.get("last_day", "TBD")
    reason = ctx.inputs.get("reason", "")
    ctx.record("departure", {"last_day": last_day, "reason": reason, "logged_at": _today()})
    return HandlerResult(
        summary=f"Departure logged for {ctx.run.subject}, last day {last_day}.",
        evidence={"last_day": last_day},
    )


def confirm_termination(ctx: StepContext) -> HandlerResult:
    # Only reached after a human approves the C_human gate.
    ctx.record("termination", {"confirmed": True, "confirmed_at": _today()})
    return HandlerResult(
        summary=f"Termination of {ctx.run.subject} confirmed by founder decision.",
        evidence={"confirmed": True},
    )


def calc_final_settlement(ctx: StepContext) -> HandlerResult:
    # Only reached after a human approves the B_approve gate (money).
    ctx.record("settlement", {
        "components": ["unpaid_salary", "leave_encashment", "gratuity_if_applicable"],
        "status": "approved_and_scheduled",
        "prepared_at": _today(),
    })
    return HandlerResult(
        summary=f"Final settlement for {ctx.run.subject} prepared and scheduled.",
        evidence={"status": "approved_and_scheduled"},
    )


def revoke_access(ctx: StepContext) -> HandlerResult:
    systems = ["google_workspace", "slack", "github", "vpn"]
    ctx.record("access_revoked", {
        "systems": {s: "revoked" for s in systems},
        "revoked_at": _today(),
    })
    return HandlerResult(
        summary=f"Access revoked for {ctx.run.subject} across {len(systems)} systems.",
        evidence={"systems": systems},
    )


def issue_exit_docs(ctx: StepContext) -> HandlerResult:
    docs = ["Relieving letter", "Experience certificate", "Final payslip"]
    ctx.record("exit_docs", {"documents": docs, "issued_at": _today()})
    return HandlerResult(
        summary=f"Exit documents issued to {ctx.run.subject}.",
        evidence={"documents": docs},
    )


# ── Leave & PTO specialist ──────────────────────────────────────────────────────

def check_policy_balance(ctx: StepContext) -> HandlerResult:
    name = ctx.run.subject
    days = int(ctx.inputs.get("days", 2))
    # Seed a balance if none exists, then decide.
    bal = ctx.find("leave_balance")
    remaining = bal["data"]["remaining"] if bal else 18
    decision = "approved" if days <= remaining else "insufficient_balance"
    ctx.record("leave_balance", {"remaining": remaining, "policy": "18 days annual"})
    ctx.record("leave_decision", {"days": days, "decision": decision})
    return HandlerResult(
        summary=f"Checked {name}'s balance ({remaining}d) against {days}d request → {decision}.",
        evidence={"remaining": remaining, "requested": days, "decision": decision},
    )


def record_leave(ctx: StepContext) -> HandlerResult:
    ctx.record("leave", {
        "start": ctx.inputs.get("start", "TBD"),
        "end": ctx.inputs.get("end", "TBD"),
        "days": int(ctx.inputs.get("days", 2)),
        "status": "recorded",
    })
    return HandlerResult(summary=f"Leave recorded for {ctx.run.subject}.",
                         evidence={"status": "recorded"})


def update_team_calendar(ctx: StepContext) -> HandlerResult:
    ctx.record("calendar", {"event": f"{ctx.run.subject} — Out of office",
                            "start": ctx.inputs.get("start", "TBD"),
                            "end": ctx.inputs.get("end", "TBD")})
    return HandlerResult(summary=f"Team calendar updated for {ctx.run.subject}'s leave.",
                         evidence={"calendar": "updated"})


def notify_manager(ctx: StepContext) -> HandlerResult:
    mgr = ctx.inputs.get("manager", "the manager")
    ctx.record("notification", {"to": mgr, "about": "leave", "sent_at": _today()})
    return HandlerResult(summary=f"Notified {mgr} of {ctx.run.subject}'s leave.",
                         evidence={"to": mgr})


def answer_employee(ctx: StepContext) -> HandlerResult:
    dec = ctx.find("leave_decision") or {}
    verdict = (dec.get("data") or {}).get("decision", "recorded")
    reply = (f"Your leave is {verdict.replace('_', ' ')}. It's on the team calendar and "
             f"your manager has been notified.")
    ctx.record("reply", {"message": reply})
    return HandlerResult(summary=f"Replied to {ctx.run.subject}.", evidence={"reply": reply})


# ── Compliance & people-calendar specialist ─────────────────────────────────────

def detect_deadline(ctx: StepContext) -> HandlerResult:
    item = ctx.inputs.get("item_type", "compliance item")
    due = ctx.inputs.get("due_date", "TBD")
    ctx.record("compliance_item", {"type": item, "due_date": due, "status": "tracked"})
    return HandlerResult(summary=f"Tracking {item} for {ctx.run.subject}, due {due}.",
                         evidence={"type": item, "due_date": due})


def prepare_compliance_doc(ctx: StepContext) -> HandlerResult:
    item = ctx.inputs.get("item_type", "document")
    ctx.record("doc_draft", {"for": item, "status": "drafted", "drafted_at": _today()})
    return HandlerResult(summary=f"Prepared draft for {item} ({ctx.run.subject}).",
                         evidence={"status": "drafted"})


def schedule_reminder(ctx: StepContext) -> HandlerResult:
    due = ctx.inputs.get("due_date", "TBD")
    ctx.record("reminder", {"due_date": due, "lead_days": 7, "status": "scheduled"})
    return HandlerResult(summary=f"Reminder scheduled ahead of {due}.",
                         evidence={"due_date": due})


def file_with_signature(ctx: StepContext) -> HandlerResult:
    # Only after a human approves the C_human gate.
    ctx.record("filed", {"status": "filed", "filed_at": _today()})
    return HandlerResult(summary=f"Filing for {ctx.run.subject} completed after sign-off.",
                         evidence={"status": "filed"})


# ── Policy & docs specialist (the demoted chat trigger) ─────────────────────────

def answer_policy_question(ctx: StepContext) -> HandlerResult:
    q = ctx.inputs.get("question", "")
    from orgos.knowledge import ask_knowledge_base

    res = ask_knowledge_base(q, ctx.run.department)
    if res is not None:
        ctx.record("answer", {
            "question": q,
            "answer": res["answer"],
            "citations": res["citations"],
            "confidence": res["confidence"],
            "source": "rag",
            "answered_at": _today(),
        })
        cited = ", ".join(res["citations"]) if res["citations"] else "no matching documents"
        return HandlerResult(
            summary=f"Policy question answered from the knowledge base ({cited}).",
            evidence={"question": q, "citations": res["citations"],
                      "confidence": res["confidence"]})

    # Knowledge backend unreachable — say so, never fake a grounded answer.
    answer = ("The HR knowledge base could not be reached right now. "
              "Your question has been logged and HR will follow up with a "
              "sourced answer.")
    ctx.record("answer", {
        "question": q,
        "answer": answer,
        "citations": [],
        "source": "unavailable",
        "answered_at": _today(),
    })
    return HandlerResult(
        summary="Knowledge base unavailable — question logged and an honest "
                "fallback reply sent.",
        evidence={"question": q, "source": "unavailable"})
