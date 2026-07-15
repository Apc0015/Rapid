"""
orgos/departments/finance/classifiers.py — runtime autonomy decisions for Finance.
"""

from __future__ import annotations

from orgos.models import Autonomy

EXPENSE_AUTO_THRESHOLD = 100.0   # USD
BUDGET_AUTO_THRESHOLD = 500.0    # USD


def classify_expense_amount(payload: dict) -> tuple:
    amount = float(payload.get("amount", 0) or 0)
    if amount <= EXPENSE_AUTO_THRESHOLD:
        return Autonomy.A_AUTO, ""
    return (
        Autonomy.B_APPROVE,
        f"This expense is ${amount:.2f}, above the ${EXPENSE_AUTO_THRESHOLD:.0f} "
        f"auto-approval threshold — needs your sign-off.",
    )


def classify_budget_amount(payload: dict) -> tuple:
    amount = float(payload.get("amount", 0) or 0)
    if amount <= BUDGET_AUTO_THRESHOLD:
        return Autonomy.A_AUTO, ""
    return (
        Autonomy.B_APPROVE,
        f"This budget request is ${amount:.2f}, above the ${BUDGET_AUTO_THRESHOLD:.0f} "
        f"auto-approval threshold — needs your sign-off.",
    )
