"""
orgos/verifier.py — The independent QA gate (Tier 4).

The single most important rule in the whole system lives here: a specialist
cannot verify its own work. The engine executes a step by calling its `handler`;
it confirms a step by calling THIS module, which runs the step's separate
`verify` check against the real system of record. The two are wired
independently in the registry, so there is no code path by which a handler's
own return value marks itself verified.

If the verify check does not find the state it expects, the step FAILS — even
if the handler reported success. That gap is exactly what this gate exists to
catch.
"""

from __future__ import annotations

import logging

from orgos.registry import StepContext, VerifyResult, get_registry

logger = logging.getLogger(__name__)

VERIFIER_ACTOR = "verifier"


class Verifier:
    """Independent confirmation of a step against real recorded state."""

    def verify_step(self, ctx: StepContext) -> VerifyResult:
        check = get_registry().verify(ctx.step.verify)
        if check is None:
            # No verify registered is a hard failure, not a silent pass.
            return VerifyResult(
                ok=False,
                detail=f"No verify check registered under '{ctx.step.verify}'. "
                       "Refusing to pass a step that cannot be confirmed.",
            )
        try:
            result = check(ctx)
        except Exception as e:  # a verify that throws is a failure, never a pass
            logger.exception("Verify check '%s' raised", ctx.step.verify)
            return VerifyResult(ok=False, detail=f"Verify check errored: {e!r}")

        if not isinstance(result, VerifyResult):
            return VerifyResult(ok=False, detail="Verify check returned a non-VerifyResult.")
        return result


_verifier: Verifier | None = None


def get_verifier() -> Verifier:
    global _verifier
    if _verifier is None:
        _verifier = Verifier()
    return _verifier
