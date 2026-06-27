"""
infrastructure/monitoring_loop.py — Background Project Monitoring Loop.

Part of RAPID Phase 5 (Human-in-the-Loop). Implements the "Agent Proactivity"
described in blueprint Section 9.

The BackgroundMonitor runs as an asyncio background task started from main.py.
It loops through all active projects and checks for threshold crossings:

  ● Budget alerts    — warns when budget utilization hits 80%, 90%, 100%
  ● Milestone alerts — flags overdue milestones and those due within N days
  ● KPI status drift — detects when a KPI moves from on_track → at_risk → off_track
  ● Risk escalation  — flags new high-impact open risks
  ● Inactivity       — alerts if no activity has been logged in X days

For each alert found:
  1. A Notification is created (in-app, email for high/urgent)
  2. A Category B action is queued (for budget overruns, status changes)
  3. An insight node is written to the knowledge graph (optional, graceful skip)

Configuration (from environment)
─────────────────────────────────
  MONITOR_INTERVAL_SECONDS  — How often the loop runs (default 3600 = 1hr)
  MONITOR_DEV_MODE          — If "true", uses 300s (5 min) for faster dev testing
  MONITOR_BUDGET_WARN_PCT   — Budget % to start warning (default 80)
  MONITOR_MILESTONE_WARN_DAYS — Days before due to warn (default 7)
  MONITOR_INACTIVITY_DAYS   — Days of silence before alert (default 3)

Usage (from main.py lifespan)
──────────────────────────────
    monitor = BackgroundMonitor()
    asyncio.create_task(monitor.start())
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

def _monitor_interval() -> int:
    if os.getenv("MONITOR_DEV_MODE", "").lower() == "true":
        return int(os.getenv("MONITOR_INTERVAL_SECONDS", "300"))
    return int(os.getenv("MONITOR_INTERVAL_SECONDS", "3600"))

BUDGET_WARN_PCT      = int(os.getenv("MONITOR_BUDGET_WARN_PCT", "80"))
MILESTONE_WARN_DAYS  = int(os.getenv("MONITOR_MILESTONE_WARN_DAYS", "7"))
INACTIVITY_DAYS      = int(os.getenv("MONITOR_INACTIVITY_DAYS", "3"))


# ── BackgroundMonitor ─────────────────────────────────────────────────────────

class BackgroundMonitor:
    """
    Async background task that monitors all active projects.

    Designed to run as a single asyncio task for the lifetime of the app.
    Stops cleanly when cancelled.
    """

    def __init__(self):
        self._running          = False
        self._check_count      = 0
        self._last_run_at:   Optional[datetime] = None
        # Track which alert keys have already been fired (avoids spam)
        # Key format: f"{project_id}:{alert_key}"
        self._fired_alerts: set[str] = set()

    async def start(self) -> None:
        """
        Entry point — runs forever until cancelled.
        Called via asyncio.create_task(monitor.start()) in main.py lifespan.
        """
        self._running = True
        interval      = _monitor_interval()
        logger.info(
            f"[Monitor] Background monitoring started — interval={interval}s, "
            f"budget_warn={BUDGET_WARN_PCT}%, milestone_warn={MILESTONE_WARN_DAYS}d"
        )

        # Stagger first run by 30s to let the app finish starting
        await asyncio.sleep(30)

        while self._running:
            try:
                await self._run_all_checks()
            except asyncio.CancelledError:
                logger.info("[Monitor] Monitoring loop cancelled — shutting down")
                break
            except Exception as e:
                logger.error(f"[Monitor] Unexpected error in monitoring loop: {e}")

            # Wait for next cycle
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

        self._running = False
        logger.info("[Monitor] Background monitoring stopped")

    def stop(self) -> None:
        """Signal the loop to stop after the current cycle."""
        self._running = False

    @property
    def status(self) -> dict:
        return {
            "running":       self._running,
            "check_count":   self._check_count,
            "last_run_at":   self._last_run_at.isoformat() if self._last_run_at else None,
            "interval_secs": _monitor_interval(),
            "fired_alerts":  len(self._fired_alerts),
        }

    # ── Core check loop ───────────────────────────────────────────────────────

    async def _run_all_checks(self) -> None:
        """Discover all active projects and run checks for each."""
        projects = await asyncio.get_event_loop().run_in_executor(
            None, self._discover_active_projects
        )
        self._check_count += 1
        self._last_run_at  = datetime.utcnow()

        if not projects:
            logger.debug("[Monitor] No active projects to monitor")
            return

        logger.debug(f"[Monitor] Checking {len(projects)} active projects")
        for proj in projects:
            try:
                await self._check_project(proj)
            except Exception as e:
                logger.warning(f"[Monitor] Error checking project {proj.get('project_id', '?')}: {e}")

    async def _check_project(self, proj: dict) -> None:
        """
        Run all threshold checks for a single project.
        All DB reads happen in a thread executor to avoid blocking the event loop.
        """
        project_id = proj["project_id"]
        tenant_id  = proj["tenant_id"]
        db_path    = proj["db_path"]
        owner_email = proj.get("owner_email")

        if not db_path or not Path(db_path).exists():
            return

        # Run checks concurrently (all read-only, safe to parallelize)
        await asyncio.gather(
            self._check_budget(project_id, tenant_id, db_path, owner_email),
            self._check_milestones(project_id, tenant_id, db_path, owner_email),
            self._check_kpis(project_id, tenant_id, db_path),
            self._check_risks(project_id, tenant_id, db_path),
            self._check_inactivity(project_id, tenant_id, db_path),
            return_exceptions=True,
        )

    # ── Individual checks ─────────────────────────────────────────────────────

    async def _check_budget(
        self,
        project_id:  str,
        tenant_id:   str,
        db_path:     str,
        owner_email: Optional[str],
    ) -> None:
        """Warn when budget utilization hits 80%, 90%, 100%."""
        try:
            loop = asyncio.get_event_loop()
            meta = await loop.run_in_executor(None, lambda: self._fetch_meta(db_path))
            if not meta:
                return

            bt = float(meta.get("budget_total") or 0)
            bs = float(meta.get("budget_spent") or 0)
            if bt <= 0:
                return

            pct = bs / bt * 100

            # Determine threshold crossed
            for threshold, severity in [(100, "urgent"), (90, "high"), (BUDGET_WARN_PCT, "medium")]:
                if pct >= threshold:
                    alert_key = f"{project_id}:budget_{threshold}"
                    if alert_key in self._fired_alerts:
                        return  # Already alerted this cycle
                    self._fired_alerts.add(alert_key)

                    title   = f"Budget alert: {pct:.0f}% utilised"
                    message = (
                        f"Project has spent {self._fmt_currency(bs)} of "
                        f"{self._fmt_currency(bt)} ({pct:.1f}%). "
                        + (f"Budget exceeded by {self._fmt_currency(bs - bt)}!"
                           if pct >= 100 else
                           f"At current burn rate, budget will be exhausted soon.")
                    )

                    # Create notification
                    await loop.run_in_executor(
                        None,
                        lambda: self._create_notification(
                            db_path, project_id, tenant_id,
                            title, message, severity,
                            "budget_threshold", owner_email,
                        )
                    )

                    # Queue Category B action for 90%+ alerts
                    if pct >= 90:
                        await loop.run_in_executor(
                            None,
                            lambda: self._queue_action(
                                db_path, project_id, tenant_id,
                                agent_dept   = "finance",
                                action_type  = "flag_budget_risk",
                                category     = "B_approve",
                                title        = f"Flag project budget as at-risk ({pct:.0f}% utilised)",
                                description  = message,
                                reasoning    = f"Budget utilization has reached {pct:.0f}%, exceeding the risk threshold.",
                                evidence     = {"budget_total": bt, "budget_spent": bs, "utilization_pct": pct},
                                priority     = "high" if pct >= 90 else "medium",
                            )
                        )
                    return  # Only fire highest threshold alert

        except Exception as e:
            logger.debug(f"[Monitor] budget check failed ({project_id}): {e}")

    async def _check_milestones(
        self,
        project_id:  str,
        tenant_id:   str,
        db_path:     str,
        owner_email: Optional[str],
    ) -> None:
        """Alert on overdue milestones and those approaching their due date."""
        try:
            loop  = asyncio.get_event_loop()
            today = datetime.utcnow().date()

            milestones = await loop.run_in_executor(
                None,
                lambda: self._fetch_milestones(db_path),
            )

            for m in milestones:
                if m["status"] in ("completed", "cancelled"):
                    continue
                due_str = m.get("due_date")
                if not due_str:
                    continue

                try:
                    due = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue

                days_until = (due - today).days
                name       = m["name"]

                if days_until < 0:
                    # Overdue
                    alert_key = f"{project_id}:milestone_overdue_{m['milestone_id']}"
                    if alert_key not in self._fired_alerts:
                        self._fired_alerts.add(alert_key)
                        days_late = abs(days_until)
                        await loop.run_in_executor(
                            None,
                            lambda: self._create_notification(
                                db_path, project_id, tenant_id,
                                f"Overdue milestone: {name}",
                                f"Milestone '{name}' was due {days_late} day(s) ago and is still {m['status']}.",
                                "high", "milestone_overdue", owner_email,
                            )
                        )

                elif days_until <= MILESTONE_WARN_DAYS:
                    # Due soon
                    alert_key = f"{project_id}:milestone_due_{m['milestone_id']}"
                    if alert_key not in self._fired_alerts:
                        self._fired_alerts.add(alert_key)
                        await loop.run_in_executor(
                            None,
                            lambda: self._create_notification(
                                db_path, project_id, tenant_id,
                                f"Milestone due in {days_until}d: {name}",
                                f"Milestone '{name}' is due on {due_str} — {days_until} day(s) remaining. "
                                f"Current status: {m['status']}.",
                                "medium", "milestone_due_soon", None,
                            )
                        )

        except Exception as e:
            logger.debug(f"[Monitor] milestone check failed ({project_id}): {e}")

    async def _check_kpis(
        self,
        project_id: str,
        tenant_id:  str,
        db_path:    str,
    ) -> None:
        """Alert when KPIs are off_track or at_risk."""
        try:
            loop = asyncio.get_event_loop()
            kpis = await loop.run_in_executor(
                None,
                lambda: self._fetch_kpis(db_path),
            )

            for k in kpis:
                status = k.get("status") or "unknown"
                if status in ("off_track", "at_risk"):
                    alert_key = f"{project_id}:kpi_{k['kpi_id']}_{status}"
                    if alert_key in self._fired_alerts:
                        continue
                    self._fired_alerts.add(alert_key)

                    severity = "high" if status == "off_track" else "medium"
                    name     = k.get("kpi_name", "KPI")
                    current  = k.get("current_value", "N/A")
                    target   = k.get("target_value", "N/A")

                    await loop.run_in_executor(
                        None,
                        lambda: self._create_notification(
                            db_path, project_id, tenant_id,
                            f"KPI {status.replace('_', ' ')}: {name}",
                            f"'{name}' is {status.replace('_', ' ')}. "
                            f"Current: {current} | Target: {target} | Unit: {k.get('unit', '')}",
                            severity, "kpi_status_change", None,
                        )
                    )

        except Exception as e:
            logger.debug(f"[Monitor] KPI check failed ({project_id}): {e}")

    async def _check_risks(
        self,
        project_id: str,
        tenant_id:  str,
        db_path:    str,
    ) -> None:
        """Alert on open high-impact risks."""
        try:
            loop  = asyncio.get_event_loop()
            risks = await loop.run_in_executor(
                None,
                lambda: self._fetch_high_risks(db_path),
            )

            for r in risks:
                alert_key = f"{project_id}:risk_high_{r['risk_id']}"
                if alert_key in self._fired_alerts:
                    continue
                self._fired_alerts.add(alert_key)

                await loop.run_in_executor(
                    None,
                    lambda: self._create_notification(
                        db_path, project_id, tenant_id,
                        f"High-impact risk open: {r['title']}",
                        f"Risk '{r['title']}' is open with high impact. "
                        + (f"Mitigation: {r['mitigation_plan']}" if r.get("mitigation_plan") else "No mitigation plan recorded."),
                        "high", "risk_escalated", None,
                    )
                )

        except Exception as e:
            logger.debug(f"[Monitor] risk check failed ({project_id}): {e}")

    async def _check_inactivity(
        self,
        project_id: str,
        tenant_id:  str,
        db_path:    str,
    ) -> None:
        """Alert if no activity has been logged in INACTIVITY_DAYS days."""
        try:
            loop  = asyncio.get_event_loop()
            alert_key = f"{project_id}:inactivity"
            if alert_key in self._fired_alerts:
                return

            last_activity = await loop.run_in_executor(
                None,
                lambda: self._fetch_last_activity(db_path),
            )
            if not last_activity:
                return

            cutoff = datetime.utcnow() - timedelta(days=INACTIVITY_DAYS)
            try:
                last_dt = datetime.fromisoformat(last_activity[:19])
            except ValueError:
                return

            if last_dt < cutoff:
                self._fired_alerts.add(alert_key)
                days_since = (datetime.utcnow() - last_dt).days
                await loop.run_in_executor(
                    None,
                    lambda: self._create_notification(
                        db_path, project_id, tenant_id,
                        f"No project activity in {days_since} days",
                        f"No activity has been logged for this project in {days_since} days. "
                        f"Last recorded activity: {last_activity[:10]}.",
                        "medium", "inactivity", None,
                    )
                )

        except Exception as e:
            logger.debug(f"[Monitor] inactivity check failed ({project_id}): {e}")

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _discover_active_projects(self) -> list[dict]:
        """
        Read the project_registry table from rapid.db to get all active projects.
        Also fetches owner email if available (for email notifications).
        """
        import config
        try:
            conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT pr.project_id, pr.tenant_id, pr.db_path,
                       p.owner_user_id
                FROM project_registry pr
                LEFT JOIN projects p ON pr.project_id = p.project_id
                WHERE pr.status = 'active'
                """
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.debug(f"[Monitor] discover_projects failed: {e}")
            return []

    def _fetch_meta(self, db_path: str) -> Optional[dict]:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            row  = conn.execute("SELECT * FROM project_metadata LIMIT 1").fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            return None

    def _fetch_milestones(self, db_path: str) -> list[dict]:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT milestone_id, name, due_date, status FROM project_milestones"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _fetch_kpis(self, db_path: str) -> list[dict]:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT kpi_id, kpi_name, current_value, target_value, unit, status FROM project_kpis"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _fetch_high_risks(self, db_path: str) -> list[dict]:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT risk_id, title, mitigation_plan FROM project_risks "
                "WHERE status='open' AND impact='high'"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _fetch_last_activity(self, db_path: str) -> Optional[str]:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            row  = conn.execute(
                "SELECT MAX(logged_at) FROM project_activity_log"
            ).fetchone()
            conn.close()
            return row[0] if row else None
        except Exception:
            return None

    # ── Side-effect helpers ───────────────────────────────────────────────────

    def _create_notification(
        self,
        db_path:     str,
        project_id:  str,
        tenant_id:   str,
        title:       str,
        message:     str,
        severity:    str,
        category:    str,
        email_to:    Optional[str],
    ) -> None:
        from infrastructure.notification_engine import get_notification_engine
        engine = get_notification_engine(db_path, project_id, tenant_id)
        engine.notify(
            title     = title,
            message   = message,
            severity  = severity,
            category  = category,
            source    = "monitoring_loop",
            email_to  = email_to,
        )

    def _queue_action(
        self,
        db_path:     str,
        project_id:  str,
        tenant_id:   str,
        agent_dept:  str,
        action_type: str,
        category:    str,
        title:       str,
        description: str,
        reasoning:   str,
        evidence:    dict,
        priority:    str,
    ) -> None:
        from infrastructure.action_queue import get_action_queue
        aq = get_action_queue(db_path, project_id, tenant_id)
        aq.enqueue(
            agent_dept   = agent_dept,
            action_type  = action_type,
            category     = category,
            title        = title,
            description  = description,
            reasoning    = reasoning,
            evidence     = evidence,
            priority     = priority,
        )

    @staticmethod
    def _fmt_currency(val) -> str:
        try:
            return f"${float(val):,.0f}"
        except Exception:
            return str(val)


# ── Singleton ─────────────────────────────────────────────────────────────────

_monitor: Optional[BackgroundMonitor] = None


def get_background_monitor() -> BackgroundMonitor:
    global _monitor
    if _monitor is None:
        _monitor = BackgroundMonitor()
    return _monitor
