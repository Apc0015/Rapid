"""
orgos/engine.py — The organization's loop engine.

Every unit of work moves through one fixed loop, and this module is the only
thing that drives it:

    Trigger  → a run is created from a playbook (the department lead plans it)
    Plan     → the playbook is expanded into ordered, classified steps
    Execute  → each A_auto step runs its specialist handler
    Verify   → the Verifier independently confirms it against real state
    Log      → every transition appends to the immutable audit ledger
    Reflect  → a one-line digest is produced for the founder

The human-in-the-loop gate is not a step you can forget to add — it is
structural. The moment the loop reaches a B_approve or C_human step it stops,
raises an Escalation, and refuses to proceed until a human decides. Only
A_auto work ever runs unattended.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from orgos.models import (
    TaskRun, RunStep, Escalation, AuditEntry,
    Autonomy, RunStatus, StepStatus, EscalationStatus,
)
from orgos.registry import StepContext, HandlerResult, get_registry
from orgos.store import OrgStore, get_store
from orgos.verifier import get_verifier, VERIFIER_ACTOR

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Engine:
    def __init__(self, store: Optional[OrgStore] = None):
        self.store = store or get_store()
        self.registry = get_registry()
        self.verifier = get_verifier()

    # ── Trigger + Plan ─────────────────────────────────────────────────────────

    def create_run(self, department: str, playbook_key: str, subject: str,
                   trigger_type: str, payload: dict, created_by: str,
                   title: Optional[str] = None,
                   parent_run_id: Optional[str] = None,
                   mesh_group_id: Optional[str] = None) -> TaskRun:
        pb = self.registry.playbook(playbook_key)
        if pb is None or pb.department != department:
            raise ValueError(f"Unknown playbook '{playbook_key}' for department '{department}'")

        run = TaskRun.new(
            department=department,
            playbook=playbook_key,
            title=title or f"{pb.title} — {subject}",
            subject=subject,
            trigger_type=trigger_type,
            trigger_payload=payload or {},
            created_by=created_by,
            parent_run_id=parent_run_id,
            mesh_group_id=mesh_group_id,
        )
        run.assigned_lead = f"{department}-lead"

        # PLAN: expand the playbook into live, classified steps.
        # A step's autonomy is normally the playbook's static default. If the
        # step declares a classifier, its REAL tier is computed here from the
        # run's actual trigger data (e.g. "auto under $500, approval over") —
        # resolved once, from live inputs, never left as an unenforced label.
        for i, spec in enumerate(pb.steps):
            autonomy = spec.autonomy
            escalate_reason = spec.escalate_reason
            if spec.classify:
                clf = self.registry.classifier(spec.classify)
                if clf is None:
                    raise ValueError(f"No classifier registered under '{spec.classify}'")
                resolved, reason = clf(run.trigger_payload)
                autonomy = resolved
                if reason:
                    escalate_reason = reason
            run.steps.append(RunStep(
                step_id=f"{run.run_id}_s{i}",
                run_id=run.run_id,
                seq=i,
                key=spec.key,
                title=spec.title,
                owner=spec.owner,
                autonomy=autonomy.value,
                handler=spec.handler,
                verify=spec.verify,
                description=spec.description,
                escalate_reason=escalate_reason,
            ))

        run.status = RunStatus.PLANNED.value
        self.store.save_run(run)
        self._audit(run, f"{department}-lead", "run.triggered",
                    f"Triggered via {trigger_type}: {run.title}")
        self._audit(run, f"{department}-lead", "run.planned",
                    f"Planned {len(run.steps)} steps from playbook '{playbook_key}'")
        return run

    # ── Execute + Verify loop ──────────────────────────────────────────────────

    def advance(self, run_id: str, single_step: bool = False) -> TaskRun:
        """
        Drive the run forward. Runs A_auto steps (execute → verify) in order.
        Stops when it reaches a human gate (escalation), a failure, or the end.
        If single_step is True, performs exactly one step then returns.
        """
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        if run.status in (RunStatus.DONE.value, RunStatus.ESCALATED.value,
                          RunStatus.FAILED.value):
            return run

        run.status = RunStatus.EXECUTING.value
        self.store.update_run(run)

        for step in run.steps:
            if step.status in (StepStatus.VERIFIED.value, StepStatus.SKIPPED.value):
                continue
            if step.status == StepStatus.ESCALATED.value:
                # already waiting on a human — do not proceed past the gate
                run.status = RunStatus.ESCALATED.value
                self.store.update_run(run)
                return run

            # Human-in-the-loop gate: B/C steps never run unattended.
            if step.autonomy != Autonomy.A_AUTO.value:
                self._raise_escalation(run, step)
                return run

            ok = self._execute_and_verify(run, step)
            if not ok:
                run.status = RunStatus.FAILED.value
                run.digest_line = f"{run.title}: FAILED at '{step.title}' — {step.error or 'verification failed'}"
                self.store.update_run(run)
                self._audit(run, "hr-lead", "run.failed", run.digest_line, step.step_id)
                return run

            if single_step:
                # leave the run in a resumable state
                remaining = [s for s in run.steps
                             if s.status not in (StepStatus.VERIFIED.value, StepStatus.SKIPPED.value)]
                run.status = RunStatus.EXECUTING.value if remaining else RunStatus.DONE.value
                if not remaining:
                    self._finish(run)
                else:
                    self.store.update_run(run)
                return self.store.get_run(run_id)

        # All steps resolved → done.
        self._finish(run)
        return self.store.get_run(run_id)

    def _execute_and_verify(self, run: TaskRun, step: RunStep) -> bool:
        # EXECUTE — specialist runs the step.
        step.status = StepStatus.EXECUTING.value
        step.started_at = _now()
        self.store.update_step(step)

        handler = self.registry.handler(step.handler)
        ctx = StepContext(run=run, step=step, store=self.store, inputs=run.trigger_payload)
        if handler is None:
            step.status = StepStatus.FAILED.value
            step.error = f"No handler registered under '{step.handler}'"
            step.finished_at = _now()
            self.store.update_step(step)
            return False
        try:
            result = handler(ctx)
            if not isinstance(result, HandlerResult):
                raise TypeError("handler did not return a HandlerResult")
        except Exception as e:
            logger.exception("Handler '%s' failed", step.handler)
            step.status = StepStatus.FAILED.value
            step.error = f"Handler errored: {e!r}"
            step.finished_at = _now()
            self.store.update_step(step)
            return False

        step.evidence = result.evidence
        step.result_summary = result.summary
        step.status = StepStatus.EXECUTED.value
        self.store.update_step(step)
        self._audit(run, f"{step.owner}-specialist", "step.executed",
                    result.summary, step.step_id)

        # VERIFY — the Verifier independently confirms it. The specialist has
        # no say in this; a different callable checks real recorded state.
        run.status = RunStatus.VERIFYING.value
        self.store.update_run(run)
        vres = self.verifier.verify_step(ctx)
        step.verify_result = {"ok": vres.ok, "detail": vres.detail, "found": vres.found}
        step.finished_at = _now()

        if vres.ok:
            step.status = StepStatus.VERIFIED.value
            step.verified_by = VERIFIER_ACTOR
            self.store.update_step(step)
            self._audit(run, VERIFIER_ACTOR, "step.verified", vres.detail, step.step_id)
            return True

        step.status = StepStatus.FAILED.value
        step.error = f"Verification failed: {vres.detail}"
        self.store.update_step(step)
        self._audit(run, VERIFIER_ACTOR, "step.verify_failed", vres.detail, step.step_id)
        return False

    # ── Escalation (the human-in-the-loop gate) ────────────────────────────────

    def _raise_escalation(self, run: TaskRun, step: RunStep) -> None:
        step.status = StepStatus.ESCALATED.value
        self.store.update_step(step)
        esc = Escalation.new(run, step)
        self.store.save_escalation(esc)
        run.status = RunStatus.ESCALATED.value
        run.digest_line = f"{run.title}: waiting on your decision — {step.title}"
        self.store.update_run(run)
        self._audit(run, "hr-lead", "run.escalated",
                    f"Paused at '{step.title}' ({step.autonomy}): {esc.reason}", step.step_id)

    def decide_escalation(self, escalation_id: str, approved: bool,
                          decided_by: str, note: str = "") -> TaskRun:
        esc = self.store.get_escalation(escalation_id)
        if esc is None:
            raise ValueError(f"Escalation {escalation_id} not found")
        if esc.status != EscalationStatus.PENDING.value:
            return self.store.get_run(esc.run_id)

        esc.status = EscalationStatus.APPROVED.value if approved else EscalationStatus.REJECTED.value
        esc.decided_by = decided_by
        esc.decided_at = _now()
        esc.decision_note = note
        self.store.update_escalation(esc)

        run = self.store.get_run(esc.run_id)
        step = next((s for s in run.steps if s.step_id == esc.step_id), None)
        actor = f"founder:{decided_by}"

        if not approved:
            # Declined: do not perform this action, and stop the run safely.
            if step:
                step.status = StepStatus.SKIPPED.value
                step.result_summary = f"Declined by {decided_by}. {note}".strip()
                self.store.update_step(step)
            run.status = RunStatus.DONE.value
            run.digest_line = f"{run.title}: stopped — you declined '{step.title if step else 'the action'}'. No further action taken."
            self.store.update_run(run)
            self._audit(run, actor, "run.declined", run.digest_line, esc.step_id)
            return self.store.get_run(esc.run_id)

        # Approved: the gated step is now cleared to execute like an auto step.
        self._audit(run, actor, "escalation.approved",
                    f"Approved '{step.title if step else esc.title}'. {note}".strip(), esc.step_id)
        if step:
            ok = self._execute_and_verify(run, step)
            if not ok:
                run.status = RunStatus.FAILED.value
                run.digest_line = f"{run.title}: FAILED at '{step.title}' after approval — {step.error}"
                self.store.update_run(run)
                self._audit(run, "hr-lead", "run.failed", run.digest_line, step.step_id)
                return self.store.get_run(esc.run_id)

        # Continue the loop past the now-cleared gate.
        return self.advance(esc.run_id)

    # ── Reflect / finish ───────────────────────────────────────────────────────

    def _finish(self, run: TaskRun) -> None:
        run.status = RunStatus.DONE.value
        done, total = run.progress()
        run.digest_line = self._digest_for(run, done, total)
        self.store.update_run(run)
        self._audit(run, "hr-lead", "run.done", run.digest_line)

    def _digest_for(self, run: TaskRun, done: int, total: int) -> str:
        # Report human touches honestly: count decided escalations on this run.
        decided = [e for e in self.store.list_escalations(department=run.department)
                   if e.run_id == run.run_id
                   and e.status != EscalationStatus.PENDING.value]
        n = len(decided)
        touches = "0 touches from you" if n == 0 else (
            f"{n} decision{'s' if n != 1 else ''} from you")
        base = f"{run.subject}: {run.playbook} complete — {done}/{total} steps verified"
        return f"{base}, {touches}."

    # ── audit helper ───────────────────────────────────────────────────────────

    def _audit(self, run: TaskRun, actor: str, event: str, detail: str,
               step_id: Optional[str] = None) -> None:
        self.store.append_audit(
            AuditEntry.new(run_id=run.run_id, department=run.department,
                           actor=actor, event=event, detail=detail, step_id=step_id)
        )


_engine: Optional[Engine] = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine
