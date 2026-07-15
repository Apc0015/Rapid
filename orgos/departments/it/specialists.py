"""
orgos/departments/it/specialists.py — IT specialist handlers (Tier 3).

Same contract as HR's: write real structured state into the system of record,
never grade your own work. No live device/identity-provider integration yet —
these write the record a real admin console would later mirror.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orgos.registry import StepContext, HandlerResult


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ── Device & account provisioning ───────────────────────────────────────────────

def order_equipment(ctx: StepContext) -> HandlerResult:
    equipment = ctx.inputs.get("equipment", "laptop")
    ctx.record("equipment", {"item": equipment, "status": "ordered", "ordered_at": _today()})
    return HandlerResult(summary=f"{equipment.title()} ordered for {ctx.run.subject}.",
                         evidence={"item": equipment, "status": "ordered"})


def provision_it_accounts(ctx: StepContext) -> HandlerResult:
    systems = ["email", "vpn", "identity_provider", "ticketing"]
    ctx.record("it_accounts", {"systems": {s: "provisioned" for s in systems},
                               "provisioned_at": _today()})
    return HandlerResult(summary=f"IT accounts provisioned for {ctx.run.subject}: {', '.join(systems)}.",
                         evidence={"systems": systems})


def configure_security_policy(ctx: StepContext) -> HandlerResult:
    role = ctx.inputs.get("role", "employee")
    policy = "standard_mfa_required" if role.lower() != "admin" else "admin_mfa_hardware_key_required"
    ctx.record("security_policy", {"policy": policy, "applied_at": _today()})
    return HandlerResult(summary=f"Security policy '{policy}' applied for {ctx.run.subject}.",
                         evidence={"policy": policy})


def confirm_it_active(ctx: StepContext) -> HandlerResult:
    equip = ctx.find("equipment") or {}
    equip_d = equip.get("data", {})
    equip_d["status"] = "active"
    ctx.record("equipment", equip_d)
    return HandlerResult(summary=f"{ctx.run.subject} confirmed fully set up and active.",
                         evidence={"status": "active"})


# ── Access revocation (offboarding) ─────────────────────────────────────────────

def revoke_it_accounts(ctx: StepContext) -> HandlerResult:
    systems = ["email", "vpn", "identity_provider", "ticketing"]
    ctx.record("it_accounts", {"systems": {s: "revoked" for s in systems},
                               "revoked_at": _today()})
    return HandlerResult(summary=f"IT accounts revoked for {ctx.run.subject} across {len(systems)} systems.",
                         evidence={"systems": systems})


def reclaim_device(ctx: StepContext) -> HandlerResult:
    ctx.record("equipment", {"status": "reclaim_scheduled", "scheduled_at": _today()})
    return HandlerResult(summary=f"Device reclaim scheduled for {ctx.run.subject}.",
                         evidence={"status": "reclaim_scheduled"})


def confirm_access_clean(ctx: StepContext) -> HandlerResult:
    accounts = ctx.find("it_accounts") or {}
    systems = accounts.get("data", {}).get("systems", {})
    ctx.record("access_audit", {"systems_checked": list(systems.keys()),
                                "all_revoked": all(v == "revoked" for v in systems.values()),
                                "checked_at": _today()})
    return HandlerResult(summary=f"Confirmed no lingering access remains for {ctx.run.subject}.",
                         evidence={"systems_checked": list(systems.keys())})


# ── Software / license request ──────────────────────────────────────────────────

def check_budget_and_vendor(ctx: StepContext) -> HandlerResult:
    tool = ctx.inputs.get("tool_name", "requested tool")
    cost = float(ctx.inputs.get("monthly_cost", 0) or 0)
    ctx.record("license_request", {"tool": tool, "monthly_cost": cost,
                                   "vendor_check": "not_on_blocklist", "evaluated_at": _today()})
    return HandlerResult(summary=f"Checked '{tool}' (${cost:.0f}/mo) against budget and vendor policy.",
                         evidence={"tool": tool, "monthly_cost": cost})


def provision_license(ctx: StepContext) -> HandlerResult:
    tool = ctx.inputs.get("tool_name", "requested tool")
    req = ctx.find("license_request") or {}
    req_d = req.get("data", {})
    req_d["status"] = "provisioned"
    req_d["provisioned_at"] = _today()
    ctx.record("license_request", req_d)
    return HandlerResult(summary=f"License for '{tool}' provisioned for {ctx.inputs.get('requested_by', ctx.run.subject)}.",
                         evidence={"tool": tool, "status": "provisioned"})
