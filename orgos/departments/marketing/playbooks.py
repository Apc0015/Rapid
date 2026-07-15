"""
orgos/departments/marketing/playbooks.py — what the Marketing department
knows how to do.

Weekly digest and campaign launch are informational/creative ops, not
money-gated — fully A_auto. Spend increases are dynamically classified by
amount, same pattern as IT's license request and Finance's budget request.
"""

from __future__ import annotations

from orgos.models import Playbook, StepSpec, Autonomy

A = Autonomy.A_AUTO


WEEKLY_DIGEST = Playbook(
    key="weekly_digest",
    department="marketing",
    title="Weekly Performance Digest",
    description="Every Monday: pull the numbers, say what happened, draft "
                "next week's plan. The founder gets the readout, not the job "
                "of building the deck.",
    required_inputs=[
        {"name": "week_of", "label": "Week of", "type": "date", "required": False},
        {"name": "spend", "label": "Spend (USD)", "type": "number", "required": False},
        {"name": "impressions", "label": "Impressions", "type": "number", "required": False},
        {"name": "conversions", "label": "Conversions", "type": "number", "required": False},
    ],
    steps=[
        StepSpec("pull_metrics", "Metrics pulled", "marketing", A,
                 "pull_metrics", "v_metrics_pulled"),
        StepSpec("summarize", "Performance summarized", "marketing", A,
                 "summarize_performance", "v_performance_summarized"),
        StepSpec("draft_plan", "Next week's plan drafted", "marketing", A,
                 "draft_next_week_plan", "v_plan_drafted"),
    ],
)


CAMPAIGN_BUDGET_REQUEST = Playbook(
    key="campaign_budget_request",
    department="marketing",
    title="Campaign Budget Request",
    description="Marketing wants to increase spend on a channel that's "
                "performing. Small increases clear automatically; larger "
                "ones need your sign-off.",
    required_inputs=[
        {"name": "channel", "label": "Channel", "type": "text", "required": True},
        {"name": "amount", "label": "Increase amount (USD)", "type": "number", "required": True},
    ],
    steps=[
        StepSpec("check_performance", "Channel performance checked", "marketing", A,
                 "check_channel_performance", "v_channel_checked"),
        StepSpec("allocate_spend", "Spend increase allocated", "marketing", A,
                 "approve_and_allocate_spend", "v_spend_allocated",
                 classify="classify_spend_amount"),
    ],
)


CAMPAIGN_LAUNCH = Playbook(
    key="campaign_launch",
    department="marketing",
    title="Campaign Launch",
    description="A new campaign or piece of content is ready to go live — "
                "checked against brand guidelines, scheduled, confirmed live.",
    required_inputs=[
        {"name": "channel", "label": "Channel", "type": "text", "required": True},
        {"name": "launch_date", "label": "Launch date", "type": "date", "required": True},
    ],
    steps=[
        StepSpec("check_brand", "Brand guidelines checked", "marketing", A,
                 "check_brand_guidelines", "v_brand_checked"),
        StepSpec("schedule", "Launch scheduled", "marketing", A,
                 "schedule_launch", "v_launch_scheduled"),
        StepSpec("confirm_live", "Confirmed live", "marketing", A,
                 "confirm_live", "v_confirmed_live"),
    ],
)


ALL_PLAYBOOKS = [WEEKLY_DIGEST, CAMPAIGN_BUDGET_REQUEST, CAMPAIGN_LAUNCH]
