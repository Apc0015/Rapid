"""orgos/departments/marketing — the Marketing department, as a plug-in to the org core."""

from __future__ import annotations

from orgos.departments.marketing import specialists as S
from orgos.departments.marketing import verifiers as V
from orgos.departments.marketing import classifiers as C
from orgos.departments.marketing.playbooks import ALL_PLAYBOOKS


def register(reg) -> None:
    for pb in ALL_PLAYBOOKS:
        reg.register_playbook(pb)

    handlers = {
        "pull_metrics": S.pull_metrics,
        "summarize_performance": S.summarize_performance,
        "draft_next_week_plan": S.draft_next_week_plan,
        "check_channel_performance": S.check_channel_performance,
        "approve_and_allocate_spend": S.approve_and_allocate_spend,
        "check_brand_guidelines": S.check_brand_guidelines,
        "schedule_launch": S.schedule_launch,
        "confirm_live": S.confirm_live,
    }
    for name, fn in handlers.items():
        reg.register_handler(name, fn)

    verifies = {
        "v_metrics_pulled": V.v_metrics_pulled,
        "v_performance_summarized": V.v_performance_summarized,
        "v_plan_drafted": V.v_plan_drafted,
        "v_channel_checked": V.v_channel_checked,
        "v_spend_allocated": V.v_spend_allocated,
        "v_brand_checked": V.v_brand_checked,
        "v_launch_scheduled": V.v_launch_scheduled,
        "v_confirmed_live": V.v_confirmed_live,
    }
    for name, fn in verifies.items():
        reg.register_verify(name, fn)

    reg.register_classifier("classify_spend_amount", C.classify_spend_amount)
