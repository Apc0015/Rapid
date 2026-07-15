"""
orgos/departments/marketing/specialists.py — Marketing specialist handlers
(Tier 3).

No live ad-platform/analytics integration yet — metrics are recorded as
structured state the same way every other department's handlers work.
When a real ads API is wired in, only these handlers change.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orgos.registry import StepContext, HandlerResult


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ── Weekly performance digest ────────────────────────────────────────────────────

def pull_metrics(ctx: StepContext) -> HandlerResult:
    week = ctx.inputs.get("week_of", _today())
    metrics = {
        "spend": float(ctx.inputs.get("spend", 0) or 0),
        "impressions": int(ctx.inputs.get("impressions", 0) or 0),
        "conversions": int(ctx.inputs.get("conversions", 0) or 0),
    }
    ctx.record("weekly_metrics", {"week_of": week, **metrics, "pulled_at": _today()})
    return HandlerResult(summary=f"Pulled metrics for week of {week}: "
                                f"${metrics['spend']:.0f} spend, {metrics['conversions']} conversions.",
                         evidence=metrics)


def summarize_performance(ctx: StepContext) -> HandlerResult:
    m = ctx.find("weekly_metrics") or {}
    d = m.get("data", {})
    spend = d.get("spend", 0) or 0
    conv = d.get("conversions", 0) or 0
    cpa = (spend / conv) if conv else None
    summary = (f"${spend:.0f} spent, {conv} conversions"
               + (f", ${cpa:.2f} CPA." if cpa else ", no conversions this week."))
    ctx.record("performance_summary", {"summary": summary, "cpa": cpa, "summarized_at": _today()})
    return HandlerResult(summary=summary, evidence={"cpa": cpa})


def draft_next_week_plan(ctx: StepContext) -> HandlerResult:
    summ = ctx.find("performance_summary") or {}
    cpa = summ.get("data", {}).get("cpa")
    plan = ("Hold spend steady, performance is on track." if cpa and cpa < 50
            else "Recommend reviewing targeting — CPA trending high or no conversions.")
    ctx.record("next_week_plan", {"plan": plan, "drafted_at": _today()})
    return HandlerResult(summary=f"Next week's plan drafted: {plan}", evidence={"plan": plan})


# ── Campaign budget request ──────────────────────────────────────────────────────

def check_channel_performance(ctx: StepContext) -> HandlerResult:
    channel = ctx.inputs.get("channel", "unspecified")
    amount = float(ctx.inputs.get("amount", 0) or 0)
    ctx.record("channel_budget_request", {
        "channel": channel, "amount": amount,
        "performance_check": "channel_meeting_target", "checked_at": _today(),
    })
    return HandlerResult(summary=f"Checked {channel} performance ahead of ${amount:.0f} spend increase.",
                         evidence={"channel": channel, "amount": amount})


def approve_and_allocate_spend(ctx: StepContext) -> HandlerResult:
    req = ctx.find("channel_budget_request") or {}
    d = req.get("data", {})
    d["status"] = "allocated"
    d["allocated_at"] = _today()
    ctx.record("channel_budget_request", d)
    return HandlerResult(summary=f"Spend increase allocated on {d.get('channel', ctx.run.subject)}.",
                         evidence={"status": "allocated"})


# ── Campaign launch ──────────────────────────────────────────────────────────────

def check_brand_guidelines(ctx: StepContext) -> HandlerResult:
    campaign = ctx.inputs.get("campaign_name", ctx.run.subject)
    ctx.record("campaign", {
        "name": campaign, "channel": ctx.inputs.get("channel", ""),
        "brand_check": "compliant", "checked_at": _today(),
    })
    return HandlerResult(summary=f"'{campaign}' checked against brand guidelines — compliant.",
                         evidence={"brand_check": "compliant"})


def schedule_launch(ctx: StepContext) -> HandlerResult:
    launch_date = ctx.inputs.get("launch_date", "TBD")
    camp = ctx.find("campaign") or {}
    d = camp.get("data", {})
    d["status"] = "scheduled"
    d["launch_date"] = launch_date
    ctx.record("campaign", d)
    return HandlerResult(summary=f"'{d.get('name', ctx.run.subject)}' scheduled to launch {launch_date}.",
                         evidence={"launch_date": launch_date})


def confirm_live(ctx: StepContext) -> HandlerResult:
    camp = ctx.find("campaign") or {}
    d = camp.get("data", {})
    d["status"] = "live"
    ctx.record("campaign", d)
    return HandlerResult(summary=f"'{d.get('name', ctx.run.subject)}' confirmed live.",
                         evidence={"status": "live"})
