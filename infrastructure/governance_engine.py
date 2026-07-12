from __future__ import annotations
"""
infrastructure/governance_engine.py
─────────────────────────────────────────────────────────────────────────────
Unified Governance Engine — runs all governance checks in strict order:

  CHECK 1 — Org Governance       (org_governance.yaml — unbreakable)
  CHECK 2 — Privacy Rights       (dept config → privacy_rights)
  CHECK 3 — Dept Governance      (dept config → dept_governance)
  CHECK 4 — Policy Formatter     (dept config → policy)

Every query passes through this engine before any data is fetched.
Every answer passes through this engine before it is returned.

Singleton — load once at startup, share across all agents.
"""

import logging
import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class GovernanceVerdict:
    """Returned by every governance check."""
    allowed: bool
    check:   str                        # which check blocked/allowed
    reason:  str = ""
    message: str = ""                   # safe message to return to user
    escalation_path: str = ""


@dataclass
class FieldVerdict:
    """Per-field verdict from dept governance."""
    field:   str
    action:  str                        # ALLOW | ANONYMIZE | BLOCK
    rule:    str = ""


@dataclass
class FormattedAnswer:
    """Policy-formatted answer ready for the spokesperson."""
    content:        str
    always_include: list[str] = field(default_factory=list)
    sources:        list[str] = field(default_factory=list)
    confidence:     float = 1.0


# ── Governance Engine ─────────────────────────────────────────────────────────

