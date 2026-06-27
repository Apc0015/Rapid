"""
Universal Skill: Status Update (Text)

Generates a concise, formatted text status update ready to paste into
an email, Slack message, or Teams post.

Output includes:
  - Project name + health badge
  - Key metrics (budget %, milestone count, open risks)
  - Top 3 KPIs
  - Next upcoming milestone
  - Pending actions count

Trigger phrases: "status update", "weekly update", "write an update",
                 "summary for the team", "standup update"
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from typing import Any

from agents.skills.base_skill import BaseSkill, SkillOutput
from infrastructure.project_context import ProjectContext

logger = logging.getLogger(__name__)

_HEALTH_EMOJI = {
    "on_track":  "🟢",
    "at_risk":   "🟡",
    "off_track": "🔴",
    "healthy":   "🟢",
    "critical":  "🔴",
}


class StatusUpdateSkill(BaseSkill):
    skill_id        = "status_update"
    dept_id         = "all"
    title_template  = "{project_name} — Status Update"
    description     = "Generate a concise text status update ready to paste into email, Slack, or Teams."
    output_format   = "text"
    trigger_phrases = [
        "status update", "weekly update", "write an update",
        "summary for the team", "team update", "standup update",
        "write me an update", "what's the status", "quick summary",
        "project summary", "send an update",
    ]

    async def execute(self, context: ProjectContext, params: dict[str, Any] = None) -> SkillOutput:
        params = params or {}
        title  = params.get("title") or self._make_title(context)

        try:
            db_path = getattr(context, "db_path", None)

            proj_info  = {}
            kpis       = []
            milestones = []
            risks      = []
            actions_n  = 0

            if db_path and os.path.exists(db_path):
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
                conn.row_factory = sqlite3.Row
                try:
                    r = conn.execute("SELECT * FROM project_details LIMIT 1").fetchone()
                    if r:
                        proj_info = dict(r)

                    kpis = [dict(r) for r in conn.execute(
                        "SELECT name, current_value, target_value, unit, status "
                        "FROM project_kpis ORDER BY status DESC LIMIT 5"
                    ).fetchall()]

                    milestones = [dict(r) for r in conn.execute(
                        "SELECT name, due_date, status FROM project_milestones "
                        "WHERE status != 'completed' ORDER BY due_date ASC LIMIT 3"
                    ).fetchall()]

                    r2 = conn.execute(
                        "SELECT COUNT(*) cnt FROM project_risks WHERE status='open'"
                    ).fetchone()
                    risks_count = r2["cnt"] if r2 else 0

                    r3 = conn.execute(
                        "SELECT COUNT(*) cnt FROM agent_action_queue WHERE status='pending'"
                    ).fetchone()
                    actions_n = r3["cnt"] if r3 else 0
                finally:
                    conn.close()

            now       = datetime.utcnow().strftime("%B %d, %Y")
            proj_name = proj_info.get("name") or context.project_id[:12]
            health    = proj_info.get("health_status") or "unknown"
            emoji     = _HEALTH_EMOJI.get(health.lower(), "⚪")

            budget_tot = proj_info.get("budget_total") or 0
            budget_spt = proj_info.get("budget_spent") or 0
            budget_pct = f"{budget_spt / budget_tot * 100:.1f}%" if budget_tot else "N/A"

            lines = [
                f"📊 **{proj_name} — Status Update** ({now})",
                f"",
                f"**Health:** {emoji} {health.replace('_', ' ').title()}",
                f"**Budget Used:** {budget_pct} (${budget_spt:,.0f} of ${budget_tot:,.0f})",
                f"**Open Risks:** {risks_count}",
                f"**Pending Approvals:** {actions_n}",
                f"",
            ]

            if kpis:
                lines.append("**Key Metrics:**")
                for k in kpis[:3]:
                    status_mark = {"on_track": "✅", "at_risk": "⚠️", "off_track": "❌"}.get(
                        str(k.get("status") or "").lower(), "•"
                    )
                    lines.append(
                        f"  {status_mark} {k.get('name')}: "
                        f"{k.get('current_value') or '—'} {k.get('unit') or ''} "
                        f"(target: {k.get('target_value') or '—'})"
                    )
                lines.append("")

            if milestones:
                lines.append("**Upcoming Milestones:**")
                for m in milestones:
                    lines.append(f"  • {m.get('name')} — due {m.get('due_date') or 'TBD'} [{m.get('status')}]")
                lines.append("")

            if actions_n:
                lines.append(f"⏳ **{actions_n} action(s) awaiting your review** in RAPID.")
                lines.append("")

            lines.append("_Generated by RAPID Project Intelligence_")
            text = "\n".join(lines)

            return SkillOutput(
                skill_id    = self.skill_id,
                dept_id     = self.dept_id,
                title       = title,
                file_format = "text",
                content     = text,
                preview     = text[:300],
                pages       = 1,
            )

        except Exception as e:
            logger.error(f"[StatusUpdateSkill] Failed: {e}")
            return SkillOutput(
                skill_id    = self.skill_id,
                dept_id     = self.dept_id,
                title       = title,
                file_format = "text",
                error       = str(e),
            )


# ── Self-registration ─────────────────────────────────────────────────────────

def _register(registry) -> None:
    registry.register(StatusUpdateSkill())
