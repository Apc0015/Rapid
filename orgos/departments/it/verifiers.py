"""
orgos/departments/it/verifiers.py — IT verification checks (Tier 4 logic).

Independent of the handlers in specialists.py — reads the system of record
back and confirms the state actually exists.
"""

from __future__ import annotations

from orgos.registry import StepContext, VerifyResult


def _fail(detail: str) -> VerifyResult:
    return VerifyResult(ok=False, detail=detail)


def _ok(detail: str, found: dict) -> VerifyResult:
    return VerifyResult(ok=True, detail=detail, found=found)


def v_equipment_ordered(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("equipment")
    if not rec or rec["data"].get("status") not in ("ordered", "active"):
        return _fail("No equipment order on record.")
    return _ok(f"{rec['data'].get('item')} confirmed ordered.", {"item": rec["data"].get("item")})


def v_it_accounts_provisioned(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("it_accounts")
    systems = (rec or {}).get("data", {}).get("systems", {})
    missing = [s for s, st in systems.items() if st != "provisioned"]
    if not systems or missing:
        return _fail(f"IT accounts not fully provisioned (missing: {missing or 'all'}).")
    return _ok(f"All {len(systems)} IT accounts provisioned.", {"systems": list(systems.keys())})


def v_security_configured(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("security_policy")
    if not rec or not rec["data"].get("policy"):
        return _fail("No security policy applied.")
    return _ok(f"Security policy '{rec['data']['policy']}' confirmed applied.",
               {"policy": rec["data"]["policy"]})


def v_it_active(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("equipment")
    if not rec or rec["data"].get("status") != "active":
        return _fail("Setup not confirmed active.")
    return _ok("Confirmed active.", {"status": "active"})


def v_it_accounts_revoked(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("it_accounts")
    systems = (rec or {}).get("data", {}).get("systems", {})
    still_active = [s for s, st in systems.items() if st != "revoked"]
    if not systems or still_active:
        return _fail(f"Access not fully revoked (still active: {still_active or 'all'}).")
    return _ok(f"Access revoked across {len(systems)} systems.", {"systems": list(systems.keys())})


def v_device_reclaim_scheduled(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("equipment")
    if not rec or rec["data"].get("status") != "reclaim_scheduled":
        return _fail("Device reclaim not scheduled.")
    return _ok("Device reclaim scheduled.", {"status": "reclaim_scheduled"})


def v_access_clean(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("access_audit")
    if not rec or not rec["data"].get("all_revoked"):
        return _fail("Access audit did not confirm all systems revoked.")
    return _ok("Independent audit confirms zero lingering access.",
               {"systems_checked": rec["data"].get("systems_checked")})


def v_license_evaluated(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("license_request")
    if not rec or "vendor_check" not in rec["data"]:
        return _fail("License request not evaluated against budget/vendor policy.")
    return _ok("Evaluated against budget and vendor policy.",
               {"monthly_cost": rec["data"].get("monthly_cost")})


def v_license_provisioned(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("license_request")
    if not rec or rec["data"].get("status") != "provisioned":
        return _fail("License not provisioned.")
    return _ok(f"License for '{rec['data'].get('tool')}' confirmed provisioned.",
               {"tool": rec["data"].get("tool")})