class GovernanceEngine:

    def __init__(self,
                 org_gov_path: str = "governance/org_governance.yaml",
                 dept_configs_base: str = "departments"):
        self._org   = self._load_yaml(org_gov_path)
        self._depts: dict[str, dict] = {}
        self._base  = Path(dept_configs_base)
        self._pii_patterns: list[tuple[str, re.Pattern]] = []
        self._build_pii_patterns()

    # ── Public API ────────────────────────────────────────────────────────────

    def check_query(self, query: str, dept_id: str,
                    user_role: str, user_id: str) -> GovernanceVerdict:
        """
        Run CHECK 1 (org) + CHECK 2 (privacy rights) on an incoming query.
        Call BEFORE fetching any data.
        Returns GovernanceVerdict(allowed=False) to abort early.
        """
        # Check 1 — org-level global blocks (topic-agnostic)
        verdict = self._check_org_global(query)
        if not verdict.allowed:
            logger.warning(f"[gov] Org block | user={user_id} dept={dept_id} reason={verdict.reason}")
            return verdict

        # Check 2 — dept privacy rights
        cfg = self._dept_cfg(dept_id)
        if cfg:
            verdict = self._check_privacy_rights(query, cfg, dept_id)
            if not verdict.allowed:
                logger.info(f"[gov] Privacy block | user={user_id} dept={dept_id} reason={verdict.reason}")
                return verdict

        return GovernanceVerdict(allowed=True, check="passed", reason="All checks passed")

    def apply_field_rules(self, record: dict, dept_id: str,
                          user_role: str) -> tuple[dict, list[FieldVerdict]]:
        """
        Run CHECK 3 (dept governance) on a record dict.
        Returns (governed_record, list[FieldVerdict]).
        Call AFTER data is fetched, BEFORE it reaches the LLM.
        """
        cfg     = self._dept_cfg(dept_id)
        col_cfg = cfg.get("dept_governance", {}).get("column_rules", {}) if cfg else {}
        allow_cols    = set(col_cfg.get("allow",     []))
        anonymize_cols = set(col_cfg.get("anonymize", []))
        block_cols    = set(col_cfg.get("block",     []))
        global_blocks = set(
            self._org.get("absolute_rules", {})
                .get("global_blocked_fields", [])
        )
        role_map = {
            "allow_manager":        {"manager","dept_head","division_head","c_suite","ceo","admin"},
            "allow_dept_head":      {"dept_head","division_head","c_suite","ceo","admin"},
            "allow_division_head":  {"division_head","c_suite","ceo","admin"},
            "allow_csuite":         {"c_suite","ceo","admin"},
            "allow_ceo":            {"ceo","admin"},
        }

        governed: dict = {}
        verdicts: list[FieldVerdict] = []

        for field_name, value in record.items():
            f_lower = field_name.lower()

            # Org absolute block
            if f_lower in global_blocks:
                verdicts.append(FieldVerdict(field_name, "BLOCK", "org_global"))
                continue

            # Dept block
            if f_lower in block_cols:
                verdicts.append(FieldVerdict(field_name, "BLOCK", "dept_block"))
                continue

            # Dept anonymize
            if f_lower in anonymize_cols:
                governed[field_name] = "[ANONYMIZED]"
                verdicts.append(FieldVerdict(field_name, "ANONYMIZE", "dept_anonymize"))
                continue

            # Role-conditional allow (e.g. allow_manager)
            matched_role_rule = False
            for rule_key, allowed_roles in role_map.items():
                if f_lower in col_cfg.get(rule_key, []):
                    if user_role.lower() in allowed_roles:
                        governed[field_name] = value
                        verdicts.append(FieldVerdict(field_name, "ALLOW", rule_key))
                    else:
                        verdicts.append(FieldVerdict(field_name, "BLOCK", rule_key))
                    matched_role_rule = True
                    break

            if matched_role_rule:
                continue

            # Dept explicit allow
            if allow_cols and f_lower in allow_cols:
                governed[field_name] = value
                verdicts.append(FieldVerdict(field_name, "ALLOW", "dept_allow"))
                continue

            # Default posture. If the dept declares an allow-list, anything not on
            # it is denied (deny-by-default). If no allow-list is configured the
            # dept is ungoverned, so preserve the legacy allow.
            if allow_cols:
                verdicts.append(FieldVerdict(field_name, "BLOCK", "default_deny"))
            else:
                governed[field_name] = value
                verdicts.append(FieldVerdict(field_name, "ALLOW", "default_ungoverned"))

        return governed, verdicts

    def redact_pii(self, text: str) -> str:
        """
        Auto-redact PII patterns from any text output.
        Runs on ALL LLM output before it reaches the user.
        """
        for label, pattern in self._pii_patterns:
            text = pattern.sub(f"[{label.upper()}_REDACTED]", text)
        return text

    def format_answer(self, raw_answer: str, dept_id: str,
                      user_role: str, sources: list[str]) -> FormattedAnswer:
        """
        Run CHECK 4 (policy formatter) on the LLM's raw answer.
        Applies dept reply_style + always_include rules.
        """
        cfg    = self._dept_cfg(dept_id)
        policy = cfg.get("policy", {}) if cfg else {}
        agent  = cfg.get("agent",  {}) if cfg else {}

        always_include = agent.get("output", {}).get("always_include", [])
        max_tokens     = agent.get("output", {}).get("max_tokens", 800)

        # Redact PII from the answer
        clean = self.redact_pii(raw_answer)

        return FormattedAnswer(
            content        = clean,
            always_include = always_include,
            sources        = sources,
            confidence     = 1.0,
        )

    def get_dept_persona(self, dept_id: str) -> str:
        cfg = self._dept_cfg(dept_id)
        if not cfg:
            return f"You are the {dept_id} department agent."
        return cfg.get("agent", {}).get("persona", f"You are the {dept_id} department agent.")

    def get_dept_reply_style(self, dept_id: str) -> dict:
        cfg = self._dept_cfg(dept_id)
        if not cfg:
            return {}
        return cfg.get("policy", {}).get("reply_style", {})

    def get_dept_skills(self, dept_id: str) -> dict:
        cfg = self._dept_cfg(dept_id)
        if not cfg:
            return {}
        return cfg.get("skills", {})

    def get_dept_escalation(self, dept_id: str) -> str:
        cfg = self._dept_cfg(dept_id)
        if not cfg:
            return "admin"
        return cfg.get("agent", {}).get("escalates_to", "admin")

    def get_dept_confidence_threshold(self, dept_id: str) -> float:
        cfg = self._dept_cfg(dept_id)
        if not cfg:
            return 0.65
        return float(cfg.get("agent", {}).get("confidence_threshold", 0.65))

    def get_dept_peers(self, dept_id: str) -> list[str]:
        cfg = self._dept_cfg(dept_id)
        if not cfg:
            return []
        return cfg.get("agent", {}).get("can_consult", [])

    def get_pipeline_cfg(self, dept_id: str, pipeline: str) -> dict:
        """pipeline = 'structured_pipeline' | 'unstructured_pipeline'"""
        cfg = self._dept_cfg(dept_id)
        if not cfg:
            return {}
        return cfg.get(pipeline, {})

    def role_entitlement(self, role: str) -> dict:
        return self._org.get("role_entitlements", {}).get(role, {})

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _dept_cfg(self, dept_id: str) -> dict:
        if dept_id not in self._depts:
            path = self._base / dept_id / "config.yaml"
            self._depts[dept_id] = self._load_yaml(str(path))
        return self._depts[dept_id]

    def _check_org_global(self, query: str) -> GovernanceVerdict:
        """Check if query contains references to globally blocked fields."""
        blocked = self._org.get("absolute_rules", {}).get("global_blocked_fields", [])
        q_lower = query.lower()
        for field in blocked:
            if field.replace("_", " ") in q_lower or field in q_lower:
                return GovernanceVerdict(
                    allowed=False,
                    check="org_global",
                    reason=f"Query references globally blocked field: {field}",
                    message="That type of information is not accessible through this system.",
                )
        return GovernanceVerdict(allowed=True, check="org_global")

    def _check_privacy_rights(self, query: str, dept_cfg: dict,
                               dept_id: str) -> GovernanceVerdict:
        """Check if query topic matches dept's internal_only privacy rights."""
        privacy   = dept_cfg.get("privacy_rights", {})
        internals = privacy.get("internal_only", [])
        q_lower   = query.lower()

        for item in internals:
            blocks = item.get("blocks_topics", [])
            for topic in blocks:
                if topic.lower() in q_lower:
                    blocked_msg  = privacy.get("respond_with_when_blocked", {})
                    return GovernanceVerdict(
                        allowed=False,
                        check="dept_privacy",
                        reason=f"Topic '{topic}' is internal-only for {dept_id}",
                        message=blocked_msg.get("message",
                            f"That information is managed internally by the "
                            f"{dept_id.title()} team and is not available through this system."),
                        escalation_path=blocked_msg.get("escalation_path", ""),
                    )

        return GovernanceVerdict(allowed=True, check="dept_privacy")

    def _build_pii_patterns(self):
        patterns_cfg = (
            self._org.get("absolute_rules", {})
                .get("pii_auto_redact", {})
        )
        for label, pattern_str in patterns_cfg.items():
            try:
                self._pii_patterns.append((label, re.compile(pattern_str)))
            except re.error as e:
                logger.warning(f"[gov] Invalid PII pattern '{label}': {e}")

    @staticmethod
    def _load_yaml(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            logger.warning(f"[gov] Config not found: {path}")
            return {}
        try:
            return yaml.safe_load(p.read_text()) or {}
        except Exception as e:
            logger.error(f"[gov] Failed to load {path}: {e}")
            return {}


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine: Optional[GovernanceEngine] = None


def get_governance_engine() -> GovernanceEngine:
    global _engine
    if _engine is None:
        _engine = GovernanceEngine()
    return _engine
