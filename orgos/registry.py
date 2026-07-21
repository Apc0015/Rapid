"""
orgos/registry.py — Where departments plug in.

A department contributes three things and nothing else:
  1. Playbooks   — the ordered workflows it knows how to run
  2. Handlers    — the specialist functions that execute each step
  3. Verifies    — the INDEPENDENT checks that confirm each step against real state

The engine (engine.py) and store (store.py) never know anything HR-specific.
They only know how to look things up here. That is what makes the whole
organization generalize: to add Finance, you register Finance playbooks and
handlers — you do not touch the engine.

Design rule enforced here: a step's `handler` and its `verify` are separate
callables, wired independently. A specialist can never mark its own work
verified — the engine always calls `verify` through the Verifier, never the
handler. See verifier.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from orgos.models import Playbook


@dataclass
class StepContext:
    """Everything a handler or verify check is given to do its job."""
    run: object            # TaskRun
    step: object           # RunStep
    store: object          # OrgStore
    inputs: dict           # the run's trigger_payload (the form the user filled)

    def record(self, record_type: str, data: dict) -> str:
        """Write real state into the system of record for this run's subject."""
        return self.store.put_record(
            department=self.run.department,
            record_type=record_type,
            subject=self.run.subject,
            data=data,
            run_id=self.run.run_id,
            tenant_id=getattr(self.run, "tenant_id", "default"),
        )

    def find(self, record_type: str, subject: Optional[str] = None) -> Optional[dict]:
        return self.store.find_record(
            department=self.run.department,
            record_type=record_type,
            subject=subject or self.run.subject,
            tenant_id=getattr(self.run, "tenant_id", "default"),
        )

    def trigger_department(self, department: str, playbook_key: str,
                           subject: Optional[str] = None,
                           inputs: Optional[dict] = None) -> object:
        """
        The mesh primitive: dispatch a run in ANOTHER department as part of
        this run's work (e.g. HR's onboarding dispatching IT's device
        provisioning). The child run is linked back via parent_run_id and
        shares this run's mesh_group_id, so "how did this cross-department
        task go everywhere" is one query (store.list_runs_by_mesh_group).

        The child is run to completion/escalation immediately — it does not
        wait for this step to finish, matching real departments working in
        parallel rather than one blocking the next.
        """
        from orgos.engine import get_engine  # lazy import — avoids a cycle with engine.py
        eng = get_engine()
        mesh_group_id = self.run.mesh_group_id or self.run.run_id
        child = eng.create_run(
            department=department,
            playbook_key=playbook_key,
            subject=subject or self.run.subject,
            trigger_type="mesh",
            payload=inputs or {},
            created_by=f"mesh:{self.run.department}",
            tenant_id=getattr(self.run, "tenant_id", "default"),
            parent_run_id=self.run.run_id,
            mesh_group_id=mesh_group_id,
        )
        return eng.advance(child.run_id)


@dataclass
class HandlerResult:
    """What a specialist returns after executing a step."""
    summary: str
    evidence: dict = field(default_factory=dict)


@dataclass
class VerifyResult:
    """What the Verifier returns after independently checking a step."""
    ok: bool
    detail: str
    found: dict = field(default_factory=dict)


# handler:    (StepContext) -> HandlerResult
Handler = Callable[[StepContext], HandlerResult]
# verify:     (StepContext) -> VerifyResult
Verify = Callable[[StepContext], VerifyResult]
# classifier: (trigger_payload dict) -> (Autonomy, escalate_reason str) — resolves
# the REAL tier from the run's actual data (e.g. an amount) before the run is
# planned. escalate_reason may be "" when the resolved tier is A_auto.
Classifier = Callable[[dict], tuple]


class Registry:
    def __init__(self) -> None:
        self._playbooks: dict[str, Playbook] = {}        # key -> Playbook
        self._handlers: dict[str, Handler] = {}          # name -> callable
        self._verifies: dict[str, Verify] = {}           # name -> callable
        self._classifiers: dict[str, Classifier] = {}    # name -> callable

    # ── registration ───────────────────────────────────────────────────────────

    def register_playbook(self, pb: Playbook) -> None:
        self._playbooks[pb.key] = pb

    def register_handler(self, name: str, fn: Handler) -> None:
        self._handlers[name] = fn

    def register_verify(self, name: str, fn: Verify) -> None:
        self._verifies[name] = fn

    def register_classifier(self, name: str, fn: Classifier) -> None:
        self._classifiers[name] = fn

    # ── lookup ─────────────────────────────────────────────────────────────────

    def playbook(self, key: str) -> Optional[Playbook]:
        return self._playbooks.get(key)

    def handler(self, name: str) -> Optional[Handler]:
        return self._handlers.get(name)

    def verify(self, name: str) -> Optional[Verify]:
        return self._verifies.get(name)

    def classifier(self, name: str) -> Optional[Classifier]:
        return self._classifiers.get(name)

    def list_playbooks(self, department: Optional[str] = None) -> list[Playbook]:
        pbs = list(self._playbooks.values())
        if department:
            pbs = [p for p in pbs if p.department == department]
        return pbs


# ── singleton ──────────────────────────────────────────────────────────────────
_registry: Optional[Registry] = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
        _load_departments(_registry)
    return _registry


def _load_departments(reg: Registry) -> None:
    """Import each department so its playbooks/handlers self-register."""
    from orgos.departments.hr import register as register_hr
    from orgos.departments.it import register as register_it
    from orgos.departments.finance import register as register_finance
    from orgos.departments.marketing import register as register_marketing
    register_hr(reg)
    register_it(reg)
    register_finance(reg)
    register_marketing(reg)
