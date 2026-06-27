"""
infrastructure/notification_engine.py — Notification & Alert Engine.

Part of RAPID Phase 5 (Human-in-the-Loop).

The NotificationEngine stores alerts in each project's SQLite database
(project_notifications table) and optionally sends email for high-severity
events.

Severity levels
───────────────
  info     — Informational, no action required
  medium   — Worth noting; surfaces in dashboard
  high     — Requires attention; email sent to project owner
  urgent   — Immediate action needed; email + action queued

Notification categories (from blueprint Section 12)
────────────────────────────────────────────────────
  milestone_overdue    — A milestone is past its due date
  milestone_due_soon   — A milestone is due within N days
  budget_threshold     — Budget crossed 80%, 90%, or 100%
  kpi_status_change    — KPI moved from on_track → at_risk → off_track
  risk_escalated       — A risk severity increased
  action_pending_long  — An action has been waiting too long for approval
  project_at_risk      — Project health changed to at_risk or off_track
  custom               — Agent-generated alert

Usage
─────
    from infrastructure.notification_engine import get_notification_engine

    engine = get_notification_engine(db_path, project_id, tenant_id)

    # Create an alert
    notif = engine.notify(
        title    = "Budget threshold reached: 82%",
        message  = "Project Alpha has used 82% of its budget with 6 weeks remaining.",
        severity = "high",
        category = "budget_threshold",
        source   = "monitoring_loop",
    )

    # List unread notifications
    unread = engine.list_unread()

    # Mark as read
    engine.mark_read(notif.notification_id, user_id="user_ayush")
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


# ── Notification dataclass ────────────────────────────────────────────────────

@dataclass
class Notification:
    notification_id:    str
    project_id:         str
    tenant_id:          str
    title:              str
    message:            str
    severity:           str              = "medium"
    category:           str              = "custom"
    source:             str              = "system"
    action_id:          Optional[str]    = None
    read_by:            Optional[str]    = None
    read_at:            Optional[str]    = None
    created_at:         str              = field(default_factory=lambda: datetime.utcnow().isoformat())
    delivered_channels: list[str]        = field(default_factory=list)
    dismissed:          bool             = False

    @property
    def is_read(self) -> bool:
        return self.read_by is not None

    def to_dict(self) -> dict:
        return {
            "notification_id":    self.notification_id,
            "project_id":         self.project_id,
            "tenant_id":          self.tenant_id,
            "title":              self.title,
            "message":            self.message,
            "severity":           self.severity,
            "category":           self.category,
            "source":             self.source,
            "action_id":          self.action_id,
            "read_by":            self.read_by,
            "read_at":            self.read_at,
            "created_at":         self.created_at,
            "delivered_channels": self.delivered_channels,
            "dismissed":          self.dismissed,
            "is_read":            self.is_read,
        }


# ── NotificationEngine ────────────────────────────────────────────────────────

class NotificationEngine:
    """
    Creates, stores, and delivers notifications for a project.

    Delivery channels:
      - In-app  (always — stored in project_notifications table)
      - Email   (for severity=high or urgent, if SMTP is configured)
    """

    # Severity → whether to send email
    _EMAIL_SEVERITIES = {"high", "urgent"}

    def __init__(self, db_path: str, project_id: str, tenant_id: str):
        self.db_path    = db_path
        self.project_id = project_id
        self.tenant_id  = tenant_id

    # ── Public API ────────────────────────────────────────────────────────────

    def notify(
        self,
        title:      str,
        message:    str,
        severity:   str           = "medium",
        category:   str           = "custom",
        source:     str           = "system",
        action_id:  Optional[str] = None,
        email_to:   Optional[str] = None,
    ) -> Notification:
        """
        Create and deliver a notification.

        email_to — if provided AND severity is high/urgent, an email is sent.
                   If SMTP is not configured, email delivery is silently skipped.
        """
        notif = Notification(
            notification_id = str(uuid.uuid4()),
            project_id      = self.project_id,
            tenant_id       = self.tenant_id,
            title           = title,
            message         = message,
            severity        = severity,
            category        = category,
            source          = source,
            action_id       = action_id,
        )

        # 1. Always store in-app
        self._store(notif)
        notif.delivered_channels.append("in_app")

        # 2. Email for high/urgent severity
        if severity in self._EMAIL_SEVERITIES and email_to:
            sent = self._send_email(notif, email_to)
            if sent:
                notif.delivered_channels.append("email")
                self._update_channels(notif)

        logger.info(
            f"[NotificationEngine] [{severity.upper()}] {title} "
            f"(project={self.project_id[:8]}, channels={notif.delivered_channels})"
        )
        return notif

    def list_unread(self, limit: int = 50) -> list[Notification]:
        """Return all unread (not dismissed) notifications, newest first."""
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                """
                SELECT * FROM project_notifications
                WHERE project_id=? AND read_by IS NULL AND dismissed=0
                ORDER BY created_at DESC LIMIT ?
                """,
                (self.project_id, limit),
            ).fetchall()
            return [self._row_to_notif(r) for r in rows]
        finally:
            conn.close()

    def list_all(
        self,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        limit:    int           = 100,
    ) -> list[Notification]:
        """Return all notifications with optional filters."""
        clauses = ["project_id = ?"]
        params  = [self.project_id]
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if category:
            clauses.append("category = ?")
            params.append(category)

        where = "WHERE " + " AND ".join(clauses)
        conn  = self._connect_ro()
        try:
            rows = conn.execute(
                f"SELECT * FROM project_notifications {where} ORDER BY created_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
            return [self._row_to_notif(r) for r in rows]
        finally:
            conn.close()

    def mark_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read by a specific user."""
        now  = datetime.utcnow().isoformat()
        conn = self._connect()
        try:
            rows = conn.execute(
                "UPDATE project_notifications SET read_by=?, read_at=? WHERE notification_id=?",
                (user_id, now, notification_id),
            ).rowcount
            conn.commit()
            return rows > 0
        finally:
            conn.close()

    def dismiss(self, notification_id: str) -> bool:
        """Dismiss a notification (hide from unread list)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "UPDATE project_notifications SET dismissed=1 WHERE notification_id=?",
                (notification_id,),
            ).rowcount
            conn.commit()
            return rows > 0
        finally:
            conn.close()

    def unread_count(self) -> int:
        """Fast count of unread notifications."""
        conn = self._connect_ro()
        try:
            r = conn.execute(
                "SELECT COUNT(*) FROM project_notifications WHERE project_id=? AND read_by IS NULL AND dismissed=0",
                (self.project_id,),
            ).fetchone()
            return r[0] if r else 0
        finally:
            conn.close()

    # ── Storage helpers ───────────────────────────────────────────────────────

    def _store(self, notif: Notification) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO project_notifications
                    (notification_id, project_id, tenant_id, title, message,
                     severity, category, source, action_id,
                     created_at, delivered_channels, dismissed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    notif.notification_id,
                    notif.project_id,
                    notif.tenant_id,
                    notif.title,
                    notif.message,
                    notif.severity,
                    notif.category,
                    notif.source,
                    notif.action_id,
                    notif.created_at,
                    json.dumps(notif.delivered_channels),
                    1 if notif.dismissed else 0,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"[NotificationEngine] Store failed: {e}")
        finally:
            conn.close()

    def _update_channels(self, notif: Notification) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE project_notifications SET delivered_channels=? WHERE notification_id=?",
                (json.dumps(notif.delivered_channels), notif.notification_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Email delivery ────────────────────────────────────────────────────────

    def _send_email(self, notif: Notification, to_email: str) -> bool:
        """
        Send an email alert.
        Reads SMTP config from environment variables:
          SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
        Returns True if sent, False if SMTP not configured or delivery failed.
        """
        smtp_host = os.getenv("SMTP_HOST", "")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASSWORD", "")
        smtp_from = os.getenv("SMTP_FROM", smtp_user)

        if not smtp_host:
            logger.debug("[NotificationEngine] SMTP_HOST not set — email skipped")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[RAPID Alert] {notif.title}"
            msg["From"]    = smtp_from
            msg["To"]      = to_email

            severity_label = notif.severity.upper()
            body_html = f"""
