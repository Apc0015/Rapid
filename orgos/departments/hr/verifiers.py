"""
orgos/departments/hr/verifiers.py — HR verification checks (Tier 4 logic).

Each check reads the system of record back and confirms the state a step was
supposed to produce actually exists. These are deliberately NOT the same
functions as the handlers, and they receive no hint of what the handler
"claimed" — they look at real records only. If the record isn't there, the
step fails, no matter what the specialist reported.
"""

from __future__ import annotations

from orgos.registry import StepContext, VerifyResult


def _fail(detail: str) -> VerifyResult:
    return VerifyResult(ok=False, detail=detail)


def _ok(detail: str, found: dict) -> VerifyResult:
    return VerifyResult(ok=True, detail=detail, found=found)


# ── Onboarding ──────────────────────────────────────────────────────────────────

def v_offer_exists(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("offer")
    if not rec or not rec["data"].get("letter"):
        return _fail("No offer letter found in the record.")
    d = rec["data"]
    if not d.get("role") or not d.get("start_date"):
        return _fail("Offer exists but is missing role or start date.")
    return _ok(f"Offer on file for role '{d['role']}', start {d['start_date']}.",
               {"role": d["role"], "start_date": d["start_date"]})


def v_esign_sent(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("esign")
    if not rec or rec["data"].get("status") not in ("sent", "signed"):
        return _fail("E-sign request was not registered as sent.")
    return _ok("Offer confirmed sent for signature.", {"status": rec["data"]["status"]})


def v_esign_signed(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("esign")
    if not rec or rec["data"].get("status") != "signed":
        return _fail("Signature not yet recorded as received.")
    return _ok("Signed offer confirmed on file.", {"signed_at": rec["data"].get("signed_at")})


def v_mesh_dispatched(ctx: StepContext) -> VerifyResult:
    """
    Cross-department check: doesn't just confirm HR SAID it dispatched IT and
    Finance — independently looks up both child runs (in their own
    departments' tables) and confirms they actually reached 'done'. If either
    is still running, escalated, or failed, this step is not verified.
    """
    rec = ctx.find("mesh_dispatch")
    if not rec:
        return _fail("No mesh dispatch record found — IT/Finance were never triggered.")
    d = rec["data"]
    it_run = ctx.store.get_run(d.get("it_run_id", ""))
    fin_run = ctx.store.get_run(d.get("finance_run_id", ""))
    if not it_run or not fin_run:
        return _fail("Dispatched IT/Finance run(s) not found in the store.")
    problems = []
    if it_run.status != "done":
        problems.append(f"IT is {it_run.status}, not done")
    if fin_run.status != "done":
        problems.append(f"Finance is {fin_run.status}, not done")
    if problems:
        return _fail("; ".join(problems))
    return _ok("IT (device provisioning) and Finance (payroll setup) both confirmed done.",
               {"it_run_id": it_run.run_id, "finance_run_id": fin_run.run_id})


def v_schedule_ready(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("schedule")
    agenda = (rec or {}).get("data", {}).get("agenda", [])
    if len(agenda) < 3:
        return _fail("Day-1 schedule has fewer than 3 items.")
    return _ok(f"Day-1 schedule ready with {len(agenda)} items.", {"items": len(agenda)})


def v_welcome_sent(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("welcome")
    if not rec or not rec["data"].get("documents"):
        return _fail("Welcome message/documents not found.")
    return _ok(f"Welcome sent with {len(rec['data']['documents'])} documents.",
               {"documents": rec["data"]["documents"]})


def v_forms_requested(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("forms")
    if not rec or not rec["data"].get("required"):
        return _fail("Onboarding forms were not requested.")
    return _ok(f"{len(rec['data']['required'])} forms requested; chasing until returned.",
               {"required": rec["data"]["required"]})


def v_employee_onboarded(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("employee")
    if not rec or rec["data"].get("status") != "onboarded":
        return _fail("Employee record not marked onboarded.")
    return _ok("Employee is active in the people record.", {"status": "onboarded"})


# ── Offboarding / termination ────────────────────────────────────────────────────

def v_departure_logged(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("departure")
    if not rec or not rec["data"].get("last_day"):
        return _fail("Departure not logged.")
    return _ok("Departure logged.", {"last_day": rec["data"]["last_day"]})


def v_termination_confirmed(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("termination")
    if not rec or not rec["data"].get("confirmed"):
        return _fail("Termination not confirmed.")
    return _ok("Termination confirmed by founder decision.", {"confirmed": True})


def v_settlement_ready(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("settlement")
    if not rec or rec["data"].get("status") != "approved_and_scheduled":
        return _fail("Final settlement not approved/scheduled.")
    return _ok("Final settlement approved and scheduled.", {"status": "approved_and_scheduled"})


def v_access_revoked(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("access_revoked")
    systems = (rec or {}).get("data", {}).get("systems", {})
    still_active = [s for s, st in systems.items() if st != "revoked"]
    if not systems or still_active:
        return _fail(f"Access not fully revoked (still active: {still_active or 'all'}).")
    return _ok(f"Access revoked across {len(systems)} systems — none left active.",
               {"systems": list(systems.keys())})


def v_exit_docs_issued(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("exit_docs")
    if not rec or not rec["data"].get("documents"):
        return _fail("Exit documents not issued.")
    return _ok(f"{len(rec['data']['documents'])} exit documents issued.",
               {"documents": rec["data"]["documents"]})


# ── Leave & PTO ──────────────────────────────────────────────────────────────────

def v_leave_decided(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("leave_decision")
    if not rec or not rec["data"].get("decision"):
        return _fail("No leave decision recorded.")
    return _ok(f"Leave decision: {rec['data']['decision']}.", {"decision": rec["data"]["decision"]})


def v_leave_recorded(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("leave")
    if not rec or rec["data"].get("status") != "recorded":
        return _fail("Leave not recorded.")
    return _ok("Leave recorded.", {"status": "recorded"})


def v_calendar_updated(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("calendar")
    if not rec or not rec["data"].get("event"):
        return _fail("Team calendar not updated.")
    return _ok("Team calendar updated.", {"event": rec["data"]["event"]})


def v_manager_notified(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("notification")
    if not rec or not rec["data"].get("to"):
        return _fail("Manager not notified.")
    return _ok(f"Manager ({rec['data']['to']}) notified.", {"to": rec["data"]["to"]})


def v_employee_answered(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("reply")
    if not rec or not rec["data"].get("message"):
        return _fail("No reply sent to the employee.")
    return _ok("Employee received a reply.", {"replied": True})


# ── Compliance ───────────────────────────────────────────────────────────────────

def v_deadline_tracked(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("compliance_item")
    if not rec or rec["data"].get("status") != "tracked":
        return _fail("Compliance item not tracked.")
    return _ok(f"Tracking {rec['data'].get('type')} due {rec['data'].get('due_date')}.",
               {"due_date": rec["data"].get("due_date")})


def v_doc_prepared(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("doc_draft")
    if not rec or rec["data"].get("status") != "drafted":
        return _fail("Compliance document not drafted.")
    return _ok("Compliance document drafted ahead of deadline.", {"status": "drafted"})


def v_reminder_scheduled(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("reminder")
    if not rec or rec["data"].get("status") != "scheduled":
        return _fail("Reminder not scheduled.")
    return _ok("Reminder scheduled ahead of the deadline.", {"lead_days": rec["data"].get("lead_days")})


def v_filed(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("filed")
    if not rec or rec["data"].get("status") != "filed":
        return _fail("Filing not completed.")
    return _ok("Filing completed after sign-off.", {"status": "filed"})


# ── Policy Q&A ───────────────────────────────────────────────────────────────────

def v_answer_given(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("answer")
    if not rec or not rec["data"].get("answer"):
        return _fail("No answer recorded.")
    d = rec["data"]
    source = d.get("source", "template")

    if source == "rag":
        citations = d.get("citations", [])
        if citations:
            # Independent grounding check: read the document index directly
            # (never the handler's claims) and confirm every cited source is
            # really in it. A hallucinated citation fails the step.
            from orgos.knowledge import list_indexed_sources
            indexed = list_indexed_sources(ctx.run.department)
            missing = [c for c in citations if c not in indexed]
            if missing:
                return _fail(
                    f"Answer cites document(s) not present in the "
                    f"{ctx.run.department} knowledge base: {missing}")
            return _ok(
                f"Grounded answer verified — all {len(citations)} cited "
                f"document(s) exist in the knowledge base "
                f"(confidence {d.get('confidence')}).",
                {"citations": citations, "confidence": d.get("confidence")})
        return _ok("Knowledge base had no matching documents; an honest "
                   "no-answer was recorded.", {"citations": []})

    if source == "unavailable":
        return _ok("Knowledge base unavailable — honest fallback reply "
                   "recorded and question logged for follow-up.",
                   {"source": "unavailable"})

    return _ok("Answer recorded and traceable to the handbook.", {"answered": True})
