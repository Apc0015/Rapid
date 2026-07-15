"""
orgos/departments/marketing/verifiers.py — Marketing verification checks (Tier 4).
"""

from __future__ import annotations

from orgos.registry import StepContext, VerifyResult


def _fail(detail: str) -> VerifyResult:
    return VerifyResult(ok=False, detail=detail)


def _ok(detail: str, found: dict) -> VerifyResult:
    return VerifyResult(ok=True, detail=detail, found=found)


def v_metrics_pulled(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("weekly_metrics")
    if not rec or "spend" not in rec["data"]:
        return _fail("Weekly metrics not pulled.")
    return _ok(f"Metrics on file for week of {rec['data'].get('week_of')}.",
               {"week_of": rec["data"].get("week_of")})


def v_performance_summarized(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("performance_summary")
    if not rec or not rec["data"].get("summary"):
        return _fail("Performance not summarized.")
    return _ok("Performance summary on file.", {"summary": rec["data"]["summary"]})


def v_plan_drafted(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("next_week_plan")
    if not rec or not rec["data"].get("plan"):
        return _fail("Next week's plan not drafted.")
    return _ok("Next week's plan on file.", {"plan": rec["data"]["plan"]})


def v_channel_checked(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("channel_budget_request")
    if not rec or not rec["data"].get("performance_check"):
        return _fail("Channel performance not checked.")
    return _ok(f"Channel check: {rec['data']['performance_check']}.",
               {"amount": rec["data"].get("amount")})


def v_spend_allocated(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("channel_budget_request")
    if not rec or rec["data"].get("status") != "allocated":
        return _fail("Spend increase not allocated.")
    return _ok("Spend allocation confirmed.", {"status": "allocated"})


def v_brand_checked(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("campaign")
    if not rec or rec["data"].get("brand_check") != "compliant":
        return _fail("Campaign not checked against brand guidelines.")
    return _ok("Brand guideline check confirmed compliant.", {"brand_check": "compliant"})


def v_launch_scheduled(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("campaign")
    if not rec or rec["data"].get("status") != "scheduled":
        return _fail("Launch not scheduled.")
    return _ok(f"Launch scheduled for {rec['data'].get('launch_date')}.",
               {"launch_date": rec["data"].get("launch_date")})


def v_confirmed_live(ctx: StepContext) -> VerifyResult:
    rec = ctx.find("campaign")
    if not rec or rec["data"].get("status") != "live":
        return _fail("Campaign not confirmed live.")
    return _ok("Campaign confirmed live.", {"status": "live"})
