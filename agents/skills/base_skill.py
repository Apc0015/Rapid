"""
agents/skills/base_skill.py — Base class for all RAPID agent skills.

Every skill — universal or department-specific — inherits from BaseSkill.

A skill takes a ProjectContext (the project's live data environment) plus
optional caller-supplied parameters, and produces a SkillOutput containing
the generated file path and metadata.

The skill pipeline:
  1. Skill is selected (by SkillRegistry or explicit call)
  2. execute(context, params) is called
  3. Skill fetches its data via context's DB connection or ProjectContextManager
  4. Skill generates the output file (DOCX / PPTX / XLSX / HTML / text)
  5. Returns SkillOutput with file_path, title, format, and preview text
  6. Caller (coordinator or router) enqueues an action for human review
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from infrastructure.project_context import ProjectContext


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class SkillOutput:
    """
    Result produced by a skill execution.

    file_path   — Absolute path to the generated file (None for text-only skills)
    content     — Text content (for status_update or HTML dashboard inline)
    title       — Human-readable title of the output
    file_format — docx | pptx | xlsx | html | text
    skill_id    — Which skill produced this
    dept_id     — Which department
    preview     — First 500 chars of narrative, for action queue display
    pages       — Estimated page / slide count
    error       — Set if generation failed
    created_at  — ISO timestamp
    """
    skill_id:    str
    dept_id:     str
    title:       str
    file_format: str            = "text"
    file_path:   Optional[str]  = None
    content:     str            = ""
    preview:     str            = ""
    pages:       int            = 0
    error:       Optional[str]  = None
    created_at:  str            = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict:
        return {
            "skill_id":    self.skill_id,
            "dept_id":     self.dept_id,
            "title":       self.title,
            "file_format": self.file_format,
            "file_path":   self.file_path,
            "preview":     self.preview,
            "pages":       self.pages,
            "error":       self.error,
            "created_at":  self.created_at,
            "success":     self.success,
        }


# ── BaseSkill ─────────────────────────────────────────────────────────────────

class BaseSkill(ABC):
    """
    Abstract base class for all RAPID skills.

    Subclasses must implement:
      - skill_id   : str  — unique identifier (e.g. "budget_variance_report")
      - dept_id    : str  — which department owns this skill ("finance", "all")
      - title_template : str — e.g. "{project_name} — Budget Variance Report"
      - description : str — shown in /skills/available
      - output_format : str — docx | pptx | xlsx | html | text
      - trigger_phrases : list[str] — phrases that auto-detect this skill
      - execute(context, params) → SkillOutput
    """

    skill_id:        str = ""
    dept_id:         str = "all"
    title_template:  str = "Output"
    description:     str = ""
    output_format:   str = "docx"
    trigger_phrases: list[str] = []

    # ── Public interface ──────────────────────────────────────────────────────

    @abstractmethod
    async def execute(
        self,
        context: ProjectContext,
        params:  dict[str, Any] = None,
    ) -> SkillOutput:
        """
        Generate the skill output for the given project context.

        params — optional caller overrides (e.g. date range, title override)
        """

    def matches(self, query: str) -> bool:
        """
        Return True if the query matches any trigger phrase (case-insensitive).
        Used by SkillRegistry for auto-detection.
        """
        q = query.lower()
        return any(phrase.lower() in q for phrase in self.trigger_phrases)

    def _make_title(self, context: ProjectContext, override: Optional[str] = None) -> str:
        if override:
            return override
        name = getattr(context, "project_name", None) or context.project_id[:8]
        return self.title_template.replace("{project_name}", name)

    def _output_dir(self, context: ProjectContext) -> str:
        """Return the output directory path for this project's documents."""
        import os
        base = os.path.join(
            "data", "documents", "projects",
            context.tenant_id, context.project_id,
        )
        os.makedirs(base, exist_ok=True)
        return base

    def _safe_execute(self, context: ProjectContext, params: dict) -> SkillOutput:
        """Sync wrapper for execute — catches exceptions and returns error SkillOutput."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.execute(context, params or {}))
        except Exception as e:
            return SkillOutput(
                skill_id    = self.skill_id,
                dept_id     = self.dept_id,
                title       = self._make_title(context),
                file_format = self.output_format,
                error       = str(e),
            )
