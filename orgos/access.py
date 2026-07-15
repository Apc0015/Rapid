"""
orgos/access.py — role-based access control for the digital organization.

Reuses the SAME roles and JWT claims the rest of RAPID already issues at
login (routers/auth.py → infrastructure/user_registry.py) — this is not a
second, parallel user system. Three tiers, matching how a real org's board
access actually needs to work:

  admin / ceo    — full access: every department, create tasks, decide escalations
  board_member   — read-only, every department: sees boards/digest/escalations/
                   audit, but cannot create a task or approve/decline anything
  everyone else  — full access, but ONLY within their own permitted_departments
                   (the `depts` claim already on their JWT from login)

This closes the gap flagged earlier: previously any authenticated user had
identical, full power in every department — a board member and the founder
were indistinguishable. Now they aren't.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from routers.deps import get_current_user

# Roles with company-wide access regardless of their `depts` claim.
FULL_ACCESS_ROLES = {"admin", "ceo"}

# Roles that can look at everything but cannot change anything (no create,
# no approve/decline). Mirrors user_registry.AGGREGATE_ONLY_ROLES — a board
# member gets summaries and audit trails, not the controls.
READ_ONLY_ROLES = {"board_member"}


def _has_full_access(user: dict) -> bool:
    return user.get("role") in FULL_ACCESS_ROLES


def _is_read_only(user: dict) -> bool:
    return user.get("role") in READ_ONLY_ROLES


def can_view_department(user: dict, department: str) -> bool:
    if _has_full_access(user) or _is_read_only(user):
        return True  # read-only roles see every department, just can't act
    return department in (user.get("depts") or [])


def require_department_view(department: str):
    """FastAPI dependency: 403s if this user can't even see this department."""
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if not can_view_department(user, department):
            raise HTTPException(
                status_code=403,
                detail=f"You don't have access to the {department} department.",
            )
        return user
    return _check


def require_department_write(department: str):
    """
    FastAPI dependency for anything that changes state (create a run, decide
    an escalation, advance a run). Board members pass the view check but are
    blocked here — this is the enforcement point for "read-only".
    """
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if not can_view_department(user, department):
            raise HTTPException(
                status_code=403,
                detail=f"You don't have access to the {department} department.",
            )
        if _is_read_only(user):
            raise HTTPException(
                status_code=403,
                detail="Your role has read-only access — you can view this "
                       "department's work but not create tasks or decide escalations.",
            )
        return user
    return _check


def visible_departments(user: dict, all_departments: list[str]) -> list[str]:
    """Which departments this user's Overview/org-wide views should include."""
    if _has_full_access(user) or _is_read_only(user):
        return list(all_departments)
    return [d for d in all_departments if d in (user.get("depts") or [])]
