"""
orgos/departments/it/playbooks.py — what the IT department knows how to do.

Device/account provisioning and access revocation are fully A_auto — both
are reversible and, for revocation, the risk runs the OTHER way (not acting
fast is the danger). The license request step is dynamically classified by
cost (see classifiers.py): cheap tools run unattended, expensive ones need
sign-off — consequence is read from the real amount, not a fixed label.
"""

from __future__ import annotations

from orgos.models import Playbook, StepSpec, Autonomy

A = Autonomy.A_AUTO
B = Autonomy.B_APPROVE


DEVICE_PROVISIONING = Playbook(
    key="device_provisioning",
    department="it",
    title="Device & Account Provisioning",
    description="New hire or contractor needs a machine and system access, "
                "ready before their first day.",
    required_inputs=[
        {"name": "role", "label": "Role", "type": "text", "required": True},
        {"name": "equipment", "label": "Equipment", "type": "text", "required": False},
    ],
    steps=[
        StepSpec("order_equipment", "Equipment ordered", "it", A,
                 "order_equipment", "v_equipment_ordered"),
        StepSpec("provision_accounts", "IT accounts provisioned", "it", A,
                 "provision_it_accounts", "v_it_accounts_provisioned"),
        StepSpec("configure_security", "Security policy applied", "it", A,
                 "configure_security_policy", "v_security_configured"),
        StepSpec("confirm_active", "Setup confirmed active", "it", A,
                 "confirm_it_active", "v_it_active"),
    ],
)


ACCESS_REVOCATION = Playbook(
    key="access_revocation",
    department="it",
    title="Access Revocation",
    description="An employee is leaving — every system access point closed "
                "the same day, independently confirmed clean.",
    required_inputs=[
        {"name": "last_day", "label": "Last working day", "type": "date", "required": True},
    ],
    steps=[
        StepSpec("revoke_accounts", "IT accounts revoked", "it", A,
                 "revoke_it_accounts", "v_it_accounts_revoked"),
        StepSpec("reclaim_device", "Device reclaim scheduled", "it", A,
                 "reclaim_device", "v_device_reclaim_scheduled"),
        StepSpec("confirm_clean", "Access audit — confirmed clean", "it", A,
                 "confirm_access_clean", "v_access_clean",
                 "Independently re-checks every system rather than trusting the revocation step."),
    ],
)


SOFTWARE_REQUEST = Playbook(
    key="software_request",
    department="it",
    title="Software / License Request",
    description="Someone requests a new tool. Cheap tools provision "
                "immediately; anything above the monthly threshold needs "
                "your sign-off first.",
    required_inputs=[
        {"name": "tool_name", "label": "Tool", "type": "text", "required": True},
        {"name": "monthly_cost", "label": "Monthly cost (USD)", "type": "number", "required": True},
        {"name": "requested_by", "label": "Requested by", "type": "text", "required": False},
    ],
    steps=[
        StepSpec("check_budget_and_vendor", "Checked against budget & vendor policy", "it", A,
                 "check_budget_and_vendor", "v_license_evaluated"),
        StepSpec("provision_license", "License provisioned", "it", A,
                 "provision_license", "v_license_provisioned",
                 classify="classify_license_cost"),
    ],
)


ALL_PLAYBOOKS = [DEVICE_PROVISIONING, ACCESS_REVOCATION, SOFTWARE_REQUEST]
