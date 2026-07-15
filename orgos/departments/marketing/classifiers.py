"""
orgos/departments/marketing/classifiers.py — runtime autonomy decisions for
Marketing.
"""

from __future__ import annotations

from orgos.models import Autonomy

SPEND_AUTO_THRESHOLD = 300.0  # USD


def classify_spend_amount(payload: dict) -> tuple:
    amount = float(payload.get("amount", 0) or 0)
    if amount <= SPEND_AUTO_THRESHOLD:
        return Autonomy.A_AUTO, ""
    return (
        Autonomy.B_APPROVE,
        f"This spend increase is ${amount:.0f}, above the ${SPEND_AUTO_THRESHOLD:.0f} "
        f"auto-approval threshold — needs your sign-off.",
    )
