"""
orgos/departments/hr — the HR department, as a plug-in to the org core.

register() wires HR's playbooks, specialist handlers and independent verify
checks into the shared Registry. The engine and store never import anything
from here; they only look these up by name. That is the contract every future
department follows — copy this shape for Finance, IT, Legal, and the loop, the
verifier, the escalation gate and the UI all work unchanged.
"""

from __future__ import annotations

from orgos.departments.hr import specialists as S
from orgos.departments.hr import verifiers as V
from orgos.departments.hr.playbooks import ALL_PLAYBOOKS


def register(reg) -> None:
    for pb in ALL_PLAYBOOKS:
        reg.register_playbook(pb)

    # Specialist handlers (Tier 3).
    handlers = {
        "generate_offer": S.generate_offer,
        "send_for_signature": S.send_for_signature,
        "confirm_signed": S.confirm_signed,
        "dispatch_it_and_finance": S.dispatch_it_and_finance,
        "create_day1_schedule": S.create_day1_schedule,
        "send_welcome": S.send_welcome,
        "collect_forms": S.collect_forms,
        "close_onboarding": S.close_onboarding,
        "record_departure": S.record_departure,
        "confirm_termination": S.confirm_termination,
        "calc_final_settlement": S.calc_final_settlement,
        "revoke_access": S.revoke_access,
        "issue_exit_docs": S.issue_exit_docs,
        "check_policy_balance": S.check_policy_balance,
        "record_leave": S.record_leave,
        "update_team_calendar": S.update_team_calendar,
        "notify_manager": S.notify_manager,
        "answer_employee": S.answer_employee,
        "detect_deadline": S.detect_deadline,
        "prepare_compliance_doc": S.prepare_compliance_doc,
        "schedule_reminder": S.schedule_reminder,
        "file_with_signature": S.file_with_signature,
        "answer_policy_question": S.answer_policy_question,
    }
    for name, fn in handlers.items():
        reg.register_handler(name, fn)

    # Independent verify checks (Tier 4).
    verifies = {
        "v_offer_exists": V.v_offer_exists,
        "v_esign_sent": V.v_esign_sent,
        "v_esign_signed": V.v_esign_signed,
        "v_mesh_dispatched": V.v_mesh_dispatched,
        "v_schedule_ready": V.v_schedule_ready,
        "v_welcome_sent": V.v_welcome_sent,
        "v_forms_requested": V.v_forms_requested,
        "v_employee_onboarded": V.v_employee_onboarded,
        "v_departure_logged": V.v_departure_logged,
        "v_termination_confirmed": V.v_termination_confirmed,
        "v_settlement_ready": V.v_settlement_ready,
        "v_access_revoked": V.v_access_revoked,
        "v_exit_docs_issued": V.v_exit_docs_issued,
        "v_leave_decided": V.v_leave_decided,
        "v_leave_recorded": V.v_leave_recorded,
        "v_calendar_updated": V.v_calendar_updated,
        "v_manager_notified": V.v_manager_notified,
        "v_employee_answered": V.v_employee_answered,
        "v_deadline_tracked": V.v_deadline_tracked,
        "v_doc_prepared": V.v_doc_prepared,
        "v_reminder_scheduled": V.v_reminder_scheduled,
        "v_filed": V.v_filed,
        "v_answer_given": V.v_answer_given,
    }
    for name, fn in verifies.items():
        reg.register_verify(name, fn)
