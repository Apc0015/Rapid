from __future__ import annotations
"""
Governance Filter — Tier 4.
Applies Company Constitution rules to every agent output.
No agent output bypasses this — it is architecturally enforced.
"""

import logging
import os
from pathlib import Path
from typing import Optional
import yaml

logger = logging.getLogger(__name__)


# ── Anonymization helpers ──────────────────────────────────────────────────────

def _mask_email(email: str) -> str:
    """
    Hash/mask an email address for GDPR compliance.
    alice@company.com  →  a***@company.com
    """
    if not email or "@" not in email:
        return "[ANONYMIZED]"
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"

# ── Role-level ALLOW_ hierarchy ───────────────────────────────────────────────
# Maps the suffix of an ALLOW_<SUFFIX> rule → set of roles that qualify.
# Roles not listed in a set are blocked for that rule.
ALLOW_ROLE_MAP: dict[str, set[str]] = {
    "manager":       {"manager", "dept_head", "division_head", "c_suite", "board_member", "ceo", "admin"},
    "dept_head":     {"dept_head", "division_head", "c_suite", "board_member", "ceo", "admin"},
    "division_head": {"division_head", "c_suite", "ceo", "admin"},
    "executive":     {"division_head", "c_suite", "ceo", "admin"},   # excludes board (aggregate-only)
    "csuite":        {"c_suite", "ceo", "admin"},
    "ceo":           {"ceo", "admin"},
    "board":         {"board_member", "ceo", "admin"},
}


def resolve_column_action(
    column: str, column_rules: dict, user_role: str, default_action: str
) -> tuple[str, str]:
    """The single decision point for column governance.

    Every governed path resolves a column's visibility HERE, so they can never
    disagree — in particular about which roles satisfy an ``ALLOW_<role>`` rule.
    Returns ``(action, reason)`` where action is one of ALLOW / ANONYMIZE / BLOCK
    and reason ∈ {explicit, default, role_allowed, role_blocked, unknown_rule}.
    Fail-closed: an unknown or malformed rule resolves to BLOCK.
    """
    explicit = column in column_rules
    rule = column_rules.get(column, default_action)
    role = (user_role or "").lower()
    via = "explicit" if explicit else "default"

    if rule == "ALLOW":
        return "ALLOW", via
    if rule == "ANONYMIZE":
        return "ANONYMIZE", via
    if rule == "BLOCK":
        return "BLOCK", via
    if isinstance(rule, str) and rule.startswith("ALLOW_"):
        suffix = rule.split("_", 1)[1].lower()
        allowed = ALLOW_ROLE_MAP.get(suffix, {suffix, "admin"})
        return ("ALLOW", "role_allowed") if role in allowed else ("BLOCK", "role_blocked")
    return "BLOCK", "unknown_rule"


class RuleSet:
    def __init__(self, column_rules: dict, dept_tag: str, user_role: str):
        self.column_rules = column_rules   # {col: ALLOW|ANONYMIZE|BLOCK|ALLOW_MANAGER}
        self.dept_tag = dept_tag
        self.user_role = user_role


