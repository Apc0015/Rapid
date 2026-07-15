"""
orgos/departments/it/classifiers.py — runtime autonomy decisions for IT.

A classifier computes a step's REAL autonomy tier from the run's actual
trigger data, resolved once at plan time (see orgos/engine.py). This is what
makes "auto-approve under a threshold, escalate over it" an enforced rule
instead of a label with nothing behind it.
"""

from __future__ import annotations

from orgos.models import Autonomy

LICENSE_AUTO_THRESHOLD = 50.0  # USD/month


def classify_license_cost(payload: dict) -> tuple:
    cost = float(payload.get("monthly_cost", 0) or 0)
    if cost <= LICENSE_AUTO_THRESHOLD:
        return Autonomy.A_AUTO, ""
    return (
        Autonomy.B_APPROVE,
        f"This tool costs ${cost:.0f}/mo, above the ${LICENSE_AUTO_THRESHOLD:.0f}/mo "
        f"auto-approval threshold — needs your sign-off.",
    )
