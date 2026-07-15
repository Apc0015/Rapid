"""orgos/departments/it — the IT department, as a plug-in to the org core."""

from __future__ import annotations

from orgos.departments.it import specialists as S
from orgos.departments.it import verifiers as V
from orgos.departments.it import classifiers as C
from orgos.departments.it.playbooks import ALL_PLAYBOOKS


def register(reg) -> None:
    for pb in ALL_PLAYBOOKS:
        reg.register_playbook(pb)

    handlers = {
        "order_equipment": S.order_equipment,
        "provision_it_accounts": S.provision_it_accounts,
        "configure_security_policy": S.configure_security_policy,
        "confirm_it_active": S.confirm_it_active,
        "revoke_it_accounts": S.revoke_it_accounts,
        "reclaim_device": S.reclaim_device,
        "confirm_access_clean": S.confirm_access_clean,
        "check_budget_and_vendor": S.check_budget_and_vendor,
        "provision_license": S.provision_license,
    }
    for name, fn in handlers.items():
        reg.register_handler(name, fn)

    verifies = {
        "v_equipment_ordered": V.v_equipment_ordered,
        "v_it_accounts_provisioned": V.v_it_accounts_provisioned,
        "v_security_configured": V.v_security_configured,
        "v_it_active": V.v_it_active,
        "v_it_accounts_revoked": V.v_it_accounts_revoked,
        "v_device_reclaim_scheduled": V.v_device_reclaim_scheduled,
        "v_access_clean": V.v_access_clean,
        "v_license_evaluated": V.v_license_evaluated,
        "v_license_provisioned": V.v_license_provisioned,
    }
    for name, fn in verifies.items():
        reg.register_verify(name, fn)

    reg.register_classifier("classify_license_cost", C.classify_license_cost)
