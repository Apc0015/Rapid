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
