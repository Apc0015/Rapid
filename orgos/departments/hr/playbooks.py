"""
orgos/departments/hr/playbooks.py — What the HR department knows how to do.

These are the ordered workflows a real small-company HR function needs. Each
step declares its owner specialist, its autonomy tier (who, if anyone, must
approve), the handler that executes it, and the SEPARATE verify check that
confirms it. Autonomy is set per step by consequence:

  onboarding / leave / policy  → fully A_auto (reversible, low-stakes)
  offboarding final settlement → B_approve  (money leaves the company)
  termination                  → C_human    (legal exposure, irreversible)
  statutory filing signature   → C_human    (binding, needs a signature)
"""

from __future__ import annotations

from orgos.models import Playbook, StepSpec, Autonomy

A = Autonomy.A_AUTO
B = Autonomy.B_APPROVE
C = Autonomy.C_HUMAN


ONBOARDING = Playbook(
    key="onboarding",
    department="hr",
    title="Employee Onboarding",
    description="From signed offer to an active, fully-provisioned new hire — "
                "the founder makes the hire decision and touches nothing else.",
    required_inputs=[
        {"name": "role", "label": "Role", "type": "text", "required": True},
        {"name": "start_date", "label": "Start date", "type": "date", "required": True},
        {"name": "salary", "label": "Salary (kept on file, never echoed)", "type": "text", "required": False},
        {"name": "email", "label": "Work email (optional)", "type": "text", "required": False},
        {"name": "manager", "label": "Reporting manager", "type": "text", "required": False},
    ],
    steps=[
        StepSpec("generate_offer", "Offer letter generated", "onboarding", A,
                 "generate_offer", "v_offer_exists",
                 "Draft the offer from the role, start date and comp."),
        StepSpec("send_for_signature", "Sent for e-signature", "onboarding", A,
                 "send_for_signature", "v_esign_sent"),
        StepSpec("confirm_signed", "Signed offer received", "onboarding", A,
                 "confirm_signed", "v_esign_signed",
                 "Confirmed against the e-sign provider's status, not self-reported."),
        StepSpec("dispatch_it_finance", "IT & Finance set up in parallel", "onboarding", A,
                 "dispatch_it_and_finance", "v_mesh_dispatched",
                 "HR doesn't provision accounts or payroll itself — it dispatches "
                 "IT's device provisioning and Finance's payroll setup as real, "
                 "independent runs, and only proceeds once both are confirmed done."),
        StepSpec("create_day1_schedule", "Day-1 schedule drafted", "onboarding", A,
                 "create_day1_schedule", "v_schedule_ready"),
        StepSpec("send_welcome", "Welcome message + docs sent", "onboarding", A,
                 "send_welcome", "v_welcome_sent"),
        StepSpec("collect_forms", "Onboarding forms requested", "onboarding", A,
                 "collect_forms", "v_forms_requested",
                 "Chased daily until the new hire returns them."),
        StepSpec("close_onboarding", "Run closed — employee active", "onboarding", A,
                 "close_onboarding", "v_employee_onboarded",
                 "Verifier confirms all state against the people record before close."),
    ],
)


OFFBOARDING = Playbook(
    key="offboarding",
    department="hr",
    title="Offboarding (Resignation)",
    description="Clean exit for a departing employee: settlement, access "
                "revocation and exit documents. Final pay needs your sign-off.",
    required_inputs=[
        {"name": "last_day", "label": "Last working day", "type": "date", "required": True},
        {"name": "reason", "label": "Reason (optional)", "type": "text", "required": False},
    ],
    steps=[
        StepSpec("record_departure", "Departure logged", "offboarding", A,
                 "record_departure", "v_departure_logged"),
        StepSpec("calc_final_settlement", "Final settlement prepared", "offboarding", B,
                 "calc_final_settlement", "v_settlement_ready",
                 "Final settlement moves money out of the company.",
                 escalate_reason="Final settlement for this employee needs your sign-off "
                                 "before it's scheduled."),
        StepSpec("revoke_access", "Access revoked across all systems", "offboarding", A,
                 "revoke_access", "v_access_revoked"),
        StepSpec("issue_exit_docs", "Exit documents issued", "offboarding", A,
                 "issue_exit_docs", "v_exit_docs_issued"),
    ],
)


