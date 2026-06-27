"""
Universal Skill: HTML Dashboard

Generates a self-contained, single-file HTML dashboard with:
  - Project health badge (green/amber/red)
  - KPI cards with sparkline bars
  - Milestone progress table
  - Budget utilization bar
  - Risk heatmap table
  - Pending actions list

The HTML file is fully standalone (no external dependencies).
Can be opened in any browser or embedded in RAPID's frontend.

Trigger phrases: "dashboard", "html dashboard", "live view",
                 "project overview", "status page"
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from agents.skills.base_skill import BaseSkill, SkillOutput
from infrastructure.project_context import ProjectContext

logger = logging.getLogger(__name__)

_STATUS_BADGE = {
    "on_track":  ("#27ae60", "On Track"),
    "at_risk":   ("#e67e22", "At Risk"),
    "off_track": ("#c0392b", "Off Track"),
    "healthy":   ("#27ae60", "Healthy"),
    "critical":  ("#c0392b", "Critical"),
}

_SEVERITY_COLOR = {
    "low":      "#27ae60",
    "medium":   "#e67e22",
    "high":     "#c0392b",
    "critical": "#8e44ad",
}


def _badge(status: str) -> str:
    color, label = _STATUS_BADGE.get(status.lower(), ("#7f8c8d", status.title()))
    return f'<span style="background:{color};color:#fff;padding:3px 12px;border-radius:12px;font-weight:bold;font-size:13px;">{label}</span>'


def _kpi_card(name, current, target, unit, status) -> str:
    color, _ = _STATUS_BADGE.get(str(status or "").lower(), ("#7f8c8d", ""))
    pct = 0
    try:
        pct = min(100, int(float(current or 0) / float(target or 1) * 100))
    except Exception:
        pass
    return f"""
    <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:16px;min-width:180px;flex:1;">
      <div style="color:#666;font-size:12px;text-transform:uppercase;letter-spacing:1px;">{name}</div>
      <div style="color:#1a1a1a;font-size:28px;font-weight:bold;margin:6px 0;">{current or '—'} <span style="font-size:14px;color:#999;">{unit or ''}</span></div>
      <div style="color:#999;font-size:12px;">Target: {target or '—'} {unit or ''}</div>
      <div style="background:#f0f0f0;border-radius:4px;height:6px;margin-top:10px;">
        <div style="background:{color};width:{pct}%;height:6px;border-radius:4px;"></div>
      </div>
      <div style="text-align:right;font-size:11px;color:{color};margin-top:4px;">{pct}%</div>
    </div>"""


def _milestone_row(m, idx) -> str:
    status = str(m.get("status") or "")
    color, _ = _STATUS_BADGE.get(status.lower(), ("#7f8c8d", status))
    bg = "#f8f9fa" if idx % 2 == 0 else "#fff"
    return (
        f'<tr style="background:{bg};">'
        f'<td style="padding:8px 12px;">{m.get("name","")}</td>'
        f'<td style="padding:8px 12px;">{m.get("due_date","TBD")}</td>'
        f'<td style="padding:8px 12px;">{m.get("owner","—")}</td>'
        f'<td style="padding:8px 12px;"><span style="color:{color};font-weight:bold;">{status}</span></td>'
        f'</tr>'
    )


def _risk_row(r, idx) -> str:
    sev   = str(r.get("severity") or "").lower()
    color = _SEVERITY_COLOR.get(sev, "#7f8c8d")
    bg    = "#f8f9fa" if idx % 2 == 0 else "#fff"
    return (
        f'<tr style="background:{bg};">'
        f'<td style="padding:8px 12px;">{r.get("title","")}</td>'
        f'<td style="padding:8px 12px;"><span style="color:{color};font-weight:bold;">{sev.upper()}</span></td>'
        f'<td style="padding:8px 12px;">{r.get("impact","")}</td>'
        f'<td style="padding:8px 12px;">{r.get("likelihood","")}</td>'
        f'<td style="padding:8px 12px;">{r.get("owner","—")}</td>'
        f'</tr>'
    )


class DashboardSkill(BaseSkill):
    skill_id        = "html_dashboard"
    dept_id         = "all"
    title_template  = "{project_name} — Live Dashboard"
    description     = "Generate a self-contained HTML dashboard: health, KPIs, milestones, budget, risks, actions."
    output_format   = "html"
    trigger_phrases = [
        "dashboard", "html dashboard", "live view", "project overview",
        "status page", "create dashboard", "generate dashboard",
        "visual summary", "project dashboard",
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
            actions    = []

            if db_path and os.path.exists(db_path):
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
                conn.row_factory = sqlite3.Row
                try:
                    r = conn.execute("SELECT * FROM project_details LIMIT 1").fetchone()
                    if r:
                        proj_info = dict(r)

                    kpis = [dict(r) for r in conn.execute(
                        "SELECT name, current_value, target_value, unit, status "
                        "FROM project_kpis ORDER BY status DESC LIMIT 8"
                    ).fetchall()]

                    milestones = [dict(r) for r in conn.execute(
                        "SELECT name, due_date, owner, status "
                        "FROM project_milestones ORDER BY due_date ASC LIMIT 10"
                    ).fetchall()]

                    risks = [dict(r) for r in conn.execute(
                        "SELECT title, severity, impact, likelihood, owner "
                        "FROM project_risks WHERE status='open' ORDER BY severity DESC LIMIT 8"
                    ).fetchall()]

                    actions = [dict(r) for r in conn.execute(
                        "SELECT title, priority, status FROM agent_action_queue "
                        "WHERE status='pending' ORDER BY priority DESC LIMIT 5"
                    ).fetchall()]
                finally:
                    conn.close()

            now         = datetime.utcnow().strftime("%B %d, %Y %H:%M UTC")
            proj_name   = proj_info.get("name") or context.project_id[:16]
            health      = proj_info.get("health_status") or "unknown"
            budget_tot  = proj_info.get("budget_total") or 0
            budget_spt  = proj_info.get("budget_spent") or 0
            budget_pct  = int(budget_spt / budget_tot * 100) if budget_tot else 0
            budget_color = "#27ae60" if budget_pct < 80 else ("#e67e22" if budget_pct < 95 else "#c0392b")

            # KPI cards
            kpi_cards_html = '<div style="display:flex;flex-wrap:wrap;gap:16px;">'
            for k in kpis:
                kpi_cards_html += _kpi_card(k.get("name"), k.get("current_value"),
                                            k.get("target_value"), k.get("unit"), k.get("status"))
            kpi_cards_html += "</div>"

            # Milestone rows
            ms_rows = "".join(_milestone_row(m, i) for i, m in enumerate(milestones))

            # Risk rows
            risk_rows = "".join(_risk_row(r, i) for i, r in enumerate(risks))

            # Action list
            action_items = ""
            priority_colors = {"urgent": "#c0392b", "high": "#e67e22", "medium": "#3498db", "low": "#27ae60"}
            for a in actions:
                pc = priority_colors.get(str(a.get("priority") or "").lower(), "#7f8c8d")
                action_items += (
                    f'<li style="padding:6px 0;border-bottom:1px solid #f0f0f0;">'
                    f'<span style="background:{pc};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;margin-right:8px;">'
                    f'{str(a.get("priority") or "").upper()}</span>{a.get("title","")}</li>'
                )

            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #1a1a1a; }}
  .header {{ background: #1F3564; color: white; padding: 24px 32px; }}
  .header h1 {{ font-size: 26px; font-weight: 700; }}
  .header p {{ color: #ccc; font-size: 13px; margin-top: 4px; }}
  .content {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
  .section {{ background: #fff; border-radius: 10px; border: 1px solid #e0e0e0; margin-bottom: 24px; padding: 24px; }}
  .section h2 {{ font-size: 18px; color: #1F3564; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #2E75B6; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #1F3564; color: white; padding: 10px 12px; text-align: left; }}
  td {{ padding: 8px 12px; }}
  .budget-bar {{ height: 18px; background: #e0e0e0; border-radius: 9px; overflow: hidden; }}
  .budget-fill {{ height: 18px; background: {budget_color}; border-radius: 9px; width: {budget_pct}%; transition: width 0.3s; }}
  ul {{ list-style: none; padding: 0; }}
  .footer {{ text-align: center; color: #999; font-size: 12px; padding: 24px; }}
</style>
</head>
<body>

<div class="header">
  <h1>📊 {proj_name}</h1>
  <p>Generated by RAPID · {now} &nbsp;|&nbsp; {_badge(health)}</p>
</div>

<div class="content">

  <!-- Summary row -->
  <div style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;">
    <div class="section" style="flex:1;min-width:200px;padding:16px;">
      <div style="color:#666;font-size:12px;text-transform:uppercase;">Status</div>
      <div style="font-size:22px;font-weight:bold;margin-top:6px;">{proj_info.get('status','—').title()}</div>
    </div>
    <div class="section" style="flex:1;min-width:200px;padding:16px;">
      <div style="color:#666;font-size:12px;text-transform:uppercase;">Target End</div>
      <div style="font-size:22px;font-weight:bold;margin-top:6px;">{proj_info.get('target_end_date','—')}</div>
    </div>
    <div class="section" style="flex:1;min-width:200px;padding:16px;">
      <div style="color:#666;font-size:12px;text-transform:uppercase;">Open Risks</div>
      <div style="font-size:22px;font-weight:bold;margin-top:6px;">{len(risks)}</div>
    </div>
    <div class="section" style="flex:1;min-width:200px;padding:16px;">
      <div style="color:#666;font-size:12px;text-transform:uppercase;">Pending Actions</div>
      <div style="font-size:22px;font-weight:bold;margin-top:6px;">{len(actions)}</div>
    </div>
  </div>

  <!-- Budget -->
  <div class="section">
    <h2>💰 Budget Utilization</h2>
    <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:13px;">
      <span>Spent: <strong>${budget_spt:,.0f}</strong></span>
      <span>Total: <strong>${budget_tot:,.0f}</strong></span>
      <span style="color:{budget_color};font-weight:bold;">{budget_pct}% used</span>
    </div>
    <div class="budget-bar"><div class="budget-fill"></div></div>
  </div>

  <!-- KPIs -->
  <div class="section">
    <h2>📈 Key Performance Indicators</h2>
    {kpi_cards_html if kpis else '<p style="color:#999;">No KPIs configured for this project.</p>'}
  </div>

  <!-- Milestones -->
  <div class="section">
    <h2>🎯 Milestones</h2>
    {'<table><thead><tr><th>Milestone</th><th>Due Date</th><th>Owner</th><th>Status</th></tr></thead><tbody>' + ms_rows + '</tbody></table>' if milestones else '<p style="color:#999;">No milestones configured.</p>'}
  </div>

  <!-- Risks -->
  <div class="section">
    <h2>⚠️ Open Risks</h2>
    {'<table><thead><tr><th>Risk</th><th>Severity</th><th>Impact</th><th>Likelihood</th><th>Owner</th></tr></thead><tbody>' + risk_rows + '</tbody></table>' if risks else '<p style="color:#999;">No open risks.</p>'}
  </div>

  <!-- Pending Actions -->
  <div class="section">
    <h2>⏳ Pending Actions</h2>
    {'<ul>' + action_items + '</ul>' if actions else '<p style="color:#999;">No pending actions.</p>'}
  </div>

</div>
<div class="footer">RAPID · Project Intelligence Platform · {now}</div>
</body>
</html>"""

            # Save
            out_dir  = self._output_dir(context)
            filename = f"dashboard_{uuid.uuid4().hex[:8]}.html"
            out_path = os.path.join(out_dir, filename)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)

            return SkillOutput(
                skill_id    = self.skill_id,
                dept_id     = self.dept_id,
                title       = title,
                file_format = self.output_format,
                file_path   = out_path,
                content     = html,
                preview     = f"HTML dashboard: {len(kpis)} KPIs, {len(milestones)} milestones, {len(risks)} risks.",
                pages       = 1,
            )

        except Exception as e:
            logger.error(f"[DashboardSkill] Failed: {e}", exc_info=True)
            return SkillOutput(
                skill_id    = self.skill_id,
                dept_id     = self.dept_id,
                title       = title,
                file_format = self.output_format,
                error       = str(e),
            )


# ── Self-registration ─────────────────────────────────────────────────────────

def _register(registry) -> None:
    registry.register(DashboardSkill())
