"""
orgos/models.py — Core data model for the RAPID digital organization.

These types are DEPARTMENT-AGNOSTIC. HR, Finance, IT, etc. all reuse them.
A department only supplies Playbooks (what work looks like) and Specialists
(who does each step) — never its own copy of the run machinery.

The central primitive is the Task Run: one execution of a Playbook that moves
through a fixed loop —

    triggered → planned → executing → verifying → (done | escalated | failed)

Nothing is ever "done" because a specialist said so. A step becomes VERIFIED
only after an independent check against real recorded state (see verifier.py),
and a run becomes DONE only when every step is verified.

Autonomy is tiered by consequence, not blanket (the "human-in-the-loop" rule):

    A_auto     — low-stakes, reversible, informational → executes automatically
    B_approve  — agent recommends, a human approves before it runs
    C_human    — a human decides; the agent only executes the mechanics

A_auto steps flow through untouched. B/C steps pause the run and raise an
Escalation — that pause IS the human-in-the-loop gate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ── Enums ─────────────────────────────────────────────────────────────────────

class Autonomy(str, Enum):
    """How much human involvement a step requires, by consequence."""
    A_AUTO = "A_auto"        # execute automatically, just log it
    B_APPROVE = "B_approve"  # recommend, human approves before execution
    C_HUMAN = "C_human"      # human decides; agent executes mechanics only


class RunStatus(str, Enum):
    TRIGGERED = "triggered"
    PLANNED = "planned"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    DONE = "done"
    ESCALATED = "escalated"
    FAILED = "failed"


class StepStatus(str, Enum):
    PENDING = "pending"          # not started
    EXECUTING = "executing"      # handler running
    EXECUTED = "executed"        # handler finished, awaiting verification
    VERIFIED = "verified"        # independently confirmed against real state
    ESCALATED = "escalated"      # paused, waiting on a human decision
    FAILED = "failed"            # handler or verification failed
    SKIPPED = "skipped"          # not applicable for this run


class EscalationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ── Step definition (static, from a Playbook) ──────────────────────────────────

@dataclass
class StepSpec:
    """
    The static definition of one step inside a Playbook.

    key         — stable machine identifier, unique within the playbook
    title       — human-facing label ("Offer letter generated")
    owner       — which specialist runs it ("onboarding", "compliance", ...)
    autonomy    — A_auto | B_approve | C_human — the DEFAULT tier, used as-is
                  unless `classify` is set
    handler     — name of the registered specialist handler that executes it
    verify      — name of the registered verify check (independent of handler)
    description — optional longer explanation shown in the run detail
    escalate_reason — shown to the human when this step is a B/C gate
    classify    — optional name of a registered classifier that computes the
                  REAL autonomy for this step from the run's actual trigger
                  data (e.g. "auto under $500, approval over $500"). Consequence
                  is a property of the real amount, not a label on the playbook,
                  so this is resolved once at plan time from live inputs —
                  never faked as a fixed tier that doesn't actually gate anything.
    """
    key: str
    title: str
    owner: str
    autonomy: Autonomy
    handler: str
    verify: str
    description: str = ""
    escalate_reason: str = ""
    classify: Optional[str] = None


@dataclass
class Playbook:
    """A named, ordered workflow a department knows how to run."""
    key: str                 # "onboarding"
    department: str          # "hr"
    title: str               # "Employee Onboarding"
    description: str
    steps: list[StepSpec]
    # Fields the trigger must supply (used by the UI to build the create form).
    required_inputs: list[dict] = field(default_factory=list)


# ── Live run + step state (dynamic, persisted) ─────────────────────────────────

@dataclass
class RunStep:
    """One live step inside a Task Run."""
    step_id: str
    run_id: str
    seq: int
    key: str
    title: str
    owner: str
    autonomy: str
    handler: str
    verify: str
    status: str = StepStatus.PENDING.value
    description: str = ""
    escalate_reason: str = ""
    # Evidence the handler recorded, and what verification found.
    evidence: dict = field(default_factory=dict)
    verify_result: dict = field(default_factory=dict)
    verified_by: Optional[str] = None      # always the Verifier, never the owner
    result_summary: str = ""
    error: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "run_id": self.run_id,
            "seq": self.seq,
            "key": self.key,
            "title": self.title,
            "owner": self.owner,
            "autonomy": self.autonomy,
            "handler": self.handler,
            "verify": self.verify,
            "status": self.status,
            "description": self.description,
            "escalate_reason": self.escalate_reason,
            "evidence": self.evidence,
            "verify_result": self.verify_result,
            "verified_by": self.verified_by,
            "result_summary": self.result_summary,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class TaskRun:
    """One execution of a Playbook."""
    run_id: str
    department: str
    playbook: str
    title: str                       # "Onboard Priya Sharma"
    subject: str                     # who/what this is about ("Priya Sharma")
    trigger_type: str                # "message" | "schedule" | "event"
    trigger_payload: dict
    tenant_id: str = "default"       # which customer this run belongs to (SaaS isolation)
    status: str = RunStatus.TRIGGERED.value
    created_by: str = "system"
    assigned_lead: str = ""          # department lead that planned it
    digest_line: str = ""            # one-line founder-facing summary
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    steps: list[RunStep] = field(default_factory=list)
    # Mesh linkage — set when this run was dispatched BY another department's
    # run (e.g. HR's onboarding dispatching IT's device provisioning).
    # parent_run_id: the specific run that triggered this one.
    # mesh_group_id: shared by every run in the same cross-department task,
    # so "how did Priya's onboarding go across all departments" is one query.
    parent_run_id: Optional[str] = None
    mesh_group_id: Optional[str] = None

    @staticmethod
    def new(department: str, playbook: str, title: str, subject: str,
            trigger_type: str, trigger_payload: dict, created_by: str,
            tenant_id: str = "default",
            parent_run_id: Optional[str] = None,
            mesh_group_id: Optional[str] = None) -> "TaskRun":
        return TaskRun(
            run_id=_new_id("run"),
            department=department,
            playbook=playbook,
            title=title,
            subject=subject,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload or {},
            tenant_id=tenant_id,
            created_by=created_by,
            parent_run_id=parent_run_id,
            mesh_group_id=mesh_group_id,
        )

    def progress(self) -> tuple[int, int]:
        """(#steps verified, #steps that count toward completion)."""
        counted = [s for s in self.steps if s.status != StepStatus.SKIPPED.value]
        done = [s for s in counted if s.status == StepStatus.VERIFIED.value]
        return len(done), len(counted)

    def to_dict(self, include_steps: bool = True) -> dict:
        done, total = self.progress()
        d = {
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "department": self.department,
            "playbook": self.playbook,
            "title": self.title,
            "subject": self.subject,
            "trigger_type": self.trigger_type,
            "trigger_payload": self.trigger_payload,
            "status": self.status,
            "created_by": self.created_by,
            "assigned_lead": self.assigned_lead,
            "digest_line": self.digest_line,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "parent_run_id": self.parent_run_id,
            "mesh_group_id": self.mesh_group_id,
            "progress": {"done": done, "total": total},
        }
        if include_steps:
            d["steps"] = [s.to_dict() for s in self.steps]
        return d


@dataclass
class Escalation:
    """
    A paused run waiting on a human decision — the human-in-the-loop gate.
    Raised when a step's autonomy is B_approve or C_human.
    """
    escalation_id: str
    run_id: str
    step_id: str
    department: str
    title: str
    reason: str
    autonomy: str
    tenant_id: str = "default"
    status: str = EscalationStatus.PENDING.value
    created_at: str = field(default_factory=_now)
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    decision_note: str = ""

    @staticmethod
    def new(run: "TaskRun", step: "RunStep") -> "Escalation":
        return Escalation(
            escalation_id=_new_id("esc"),
            run_id=run.run_id,
            step_id=step.step_id,
            department=run.department,
            tenant_id=run.tenant_id,
            title=f"{run.title} — {step.title}",
            reason=step.escalate_reason or f"Step '{step.title}' needs a human decision.",
            autonomy=step.autonomy,
        )

    def to_dict(self) -> dict:
        return {
            "escalation_id": self.escalation_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "department": self.department,
            "tenant_id": self.tenant_id,
            "title": self.title,
            "reason": self.reason,
            "autonomy": self.autonomy,
            "status": self.status,
            "created_at": self.created_at,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "decision_note": self.decision_note,
        }


@dataclass
class AuditEntry:
    """One immutable, append-only line in the organization's ledger."""
    entry_id: str
    run_id: str
    step_id: Optional[str]
    department: str
    actor: str          # "onboarding-specialist", "verifier", "hr-lead", "founder:ayush"
    event: str          # "step.executed", "step.verified", "run.escalated", ...
    detail: str
    tenant_id: str = "default"
    at: str = field(default_factory=_now)

    @staticmethod
    def new(run_id: str, department: str, actor: str, event: str,
            detail: str, step_id: Optional[str] = None,
            tenant_id: str = "default") -> "AuditEntry":
        return AuditEntry(
            entry_id=_new_id("aud"),
            run_id=run_id,
            step_id=step_id,
            department=department,
            tenant_id=tenant_id,
            actor=actor,
            event=event,
            detail=detail,
        )

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "department": self.department,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "event": self.event,
            "detail": self.detail,
            "at": self.at,
        }
