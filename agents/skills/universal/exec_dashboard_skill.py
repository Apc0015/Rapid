"""
Universal Skill: Executive Dashboard (HTML)

Board-ready, self-contained HTML dashboard pulling live data from all
active projects in the tenant. Renders a visual summary with:
  - KPI health cards
  - Project status grid
  - Risk heat summary
  - Department headcount bar

Trigger phrases: "executive dashboard", "board dashboard", "exec dashboard",
                 "c-suite dashboard", "leadership dashboard", "board report"
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


class ExecDashboardSkill(BaseSkill):
    skill_id        = "exec_dashboard"
    dept_id         = "all"
    title_template  = "{project_name} — Executive Dashboard"
    description     = "Universal: Generate a board-ready HTML executive dashboard aggregating all tenant project data."
    output_format   = "html"
    trigger_phrases = [
        "executive dashboard", "board dashboard", "exec dashboard",
        "c-suite dashboard", "leadership dashboard", "board report",
        "executive report", "board summary", "exec report",
        "leadership overview", "ceo dashboard",
    ]

    async def execute(self, context: ProjectContext, params: dict[str, Any] = None) -> SkillOutput:
        params = params or {}
        title  = params.get("title") or self._make_title(context)

        try:
            import config

            # ── Gather tenant-wide data ───────────────────────────────────────
            # projects table has name/status/dept; project_registry has db_path
            reg_conn = sqlite3.connect(config.DB_PATH, timeout=10)
            reg_conn.row_factory = sqlite3.Row
            projects = [dict(r) for r in reg_conn.execute(
                """
                SELECT pr.project_id,
                       COALESCE(p.name, pr.project_id)  AS name,
                       COALESCE(p.status, pr.status)    AS status,
                       COALESCE(p.primary_dept_id, '')  AS dept_id,
                       pr.db_path
                FROM project_registry pr
                LEFT JOIN projects p ON pr.project_id = p.project_id
                WHERE pr.tenant_id=? AND pr.status != 'archived'
                """,
                (context.tenant_id,),
            ).fetchall()]
            reg_conn.close()

            all_kpis:  list[dict] = []
            all_risks: list[dict] = []
            status_counts = {"active": 0, "at_risk": 0, "off_track": 0, "completed": 0, "other": 0}

            for proj in projects:
                st = (proj.get("status") or "other").lower().replace("-","_")
                status_counts[st if st in status_counts else "other"] += 1
                db_path = proj.get("db_path") or ""
                if not db_path or not os.path.exists(db_path):
                    continue
                try:
                    pconn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
                    pconn.row_factory = sqlite3.Row
                    for r in pconn.execute(
                        "SELECT name, current_value, target_value, unit, status FROM project_kpis LIMIT 4"
                    ).fetchall():
                        k = dict(r); k["project"] = proj.get("name","")[:20]
                        all_kpis.append(k)
                    for r in pconn.execute(
                        "SELECT title, severity, status FROM project_risks WHERE severity IN ('high','critical') LIMIT 3"
                    ).fetchall():
                        rk = dict(r); rk["project"] = proj.get("name","")[:20]
                        all_risks.append(rk)
                    pconn.close()
                except Exception:
                    pass

            headcount: dict[str, int] = {}
            try:
                from infrastructure.people_directory import get_people_directory
                headcount = get_people_directory().dept_headcount(context.tenant_id)
            except Exception:
                pass

            # ── Build HTML ────────────────────────────────────────────────────
            now = datetime.utcnow().strftime("%B %d, %Y %H:%M UTC")
            total_projects = len(projects)
            critical_count = len([r for r in all_risks if (r.get("severity","")).lower() == "critical"])
            off_track_count = status_counts.get("off_track", 0) + status_counts.get("at_risk", 0)

            def status_color(st: str) -> str:
                st = (st or "").lower()
                if st in ("active","on_track","completed"): return "#22c55e"
                if st in ("at_risk",):                      return "#f59e0b"
                if st in ("off_track",):                    return "#ef4444"
                return "#6b7280"

            # KPI cards HTML
            kpi_cards = ""
            for k in all_kpis[:8]:
                sc = status_color(k.get("status",""))
                kpi_cards += f"""
                <div class="kpi-card">
                  <div class="kpi-label">{k.get('name','')[:28]}</div>
                  <div class="kpi-project">{k.get('project','')}</div>
                  <div class="kpi-value" style="color:{sc}">
                    {k.get('current_value','—')} <span class="kpi-unit">{k.get('unit','')}</span>
                  </div>
                  <div class="kpi-target">Target: {k.get('target_value','—')} {k.get('unit','')}</div>
                </div>"""

            # Project status rows
            proj_rows = ""
            for proj in projects[:12]:
                st  = (proj.get("status") or "active").replace("_"," ").title()
                sc  = status_color(proj.get("status",""))
                proj_rows += f"""
                <tr>
                  <td>{proj.get('name','')[:30]}</td>
                  <td>{proj.get('dept_id') or '—'}</td>
                  <td><span class="badge" style="background:{sc}">{st}</span></td>
                </tr>"""

            # Risk rows
            risk_rows = ""
            for r in all_risks[:8]:
                sc = "#ef4444" if (r.get("severity","")).lower() == "critical" else "#f59e0b"
                risk_rows += f"""
                <tr>
                  <td>{r.get('title','')[:40]}</td>
                  <td>{r.get('project','')}</td>
                  <td><span class="badge" style="background:{sc}">{r.get('severity','').upper()}</span></td>
                </tr>"""

            # Headcount bars
            hc_bars = ""
            max_hc = max(headcount.values(), default=1)
            for dept, cnt in sorted(headcount.items(), key=lambda x: -x[1])[:8]:
                pct = int(cnt / max_hc * 100)
                hc_bars += f"""
                <div class="hc-row">
                  <div class="hc-label">{dept}</div>
                  <div class="hc-bar-wrap">
                    <div class="hc-bar" style="width:{pct}%"></div>
                  </div>
                  <div class="hc-count">{cnt}</div>
                </div>"""

            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --primary:#1F3564; --accent:#2563EB; --success:#22c55e;
    --warning:#f59e0b; --danger:#ef4444; --bg:#f8fafc; --card:#fff;
    --text:#1e293b; --muted:#64748b; --border:#e2e8f0;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);font-size:14px}}
  header{{background:var(--primary);color:#fff;padding:18px 32px;display:flex;justify-content:space-between;align-items:center}}
  header h1{{font-size:20px;font-weight:700}}
  header .sub{{font-size:12px;opacity:.8}}
  .container{{max-width:1200px;margin:0 auto;padding:24px 16px}}
  .summary-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
  .summary-card{{background:var(--card);border-radius:8px;padding:20px;border:1px solid var(--border);text-align:center}}
  .summary-card .num{{font-size:36px;font-weight:800;line-height:1}}
  .summary-card .label{{font-size:12px;color:var(--muted);margin-top:6px;text-transform:uppercase;letter-spacing:.05em}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}}
  .card{{background:var(--card);border-radius:8px;border:1px solid var(--border);overflow:hidden}}
  .card-header{{background:var(--primary);color:#fff;padding:12px 16px;font-weight:600;font-size:13px}}
  table{{width:100%;border-collapse:collapse}}
  th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid var(--border);font-size:12px}}
  tr:nth-child(even){{background:#f1f5f9}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:12px;color:#fff;font-size:11px;font-weight:600}}
  .kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
  .kpi-card{{background:var(--card);border-radius:8px;padding:14px;border:1px solid var(--border)}}
  .kpi-label{{font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;margin-bottom:2px}}
  .kpi-project{{font-size:10px;color:#94a3b8;margin-bottom:6px}}
  .kpi-value{{font-size:22px;font-weight:800}}
  .kpi-unit{{font-size:11px;font-weight:400;color:var(--muted)}}
  .kpi-target{{font-size:10px;color:var(--muted);margin-top:4px}}
  .hc-row{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
  .hc-label{{width:90px;font-size:11px;color:var(--muted);text-align:right;flex-shrink:0}}
  .hc-bar-wrap{{flex:1;background:#e2e8f0;border-radius:4px;height:14px}}
  .hc-bar{{background:var(--accent);height:14px;border-radius:4px;transition:width .3s}}
  .hc-count{{width:30px;text-align:right;font-size:11px;font-weight:700}}
  footer{{text-align:center;color:var(--muted);font-size:11px;padding:20px;border-top:1px solid var(--border)}}
  @media(max-width:768px){{
    .summary-grid,.grid2,.kpi-grid{{grid-template-columns:1fr 1fr}}
  }}
</style>
</head>
<body>
<header>
  <div>
    <h1>RAPID Executive Dashboard</h1>
    <div class="sub">{title}</div>
  </div>
  <div class="sub">{now}</div>
</header>

<div class="container">

  <!-- Summary strip -->
  <div class="summary-grid">
    <div class="summary-card">
      <div class="num" style="color:var(--accent)">{total_projects}</div>
      <div class="label">Total Projects</div>
    </div>
    <div class="summary-card">
      <div class="num" style="color:var(--success)">{status_counts.get('active',0)}</div>
      <div class="label">Active</div>
    </div>
    <div class="summary-card">
      <div class="num" style="color:var(--warning)">{off_track_count}</div>
      <div class="label">At Risk / Off-Track</div>
    </div>
    <div class="summary-card">
      <div class="num" style="color:var(--danger)">{critical_count}</div>
      <div class="label">Critical Risks</div>
    </div>
  </div>

  <!-- KPI strip -->
  {'<div class="kpi-grid">' + kpi_cards + '</div>' if kpi_cards else ''}

  <div class="grid2">
    <!-- Project status -->
    <div class="card">
      <div class="card-header">Project Portfolio</div>
      <table>
        <thead><tr><th>Project</th><th>Dept</th><th>Status</th></tr></thead>
        <tbody>{proj_rows or '<tr><td colspan="3">No projects</td></tr>'}</tbody>
      </table>
    </div>

    <!-- Top risks -->
    <div class="card">
      <div class="card-header">Top Risks</div>
      <table>
        <thead><tr><th>Risk</th><th>Project</th><th>Severity</th></tr></thead>
        <tbody>{risk_rows or '<tr><td colspan="3">No critical risks</td></tr>'}</tbody>
      </table>
    </div>
  </div>

  <!-- Headcount -->
  {f'''<div class="card" style="padding:16px">
    <div class="card-header" style="margin:-16px -16px 16px">Department Headcount</div>
    {hc_bars}
  </div>''' if hc_bars else ''}

</div>
<footer>
  Generated by RAPID Executive Intelligence &nbsp;|&nbsp; {now} &nbsp;|&nbsp;
  {total_projects} projects across organisation
</footer>
</body>
</html>"""

            out_dir  = self._output_dir(context)
            filename = f"exec_dashboard_{uuid.uuid4().hex[:8]}.html"
            out_path = os.path.join(out_dir, filename)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)

            return SkillOutput(
                skill_id    = self.skill_id,
                dept_id     = self.dept_id,
                title       = title,
                file_format = self.output_format,
                file_path   = out_path,
                preview     = f"Executive dashboard: {total_projects} projects, {critical_count} critical risks.",
                pages       = 1,
            )

        except Exception as e:
            logger.error(f"[ExecDashboardSkill] Failed: {e}", exc_info=True)
            return SkillOutput(skill_id=self.skill_id, dept_id=self.dept_id,
                               title=title, file_format=self.output_format, error=str(e))


def _register(registry) -> None:
    registry.register(ExecDashboardSkill())