class GovernanceFilter:
    """
    Loads and enforces the Company Constitution.
    Singleton — loaded once at startup.
    """

    def __init__(self, constitution_path: str = "constitution.yaml"):
        self.constitution = self._load_constitution(constitution_path)
        self._audit_actions: list[dict] = []
        # Pre-build column → anonymization method lookup from Article 4
        # e.g. {"salary": "team_average", "contact_email": "hash_email", ...}
        agg_entries = self.constitution.get("aggregation_required", [])
        self._agg_method: dict[str, str] = {
            entry["column"]: entry["method"]
            for entry in agg_entries
            if "column" in entry and "method" in entry
        }
        # Default action for columns with no explicit rule (Article 0).
        self.default_action: str = self._resolve_default_action()

    def _resolve_default_action(self) -> str:
        """
        Resolve what happens to an unlisted column.
        - No constitution loaded (dev / missing file): governance is disabled, so
          allow (matches the loud warning already emitted by _load_constitution).
        - Constitution present: honor governance.default_action, defaulting to
          BLOCK (deny-by-default). Invalid values fail closed to BLOCK.
        """
        if not self.constitution:
            return "ALLOW"
        raw = str(
            self.constitution.get("governance", {}).get("default_action", "BLOCK")
        ).upper()
        if raw not in ("ALLOW", "ANONYMIZE", "BLOCK"):
            logger.warning(
                f"governance.default_action='{raw}' is invalid — failing closed to BLOCK"
            )
            return "BLOCK"
        if raw == "ALLOW":
            logger.warning(
                "governance.default_action=ALLOW — unlisted columns are exposed to "
                "every role (fail-open). BLOCK is recommended for production."
            )
        return raw

    # ── Rule loading ──────────────────────────────────────────────────────────

    def load_rules(self, user_id: str, dept_tag: str, user_role: str = "employee") -> RuleSet:
        """
        Read Constitution rules applicable to this user in this department.
        Returns RuleSet with column-level permissions.
        """
        col_perms = self.constitution.get("column_permissions", {})
        dept_perms = col_perms.get(dept_tag, {})

        # Flatten all tables in dept into one col→rule dict
        column_rules = {}
        for table, cols in dept_perms.items():
            for col, rule in cols.items():
                column_rules[col] = rule

        return RuleSet(column_rules=column_rules, dept_tag=dept_tag, user_role=user_role)

    def get_user_permissions(self, user_id: str, role: str,
                             permitted_depts: Optional[list] = None) -> dict:
        """
        Build the full user_permissions dict that travels with every query.
        Includes role, permitted departments, and column rules per dept.

        ``permitted_depts`` — when supplied (e.g. loaded from users.yaml) it
        overrides the constitution's static department list.  Executive roles
        (ceo, board_member, admin) always get ALL departments regardless.
        """
        from infrastructure.user_registry import (
            ROLE_DEFAULT_DEPTS, ALL_DEPTS, AGGREGATE_ONLY_ROLES
        )

        # Executive roles always see all departments. "manager" is deliberately
        # excluded — a department manager should see their own department(s),
        # not every department in the company (that was a bug: it silently
        # granted every manager company-wide visibility regardless of role).
        executive_all = {"ceo", "board_member", "admin"}
        if role in executive_all:
            depts = ALL_DEPTS
        elif permitted_depts is not None:
            depts = permitted_depts
        else:
            # Fall back to constitution.yaml, then role defaults
            access      = self.constitution.get("access_control", {})
            role_access = access.get(role, {})
            if role_access.get("departments"):
                depts = role_access["departments"]
            else:
                depts = ROLE_DEFAULT_DEPTS.get(role, ["hr", "it"])

        access        = self.constitution.get("access_control", {})
        role_access   = access.get(role, access.get("employee", {}))
        access_level  = role_access.get("level", "standard")

        return {
            "user_id":              user_id,
            "role":                 role,
            "permitted_departments": depts,
            "access_level":         access_level,
            "aggregate_only":       role in AGGREGATE_ONLY_ROLES,
            # column_rules populated per-dept at query time
            "column_rules": {},
        }

    def is_aggregate_only(self, role: str) -> bool:
        """True for roles that must only ever receive aggregated summaries (no raw rows)."""
        from infrastructure.user_registry import AGGREGATE_ONLY_ROLES
        return role in AGGREGATE_ONLY_ROLES

    def enrich_permissions_for_dept(self, user_permissions: dict, dept_tag: str) -> dict:
        """Add dept-specific column rules to the permissions dict."""
        rule_set = self.load_rules(
            user_id=user_permissions["user_id"],
            dept_tag=dept_tag,
            user_role=user_permissions.get("role", "employee"),
        )
        enriched = dict(user_permissions)
        enriched["column_rules"] = rule_set.column_rules
        enriched["dept_tag"] = dept_tag
        return enriched

    # ── Rule application ──────────────────────────────────────────────────────

    def _anonymize_value(self, field: str, value, method: Optional[str]):
        """Format an anonymized value using the column's aggregation method."""
        if method == "hash_email":
            return _mask_email(str(value) if value is not None else "")
        if method in ("team_average", "average", "group_average"):
            return "[Team average only — contact your manager]"
        if method == "paraphrase":
            return "[Paraphrased for privacy]"
        # No aggregation_required entry for this column — generic mask.
        return "[ANONYMIZED]"

    def apply_rules(self, result: dict, rule_set: RuleSet) -> tuple[dict, list[dict]]:
        """
        Apply Constitution rules field-by-field to a result dict.
        Every field's visibility is decided by resolve_column_action(), the one
        shared decision point, so this path and the DB result path never disagree.
        Returns (governed_result, governance_log).
        """
        governed = {}
        log = []
        user_role = rule_set.user_role

        for field, value in result.items():
            explicit = field in rule_set.column_rules
            rule = rule_set.column_rules.get(field)
            via = "explicit" if explicit else "default"
            action, reason = resolve_column_action(
                field, rule_set.column_rules, user_role, self.default_action
            )

            if action == "ALLOW":
                governed[field] = value
                if reason == "role_allowed":
                    log.append({"field": field, "action": "ALLOW_ROLE", "rule": rule, "via": via})
                else:
                    log.append({"field": field, "action": "ALLOW", "via": via})

            elif action == "ANONYMIZE":
                method = self._agg_method.get(field)
                governed[field] = self._anonymize_value(field, value, method)
                log.append({"field": field, "action": "ANONYMIZE", "method": method or "default", "via": via})

            elif reason == "role_blocked":
                log.append({"field": field, "action": "BLOCK_ROLE", "severity": "MEDIUM", "rule": rule, "via": via})
                self._audit_actions.append({"field": field, "action": "BLOCK_ROLE", "role": user_role, "rule": rule})

            elif reason == "unknown_rule":
                log.append({"field": field, "action": "BLOCK_UNKNOWN", "severity": "HIGH", "rule": rule, "via": via})
                self._audit_actions.append({"field": field, "action": "BLOCK_UNKNOWN", "role": user_role, "rule": rule})

            else:  # explicit or default BLOCK
                log.append({"field": field, "action": "BLOCK", "severity": "HIGH", "via": via})
                self._audit_actions.append({"field": field, "action": "BLOCK", "role": user_role, "via": via})

        return governed, log

    def check_dept_boundary(self, result_dept: str, requesting_dept: str) -> bool:
        """
        Confirm no cross-department data contamination.
        Returns True if boundary is clean, False if violated.
        """
        if result_dept != requesting_dept:
            logger.error(
                f"Department boundary violation: result from '{result_dept}' "
                f"reached '{requesting_dept}' agent"
            )
            return False
        return True

    def is_dept_permitted(self, user_permissions: dict, dept_tag: str) -> bool:
        """Check if user has access to a given department."""
        return dept_tag in user_permissions.get("permitted_departments", [])

    # ── Audit ─────────────────────────────────────────────────────────────────

    def log_governance_action(self, action: dict):
        """Write governance action to in-memory log (Audit Logger persists to DB)."""
        self._audit_actions.append(action)
        severity = action.get("severity", "LOW")
        if severity == "HIGH":
            logger.warning(f"GOVERNANCE BLOCK: {action}")

    def get_pending_audit_actions(self) -> list[dict]:
        actions = list(self._audit_actions)
        self._audit_actions.clear()
        return actions

    # ── Article lookups ───────────────────────────────────────────────────────

    def get_dept_tables(self, dept_tag: str) -> list[str]:
        """Article 3: return permitted tables for a department."""
        boundaries = self.constitution.get("department_boundaries", {})
        return boundaries.get(dept_tag, [])

    def get_aggregation_rules(self) -> list[dict]:
        """Article 4: return all forced aggregation rules."""
        return self.constitution.get("aggregation_required", [])

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_constitution(self, path: str) -> dict:
        p = Path(path)
        if not p.exists():
            rapid_env = os.environ.get("RAPID_ENV", "development")
            if rapid_env == "production":
                raise RuntimeError(
                    f"constitution.yaml not found at {path}. "
                    "Governance cannot run without it. Refusing to start."
                )
            else:
                logger.error(
                    f"Constitution not found at {path} — ALL governance rules are DISABLED. "
                    "This is only acceptable in development/testing. "
                    "Set RAPID_ENV=production to enforce strict startup."
                )
                return {}
        with open(p) as f:
            constitution = yaml.safe_load(f)
        logger.info("Company Constitution loaded successfully")
        return constitution


# ── Singleton ─────────────────────────────────────────────────────────────────
_governance: Optional[GovernanceFilter] = None

def get_governance() -> GovernanceFilter:
    global _governance
    if _governance is None:
        _governance = GovernanceFilter()
    return _governance