TERMINATION = Playbook(
    key="termination",
    department="hr",
    title="Termination",
    description="Involuntary exit. Because of legal exposure, nothing happens "
                "until you confirm — this is a human-decides workflow end to end.",
    required_inputs=[
        {"name": "last_day", "label": "Effective date", "type": "date", "required": True},
        {"name": "reason", "label": "Reason", "type": "text", "required": True},
    ],
    steps=[
        StepSpec("confirm_termination", "Confirm termination", "offboarding", C,
                 "confirm_termination", "v_termination_confirmed",
                 "Legal exposure — requires an explicit founder decision.",
                 escalate_reason="This termination carries legal exposure. Nothing "
                                 "proceeds until you confirm the decision."),
        StepSpec("calc_final_settlement", "Final settlement prepared", "offboarding", B,
                 "calc_final_settlement", "v_settlement_ready",
                 escalate_reason="Approve the final settlement amount for this exit."),
        StepSpec("revoke_access", "Access revoked across all systems", "offboarding", A,
                 "revoke_access", "v_access_revoked"),
        StepSpec("issue_exit_docs", "Exit documents issued", "offboarding", A,
                 "issue_exit_docs", "v_exit_docs_issued"),
    ],
)


LEAVE = Playbook(
    key="leave",
    department="hr",
    title="Leave & PTO",
    description="An employee requests time off; HR checks policy and balance, "
                "records it, updates the calendar and notifies the manager. "
                "Zero founder involvement.",
    required_inputs=[
        {"name": "start", "label": "From", "type": "date", "required": True},
        {"name": "end", "label": "To", "type": "date", "required": True},
        {"name": "days", "label": "Number of days", "type": "number", "required": True},
        {"name": "manager", "label": "Manager to notify", "type": "text", "required": False},
    ],
    steps=[
        StepSpec("check_policy_balance", "Policy + balance checked", "leave", A,
                 "check_policy_balance", "v_leave_decided"),
        StepSpec("record_leave", "Leave recorded", "leave", A,
                 "record_leave", "v_leave_recorded"),
        StepSpec("update_calendar", "Team calendar updated", "leave", A,
                 "update_team_calendar", "v_calendar_updated"),
        StepSpec("notify_manager", "Manager notified", "leave", A,
                 "notify_manager", "v_manager_notified"),
        StepSpec("answer_employee", "Employee answered", "leave", A,
                 "answer_employee", "v_employee_answered"),
    ],
)


COMPLIANCE = Playbook(
    key="compliance",
    department="hr",
    title="Compliance & People Calendar",
    description="Tracks probation ends, contract renewals, visa expiries and "
                "statutory filings; prepares the document before the deadline "
                "and escalates only the signature.",
    required_inputs=[
        {"name": "item_type", "label": "Item type",
         "type": "select", "required": True,
         "options": ["visa_renewal", "probation_end", "contract_renewal", "statutory_filing"]},
        {"name": "due_date", "label": "Due date", "type": "date", "required": True},
    ],
    steps=[
        StepSpec("detect_deadline", "Deadline tracked", "compliance", A,
                 "detect_deadline", "v_deadline_tracked"),
        StepSpec("prepare_doc", "Document prepared ahead of deadline", "compliance", A,
                 "prepare_compliance_doc", "v_doc_prepared"),
        StepSpec("schedule_reminder", "Reminder scheduled", "compliance", A,
                 "schedule_reminder", "v_reminder_scheduled"),
        StepSpec("file_with_signature", "File with signature", "compliance", C,
                 "file_with_signature", "v_filed",
                 "Statutory filing is binding and needs a signature.",
                 escalate_reason="This filing is binding and needs your signature "
                                 "before the deadline."),
    ],
)


POLICY_QA = Playbook(
    key="policy_qa",
    department="hr",
    title="Policy Question",
    description="An employee asks an HR/policy question; the Policy & Docs "
                "specialist answers from the handbook. The old chat box, "
                "demoted to one trigger type among many.",
    required_inputs=[
        {"name": "question", "label": "Question", "type": "text", "required": True},
    ],
    steps=[
        StepSpec("answer_policy_question", "Policy question answered", "policy", A,
                 "answer_policy_question", "v_answer_given"),
    ],
)


ALL_PLAYBOOKS = [ONBOARDING, OFFBOARDING, TERMINATION, LEAVE, COMPLIANCE, POLICY_QA]