<html><body style="font-family:Arial,sans-serif;padding:20px;">
  <h2 style="color:#c0392b;">⚠️ RAPID Alert — {severity_label}</h2>
  <h3>{notif.title}</h3>
  <p>{notif.message}</p>
  <hr/>
  <small style="color:#888;">
    Project: {notif.project_id} &nbsp;|&nbsp;
    Category: {notif.category} &nbsp;|&nbsp;
    Source: {notif.source} &nbsp;|&nbsp;
    Time: {notif.created_at}
  </small>
</body></html>"""
            body_text = f"RAPID Alert [{severity_label}]\n\n{notif.title}\n\n{notif.message}"

            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, to_email, msg.as_string())

            logger.info(f"[NotificationEngine] Email sent to {to_email}: {notif.title}")
            return True

        except Exception as e:
            logger.warning(f"[NotificationEngine] Email send failed ({to_email}): {e}")
            return False

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _row_to_notif(self, row: sqlite3.Row) -> Notification:
        d = dict(row)
        try:
            channels = json.loads(d.get("delivered_channels") or "[]")
        except Exception:
            channels = []
        return Notification(
            notification_id    = d["notification_id"],
            project_id         = d["project_id"],
            tenant_id          = d["tenant_id"],
            title              = d["title"],
            message            = d["message"],
            severity           = d.get("severity") or "medium",
            category           = d.get("category") or "custom",
            source             = d.get("source") or "system",
            action_id          = d.get("action_id"),
            read_by            = d.get("read_by"),
            read_at            = d.get("read_at"),
            created_at         = d.get("created_at") or "",
            delivered_channels = channels,
            dismissed          = bool(d.get("dismissed", 0)),
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_ro(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn


# ── Convenience factory ───────────────────────────────────────────────────────

def get_notification_engine(
    db_path:    str,
    project_id: str,
    tenant_id:  str,
) -> NotificationEngine:
    return NotificationEngine(db_path=db_path, project_id=project_id, tenant_id=tenant_id)
