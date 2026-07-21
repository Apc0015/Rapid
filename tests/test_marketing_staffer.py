"""
tests/test_marketing_staffer.py — the Marketing AI staffer's behaviour.

 - It drafts next week's plan through a single governed call, and when the model
   is available records it as an AI plan with a confidence score.
 - When the model is unavailable it degrades HONESTLY: it records a rule-based
   fallback marked as such, never a fabricated AI strategy.
 - "Going live" is consequential, so it STOPS for human approval before it
   publishes — it never ships a campaign on its own.

Runs against a fresh temp orgos store; no live model is needed (the synthesis
call is stubbed so both the available and unavailable paths are deterministic).
"""
import pytest

from orgos.store import OrgStore
from orgos.engine import Engine
from orgos.models import RunStatus


@pytest.fixture
def engine(tmp_path):
    return Engine(store=OrgStore(str(tmp_path / "orgos.db")))


@pytest.fixture(autouse=True)
def _isolated_workspace(tmp_path, monkeypatch):
    """Point the workspace store at a throwaway DB so the agent's campaign reads
    (and the demo auto-seed they trigger) never touch the shared workspace DB."""
    from infrastructure.demo_workspace import DemoWorkspaceStore
    store = DemoWorkspaceStore(str(tmp_path / "workspace.db"))
    monkeypatch.setattr("infrastructure.demo_workspace.get_demo_workspace_store", lambda: store)


def _weekly(engine, subject, tenant="tenant-a"):
    run = engine.create_run(
        department="marketing", playbook_key="weekly_digest", subject=subject,
        trigger_type="manual", payload={"spend": 400, "conversions": 8},
        created_by="t", tenant_id=tenant,
    )
    return engine.advance(run.run_id)


def test_plan_degrades_honestly_when_model_unavailable(engine, monkeypatch):
    monkeypatch.setattr("orgos.reasoning.synthesize", lambda *a, **k: None)
    run = _weekly(engine, "Week 1")
    # The run still completes — a plan is on file ...
    assert run.status == RunStatus.DONE.value
    plan = engine.store.find_record("marketing", "next_week_plan", "Week 1", tenant_id="tenant-a")
    # ... but it is HONESTLY marked as a fallback, not passed off as an AI plan.
    assert plan["data"]["source"] == "unavailable"
    assert plan["data"]["plan"]


def test_plan_uses_governed_synthesis_when_available(engine, monkeypatch):
    monkeypatch.setattr(
        "orgos.reasoning.synthesize",
        lambda *a, **k: {"text": "1) Double down on paid search. 2) Test lookalike audiences.",
                         "confidence": 0.82, "citations": []},
    )
    run = _weekly(engine, "Week 2")
    assert run.status == RunStatus.DONE.value
    plan = engine.store.find_record("marketing", "next_week_plan", "Week 2", tenant_id="tenant-a")
    assert plan["data"]["source"] == "llm"
    assert plan["data"]["confidence"] == 0.82
    assert "paid search" in plan["data"]["plan"]


def test_going_live_stops_for_human_approval(engine):
    run = engine.create_run(
        department="marketing", playbook_key="campaign_launch", subject="Spring Launch",
        trigger_type="manual", payload={"channel": "email", "launch_date": "2026-08-01"},
        created_by="t", tenant_id="tenant-a",
    )
    run = engine.advance(run.run_id)

    # It pauses before publishing — it does NOT go live on its own.
    assert run.status == RunStatus.ESCALATED.value
    escs = engine.store.list_escalations(department="marketing", status="pending", tenant_id="tenant-a")
    assert len(escs) == 1
    camp = engine.store.find_record("marketing", "campaign", "Spring Launch", tenant_id="tenant-a")
    assert camp["data"]["status"] == "scheduled"  # scheduled, not live

    # A human approves → it goes live and the run completes.
    run = engine.decide_escalation(escs[0].escalation_id, approved=True, decided_by="founder")
    assert run.status == RunStatus.DONE.value
    camp = engine.store.find_record("marketing", "campaign", "Spring Launch", tenant_id="tenant-a")
    assert camp["data"]["status"] == "live"


def test_pull_metrics_reads_real_marketing_campaigns(engine):
    run = engine.create_run(
        department="marketing", playbook_key="weekly_digest", subject="Week 5",
        trigger_type="manual", payload={"spend": 100, "conversions": 3},
        created_by="t", tenant_id="tenant-a",
    )
    engine.advance(run.run_id)
    rec = engine.store.find_record("marketing", "weekly_metrics", "Week 5", tenant_id="tenant-a")

    # The agent read the tenant's REAL marketing campaigns from its workspace —
    # not just the hand-fed ad numbers — and only marketing ones (dept-scoped).
    campaigns = rec["data"]["campaigns"]
    assert isinstance(campaigns, list) and len(campaigns) >= 1
    assert any("Operations Intelligence" in (c.get("name") or "") for c in campaigns)


def test_marketing_read_is_department_scoped(engine):
    # The seeded workspace also holds sales leads/deals (Asteron, Beacon). The
    # marketing agent must read marketing campaigns ONLY — never the sales
    # pipeline. This is the governance boundary on "real data in".
    from orgos.departments.marketing.specialists import _live_marketing_signals
    signals = _live_marketing_signals("tenant-a")
    names = [c.get("name") or "" for c in signals["campaigns"]]
    assert any("Operations Intelligence" in n for n in names)          # marketing: present
    assert not any(("Asteron" in n) or ("expansion" in n) for n in names)  # sales: absent


def test_declining_go_live_never_publishes(engine):
    run = engine.create_run(
        department="marketing", playbook_key="campaign_launch", subject="Risky Launch",
        trigger_type="manual", payload={"channel": "email", "launch_date": "2026-08-01"},
        created_by="t", tenant_id="tenant-a",
    )
    engine.advance(run.run_id)
    escs = engine.store.list_escalations(department="marketing", status="pending", tenant_id="tenant-a")

    # A human declines → the campaign never goes live.
    run = engine.decide_escalation(escs[0].escalation_id, approved=False, decided_by="founder",
                                   note="Hold — legal review pending.")
    camp = engine.store.find_record("marketing", "campaign", "Risky Launch", tenant_id="tenant-a")
    assert camp["data"]["status"] != "live"
