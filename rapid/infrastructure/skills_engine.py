from __future__ import annotations
"""
skills_engine.py — Makes config.yaml skills executable.

Skills are defined in departments/*/config.yaml under the `skills` section.
Each skill has: id, trigger_phrases, output_format.

The SkillsEngine:
  1. detect(query, dept_id) — scans query against trigger phrases → returns skill_id or None
  2. execute(skill_id, dept_id, dept_results) — formats NL results per the skill's output_format

output_format values:
  structured_table         → markdown table
  narrative_with_numbers   → paragraph with embedded numbers
  table_with_chart_data    → markdown table + JSON chart hint
  executive_summary        → board-level paragraph
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml

from models.nl_result import NLResult

logger = logging.getLogger(__name__)

_DEPT_CONFIG_BASE = Path("departments")


@dataclass
class SkillResult:
    skill_id:     str
    dept_id:      str
    content:      str          # formatted output
    output_format: str
    confidence:   float


class SkillsEngine:
    """
    Singleton — loaded once.
    Reads skill definitions from config.yaml; executes them on NL summaries.
    """

    def __init__(self) -> None:
        # Cache: dept_id → flat list of skill dicts
        self._skills_cache: dict[str, List[dict]] = {}

    # ── Detection ─────────────────────────────────────────────────────────────

    def detect(self, query: str, dept_id: str) -> Optional[str]:
        """
        Return the first skill_id whose trigger_phrases match the query, or None.
        Case-insensitive substring match.
        """
        q = query.lower()
        for skill in self._get_skills(dept_id):
            for phrase in skill.get("trigger_phrases", []):
                if phrase.lower() in q:
                    logger.info(f"SkillsEngine: skill '{skill['id']}' triggered for dept={dept_id}")
                    return skill["id"]
        return None

    # ── Execution ─────────────────────────────────────────────────────────────

    async def execute(
        self,
        skill_id: str,
        dept_id: str,
        dept_results: List[NLResult],
        user_permissions: dict,
    ) -> SkillResult:
        """
        Format the dept_results according to the skill's output_format.
        Uses LLM to structure the output.
        """
        skill = self._find_skill(skill_id, dept_id)
        if skill is None:
            return SkillResult(
                skill_id=skill_id, dept_id=dept_id,
                content="Skill not found.", output_format="narrative_with_numbers",
                confidence=0.1,
            )

        output_format = skill.get("output_format", "narrative_with_numbers")
        combined_nl = "\n\n".join(
            f"[{r.dept_tag.upper()}]: {r.summary}" for r in dept_results if r.summary
        )
        avg_confidence = (
            sum(r.confidence for r in dept_results) / len(dept_results)
            if dept_results else 0.3
        )

        formatted = await self._format(
            skill_name=skill.get("name", skill_id),
            output_format=output_format,
            nl_content=combined_nl,
        )

        return SkillResult(
            skill_id=skill_id,
            dept_id=dept_id,
            content=formatted,
            output_format=output_format,
            confidence=round(avg_confidence, 3),
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _get_skills(self, dept_id: str) -> List[dict]:
        """Load and cache all skills for a dept from config.yaml."""
        if dept_id not in self._skills_cache:
            cfg_path = _DEPT_CONFIG_BASE / dept_id / "config.yaml"
            skills: List[dict] = []
            if cfg_path.exists():
                try:
                    cfg = yaml.safe_load(cfg_path.read_text()) or {}
                    skills_cfg = cfg.get("skills", {})
                    # Flatten all skill categories into one list
                    for category_skills in skills_cfg.values():
                        if isinstance(category_skills, list):
                            skills.extend(category_skills)
                except Exception as e:
                    logger.error(f"SkillsEngine: failed to load skills for {dept_id}: {e}")
            self._skills_cache[dept_id] = skills
        return self._skills_cache[dept_id]

    def _find_skill(self, skill_id: str, dept_id: str) -> Optional[dict]:
        return next(
            (s for s in self._get_skills(dept_id) if s.get("id") == skill_id), None
        )

    async def _format(self, skill_name: str, output_format: str, nl_content: str) -> str:
        """Use LLM to format the NL content per the skill's output_format."""
        from infrastructure.llm_client import get_llm
        llm = get_llm()

        format_instructions = {
            "structured_table": (
                "Format the information as a clean markdown table. "
                "Include headers, align columns, show numbers with 2 decimal places. "
                "Add a one-line summary below the table."
            ),
            "narrative_with_numbers": (
                "Write a clear narrative paragraph. Lead with the most important number. "
                "Embed all key figures inline. End with one implication or recommendation."
            ),
            "table_with_chart_data": (
                "First produce a markdown table. Then on a new line output a JSON object "
                "with key 'chart_data' containing labels and values arrays suitable for a bar chart."
            ),
            "executive_summary": (
                "Write one executive summary paragraph (max 5 sentences). "
                "Lead with the key insight, include the most important number, "
                "flag any risk, end with a recommended action."
            ),
        }.get(output_format, "Summarise the information clearly and concisely.")

        system = (
            f"You are formatting a '{skill_name}' output. "
            f"{format_instructions} "
            "Use only the information provided. Do not invent data."
        )
        prompt = f"Information to format:\n\n{nl_content}"

        try:
            return await llm.complete(prompt, system=system)
        except Exception as exc:
            logger.error(f"SkillsEngine: format failed: {exc!r}")
            return nl_content


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[SkillsEngine] = None


def get_skills_engine() -> SkillsEngine:
    global _engine
    if _engine is None:
        _engine = SkillsEngine()
    return _engine
