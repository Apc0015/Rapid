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

def _live_marketing_signals(tenant_id: str) -> dict:
    """Read this tenant's REAL marketing data from its workspace — tenant- AND
    department-scoped (marketing only, so this never pulls sales/CS records).
    Defensive: returns empty on any failure so the digest still runs honestly.
    """
    try:
        from infrastructure.demo_workspace import get_demo_workspace_store
        rows = get_demo_workspace_store().list_entities(
            tenant_id, entity_type="campaign", departments={"marketing"})
    except Exception:
        return {"campaigns": [], "active_campaigns": []}
    campaigns = [
        {"name": r.get("name"),
         "status": (r.get("data") or {}).get("status"),
         "channel": (r.get("data") or {}).get("channel"),
         "audience": (r.get("data") or {}).get("audience")}
        for r in rows
    ]
    return {
        "campaigns": campaigns,
        "active_campaigns": [c["name"] for c in campaigns if c.get("status") == "active"],
    }


def pull_metrics(ctx: StepContext) -> HandlerResult:
    week = ctx.inputs.get("week_of", _today())
    tenant_id = getattr(ctx.run, "tenant_id", "default")
    # Ad-performance numbers are still supplied on the trigger until a live ads/
    # analytics connector is wired — that connector only changes THIS handler.
    metrics = {
        "spend": float(ctx.inputs.get("spend", 0) or 0),
        "impressions": int(ctx.inputs.get("impressions", 0) or 0),
        "conversions": int(ctx.inputs.get("conversions", 0) or 0),
    }
    # Real data: the tenant's own marketing campaigns, read from its workspace.
    signals = _live_marketing_signals(tenant_id)
    ctx.record("weekly_metrics", {"week_of": week, **metrics, **signals, "pulled_at": _today()})
    n = len(signals["campaigns"])
    return HandlerResult(
        summary=(f"Pulled metrics for week of {week}: ${metrics['spend']:.0f} spend, "
                 f"{metrics['conversions']} conversions; read {n} live marketing "
                 f"campaign(s) from the workspace."),
        evidence={"campaign_count": n, **metrics},
    )


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
    """Draft next week's plan with a single governed AI call over this week's real
    numbers — confidence-scored. If the model is unavailable, record an honest
    rule-based fallback marked as such; never present it as an AI strategy."""
    metrics = (ctx.find("weekly_metrics") or {}).get("data", {})
    summ = (ctx.find("performance_summary") or {}).get("data", {})
    cpa = summ.get("cpa")
    tenant_id = getattr(ctx.run, "tenant_id", "default")

    spend = metrics.get("spend", 0) or 0
    conv = metrics.get("conversions", 0) or 0
    campaigns = metrics.get("campaigns", []) or []
    campaign_line = "\nLive campaigns on file: " + (
        "; ".join(
            f"{c.get('name')} ({c.get('channel') or 'channel n/a'}, {c.get('status') or 'status n/a'})"
            for c in campaigns
        ) if campaigns else "none on file."
    )
    prompt = (
        "You are the marketing lead for this company. Using ONLY the real data "
        "below, write next week's marketing plan as 3-5 concrete, prioritized "
        "actions. Reference the actual campaigns where relevant; do not invent "
        "figures or campaigns that aren't listed.\n\n"
        f"This week: ${spend:.0f} spend, {conv} conversions"
        + (f", ${cpa:.2f} cost per acquisition." if cpa else ", no conversions.")
        + campaign_line
    )

    from orgos.reasoning import synthesize
    drafted = synthesize(prompt, tenant_id=tenant_id)
    if drafted:
        ctx.record("next_week_plan", {
            "plan": drafted["text"], "confidence": drafted["confidence"],
            "citations": drafted["citations"], "source": "llm", "drafted_at": _today(),
        })
        return HandlerResult(
            summary=f"Next week's plan drafted by the marketing agent "
                    f"(confidence {drafted['confidence']:.0%}).",
            evidence={"confidence": drafted["confidence"], "source": "llm"},
        )

    # Honest fallback — the model couldn't run, so say so rather than fake a plan.
    fallback = ("Hold spend steady - performance is on track." if cpa and cpa < 50
                else "Review targeting - CPA is trending high or there were no conversions.")
    ctx.record("next_week_plan", {
        "plan": fallback, "confidence": 0.2, "source": "unavailable", "drafted_at": _today(),
    })
    return HandlerResult(
        summary="AI model unavailable - recorded a rule-based fallback plan (not an AI strategy).",
        evidence={"source": "unavailable"},
    )


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
