"""
agents/skills/skill_registry.py — Global Skill Registry.

All skills self-register here. The registry provides:
  - list_available(dept_id)   — skills callable for a department
  - detect(query, dept_id)    — auto-detect best skill from query text
  - get(skill_id)             — fetch a skill by ID
  - execute(skill_id, context, params) — run a skill and return SkillOutput

Universal skills are available to every department.
Department-specific skills are scoped to their dept.

Usage
─────
    from agents.skills.skill_registry import get_skill_registry

    registry = get_skill_registry()
    skill    = registry.detect("generate a budget variance report", dept_id="finance")
    output   = await registry.execute(skill.skill_id, project_context)
"""

from __future__ import annotations

import logging
from typing import Optional

from agents.skills.base_skill import BaseSkill, SkillOutput
from infrastructure.project_context import ProjectContext

logger = logging.getLogger(__name__)

_registry_instance: Optional["SkillRegistry"] = None


class SkillRegistry:
    """
    Singleton registry of all RAPID skills.

    Skills register themselves via register(skill_class).
    The registry is populated on first access by _load_all_skills().
    """

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}   # skill_id → instance
        self._loaded = False

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, skill: BaseSkill) -> None:
        """Register a skill instance."""
        self._skills[skill.skill_id] = skill
        logger.debug(f"[SkillRegistry] Registered: {skill.skill_id} (dept={skill.dept_id})")

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        _load_all_skills(self)

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, skill_id: str) -> Optional[BaseSkill]:
        """Fetch a skill by ID. Returns None if not found."""
        self._ensure_loaded()
        return self._skills.get(skill_id)

    def list_available(self, dept_id: Optional[str] = None) -> list[dict]:
        """
        Return all skills available to a department.
        Universal skills (dept_id='all') are always included.
        """
        self._ensure_loaded()
        results = []
        for skill in self._skills.values():
            if skill.dept_id == "all" or skill.dept_id == dept_id or dept_id is None:
                results.append({
                    "skill_id":      skill.skill_id,
                    "dept_id":       skill.dept_id,
                    "description":   skill.description,
                    "output_format": skill.output_format,
                    "triggers":      skill.trigger_phrases[:3],   # preview
                })
        return sorted(results, key=lambda s: (s["dept_id"], s["skill_id"]))

    def detect(self, query: str, dept_id: Optional[str] = None) -> Optional[BaseSkill]:
        """
        Find the best matching skill for a query.
        Prefers dept-specific match over universal.
        Returns None if no skill matches.
        """
        self._ensure_loaded()
        dept_match      = None
        universal_match = None

        for skill in self._skills.values():
            if not skill.matches(query):
                continue
            if dept_id and skill.dept_id == dept_id:
                dept_match = skill
                break   # exact dept match wins
            if skill.dept_id == "all":
                universal_match = skill

        result = dept_match or universal_match
        if result:
            logger.info(f"[SkillRegistry] Detected skill '{result.skill_id}' for query='{query[:60]}'")
        return result

    async def execute(
        self,
        skill_id: str,
        context:  ProjectContext,
        params:   dict = None,
    ) -> SkillOutput:
        """
        Execute a skill by ID.
        Returns an error SkillOutput if skill_id is unknown.
        """
        self._ensure_loaded()
        skill = self._skills.get(skill_id)
        if not skill:
            return SkillOutput(
                skill_id    = skill_id,
                dept_id     = "unknown",
                title       = "Unknown Skill",
                error       = f"Skill '{skill_id}' not found in registry",
            )
        try:
            logger.info(f"[SkillRegistry] Executing {skill_id} for project={context.project_id[:8]}")
            return await skill.execute(context, params or {})
        except Exception as e:
            logger.error(f"[SkillRegistry] Skill {skill_id} failed: {e}")
            return SkillOutput(
                skill_id    = skill_id,
                dept_id     = skill.dept_id,
                title       = skill.title_template,
                file_format = skill.output_format,
                error       = str(e),
            )


# ── Loader — imports all skill modules so they self-register ─────────────────

def _load_all_skills(registry: SkillRegistry) -> None:
    """Import all skill modules to trigger their registration."""
    skill_modules = [
        # Universal (Phase 6)
        "agents.skills.universal.report_skill",
        "agents.skills.universal.presentation_skill",
        "agents.skills.universal.export_skill",
        "agents.skills.universal.dashboard_skill",
        "agents.skills.universal.status_update_skill",
        # Universal (Phase 7 — Business Layer)
        "agents.skills.universal.org_overview_skill",
        "agents.skills.universal.exec_dashboard_skill",
        "agents.skills.universal.audit_report_skill",
        # Finance
        "agents.skills.dept.finance.budget_variance_skill",
        "agents.skills.dept.finance.pl_statement_skill",
        "agents.skills.dept.finance.board_presentation_skill",
        # Sales
        "agents.skills.dept.sales.pipeline_health_skill",
        "agents.skills.dept.sales.weekly_forecast_skill",
        # HR
        "agents.skills.dept.hr.headcount_skill",
        # IT
        "agents.skills.dept.it.sprint_review_skill",
        "agents.skills.dept.it.system_health_skill",
    ]

    for mod_path in skill_modules:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            # Each module calls registry.register(SkillClass()) at module level
            if hasattr(mod, "_register"):
                mod._register(registry)
            logger.debug(f"[SkillRegistry] Loaded: {mod_path}")
        except ImportError as e:
            logger.warning(f"[SkillRegistry] Could not load {mod_path}: {e}")
        except Exception as e:
            logger.warning(f"[SkillRegistry] Error in {mod_path}: {e}")


# ── Singleton factory ─────────────────────────────────────────────────────────

def get_skill_registry() -> SkillRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = SkillRegistry()
    return _registry_instance
