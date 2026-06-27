"""
industry_packs/base_pack.py — Industry Pack Base Infrastructure

An Industry Pack is a named bundle of configuration that tailors RAPID for a
specific vertical (Technology/SaaS, Healthcare, etc.).  Each pack provides:

  • metadata           — id, name, description, version
  • departments        — which departments to enable by default
  • kpi_templates      — pre-seeded KPI definitions for the industry
  • risk_templates     — common risks with severity presets
  • onboarding_steps   — ordered questions shown during tenant setup
  • governance_flags   — extra compliance controls (e.g. HIPAA PHI protection)
  • skill_overrides    — pack-specific trigger phrases / skill additions

Usage
─────
  from industry_packs.pack_registry import get_pack_registry
  registry = get_pack_registry()
  pack = registry.get("tech_saas")
  registry.apply(pack_id="tech_saas", tenant_id="t-123", answers={...})
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Optional

import config

logger = logging.getLogger("rapid.industry_packs")


# ── KPI / Risk / Onboarding template models ───────────────────────────────────

@dataclass
class KPITemplate:
    name:          str
    unit:          str                        # %, $, count, days, score …
    target_value:  str                        # default target (string for flexibility)
    description:   str
    dept_id:       str                        # which department owns it
    category:      str = "operational"       # financial | operational | customer | quality


@dataclass
class RiskTemplate:
    title:       str
    severity:    str                          # low | medium | high | critical
    category:    str                          # operational | financial | compliance | tech
    description: str
    mitigation:  str


@dataclass
class OnboardingStep:
    step:        int
    key:         str                          # answer stored under this key
    question:    str
    input_type:  str = "text"                # text | select | multiselect | number
    options:     list[str] = field(default_factory=list)
    required:    bool = True
    hint:        str = ""


@dataclass
class PackDefinition:
    """Complete definition of an industry pack."""
    pack_id:          str
    name:             str
    description:      str
    industry:         str                     # "Technology & SaaS" | "Healthcare" | …
    version:          str = "1.0.0"

    # Department configuration
    departments:      list[str] = field(default_factory=list)   # dept_ids to enable
    primary_dept:     str = "ops"

    # Content templates
    kpi_templates:    list[KPITemplate]      = field(default_factory=list)
    risk_templates:   list[RiskTemplate]     = field(default_factory=list)
    onboarding_steps: list[OnboardingStep]   = field(default_factory=list)

    # Governance & compliance
    governance_flags: dict[str, Any]         = field(default_factory=dict)
    # e.g. {"hipaa": True, "phi_protection": True, "audit_all_access": True}

    # Skills
    skill_overrides:  dict[str, list[str]]   = field(default_factory=dict)
    # e.g. {"extra_triggers": {"sprint_review": ["sprint report", "velocity report"]}}

    def to_dict(self) -> dict:
        return {
            "pack_id":     self.pack_id,
            "name":        self.name,
            "description": self.description,
            "industry":    self.industry,
            "version":     self.version,
            "departments": self.departments,
            "primary_dept": self.primary_dept,
            "kpi_count":   len(self.kpi_templates),
            "risk_count":  len(self.risk_templates),
            "onboarding_steps": len(self.onboarding_steps),
            "governance_flags": self.governance_flags,
        }

    def full_dict(self) -> dict:
        d = self.to_dict()
        d["kpi_templates"] = [
            {"name": k.name, "unit": k.unit, "target": k.target_value,
             "dept": k.dept_id, "category": k.category, "description": k.description}
            for k in self.kpi_templates
        ]
        d["risk_templates"] = [
            {"title": r.title, "severity": r.severity, "category": r.category,
             "description": r.description, "mitigation": r.mitigation}
            for r in self.risk_templates
        ]
        d["onboarding_steps"] = [
            {"step": s.step, "key": s.key, "question": s.question,
             "input_type": s.input_type, "options": s.options,
             "required": s.required, "hint": s.hint}
            for s in self.onboarding_steps
        ]
        return d


# ── Pack Application ──────────────────────────────────────────────────────────

def _ensure_tenant_packs_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenant_packs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   TEXT NOT NULL,
            pack_id     TEXT NOT NULL,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
            answers     TEXT,              -- JSON: onboarding answers
            overrides   TEXT,              -- JSON: custom overrides
            status      TEXT NOT NULL DEFAULT 'active',
            UNIQUE(tenant_id, pack_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenant_packs_tenant ON tenant_packs(tenant_id)"
    )
    conn.commit()


def apply_pack_to_tenant(
    pack:      PackDefinition,
    tenant_id: str,
    answers:   dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict:
    """
    Persist the fact that tenant_id is using this pack.
    Stores onboarding answers and any overrides.
    Returns a summary dict.
    """
    import json
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    try:
        _ensure_tenant_packs_table(conn)
        conn.execute(
            """
            INSERT INTO tenant_packs (tenant_id, pack_id, answers, overrides, status)
            VALUES (?, ?, ?, ?, 'active')
            ON CONFLICT(tenant_id, pack_id) DO UPDATE SET
                answers    = excluded.answers,
                overrides  = excluded.overrides,
                applied_at = datetime('now'),
                status     = 'active'
            """,
            (tenant_id, pack.pack_id,
             json.dumps(answers), json.dumps(overrides or {})),
        )
        conn.commit()
        logger.info(f"[Pack] Applied '{pack.pack_id}' to tenant={tenant_id}")
        return {
            "tenant_id":   tenant_id,
            "pack_id":     pack.pack_id,
            "pack_name":   pack.name,
            "departments": pack.departments,
            "kpis_seeded": len(pack.kpi_templates),
            "risks_seeded": len(pack.risk_templates),
            "governance":  pack.governance_flags,
            "status":      "applied",
        }
    finally:
        conn.close()


def get_tenant_pack(tenant_id: str) -> Optional[dict]:
    """Return the active pack record for this tenant, or None."""
    import json
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_tenant_packs_table(conn)
        row = conn.execute(
            "SELECT * FROM tenant_packs WHERE tenant_id=? AND status='active' ORDER BY applied_at DESC LIMIT 1",
            (tenant_id,),
        ).fetchone()
        if not row:
            return None
        r = dict(row)
        r["answers"]   = json.loads(r.get("answers")   or "{}")
        r["overrides"] = json.loads(r.get("overrides") or "{}")
        return r
    finally:
        conn.close()


def list_tenant_packs(tenant_id: str) -> list[dict]:
    """Return all packs ever applied to a tenant."""
    import json
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_tenant_packs_table(conn)
        rows = conn.execute(
            "SELECT * FROM tenant_packs WHERE tenant_id=? ORDER BY applied_at DESC",
            (tenant_id,),
        ).fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r["answers"]   = json.loads(r.get("answers")   or "{}")
            r["overrides"] = json.loads(r.get("overrides") or "{}")
            result.append(r)
        return result
    finally:
        conn.close()


# ── Pack Registry ─────────────────────────────────────────────────────────────

class PackRegistry:
    """
    Singleton registry of all RAPID industry packs.
    Packs register themselves via register().
    """

    def __init__(self) -> None:
        self._packs: dict[str, PackDefinition] = {}
        self._loaded = False

    def register(self, pack: PackDefinition) -> None:
        self._packs[pack.pack_id] = pack
        logger.debug(f"[PackRegistry] Registered: {pack.pack_id} — {pack.name}")

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        _load_all_packs(self)

    def get(self, pack_id: str) -> Optional[PackDefinition]:
        self._ensure_loaded()
        return self._packs.get(pack_id)

    def list_all(self) -> list[dict]:
        self._ensure_loaded()
        return [p.to_dict() for p in self._packs.values()]

    def apply(
        self,
        pack_id:   str,
        tenant_id: str,
        answers:   dict[str, Any],
        overrides: dict[str, Any] | None = None,
    ) -> dict:
        self._ensure_loaded()
        pack = self._packs.get(pack_id)
        if not pack:
            return {"error": f"Pack '{pack_id}' not found"}
        return apply_pack_to_tenant(pack, tenant_id, answers, overrides)


def _load_all_packs(registry: PackRegistry) -> None:
    """Import all pack modules to trigger self-registration."""
    pack_modules = [
        "industry_packs.tech_saas.pack",
        "industry_packs.healthcare.pack",
    ]
    for mod_path in pack_modules:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            if hasattr(mod, "_register"):
                mod._register(registry)
            logger.debug(f"[PackRegistry] Loaded: {mod_path}")
        except ImportError as e:
            logger.warning(f"[PackRegistry] Could not load {mod_path}: {e}")
        except Exception as e:
            logger.warning(f"[PackRegistry] Error in {mod_path}: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────

_registry_instance: Optional[PackRegistry] = None


def get_pack_registry() -> PackRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = PackRegistry()
    return _registry_instance
