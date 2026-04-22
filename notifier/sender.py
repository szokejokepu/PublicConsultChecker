"""Email notification module for public consultation alerts.

Reads SMTP credentials from environment variables (or a .env file) and sends
a digest email listing newly detected public consultation articles.

Environment variables
---------------------
    NOTIFIER_SMTP_HOST      SMTP server hostname       (default: smtp.gmail.com)
    NOTIFIER_SMTP_PORT      SMTP port, TLS/STARTTLS    (default: 587)
    NOTIFIER_SMTP_USER      Login username
    NOTIFIER_SMTP_PASSWORD  Login password / app password
    NOTIFIER_FROM           From address (defaults to NOTIFIER_SMTP_USER)
    NOTIFIER_TO             Recipient address

Usage
-----
    # Send a test email to verify your config:
    python -m notifier.sender --test

    # Send a test email to a different address:
    python -m notifier.sender --test --to someone@example.com
"""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import click

# Load .env if present (silently ignored if file doesn't exist)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on real env vars


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class ConsultationAlert:
    """Minimal representation of an article to include in the digest."""
    article_id: int
    title: str | None
    url: str
    date: str | None
    classifier_score: float | None
    extracted_date: str | None
    extracted_time: str | None
    extracted_place: str | None
    extracted_subject: str | None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class NotifierConfig:
    def __init__(self) -> None:
        self.smtp_host = os.environ.get("NOTIFIER_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("NOTIFIER_SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("NOTIFIER_SMTP_USER", "")
        self.smtp_password = os.environ.get("NOTIFIER_SMTP_PASSWORD", "")
        self.from_addr = os.environ.get("NOTIFIER_FROM", "") or self.smtp_user
        self.to_addr = os.environ.get("NOTIFIER_TO", "")

    def validate(self) -> None:
        missing = [
            name for name, val in [
                ("NOTIFIER_SMTP_USER", self.smtp_user),
                ("NOTIFIER_SMTP_PASSWORD", self.smtp_password),
                ("NOTIFIER_TO", self.to_addr),
            ] if not val
        ]
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Email building
# ---------------------------------------------------------------------------


def _build_subject(alerts: list[ConsultationAlert]) -> str:
    n = len(alerts)
    return f"[RAG] {n} new public consultation{'s' if n != 1 else ''} detected"


def _build_text(alerts: list[ConsultationAlert], sent_at: str) -> str:
    lines = [
        f"Public Consultation Alerts — {sent_at}",
        "=" * 60,
        f"{len(alerts)} new article(s) detected:",
        "",
    ]
    for i, a in enumerate(alerts, 1):
        lines.append(f"{i}. {a.title or '(no title)'}")
        lines.append(f"   URL     : {a.url}")
        if a.date:
            lines.append(f"   Date    : {a.date}")
        if a.classifier_score is not None:
            lines.append(f"   Score   : {a.classifier_score:.3f}")
        if a.extracted_subject:
            lines.append(f"   Subject : {a.extracted_subject}")
        if a.extracted_date:
            lines.append(f"   Event   : {a.extracted_date}"
                         + (f" {a.extracted_time}" if a.extracted_time else ""))
        if a.extracted_place:
            lines.append(f"   Place   : {a.extracted_place}")
        lines.append("")
    lines.append("—")
    lines.append("Sent by your RAG notification service.")
    return "\n".join(lines)


def _build_html(alerts: list[ConsultationAlert], sent_at: str) -> str:
    rows = []
    for a in alerts:
        score_html = f"{a.classifier_score:.3f}" if a.classifier_score is not None else "—"
        event_parts = [p for p in [a.extracted_date, a.extracted_time] if p]
        event_html = " ".join(event_parts) if event_parts else "—"
        rows.append(f"""
        <tr>
          <td style="padding:12px;border-bottom:1px solid #e2e8f0;vertical-align:top">
            <a href="{a.url}" style="font-weight:600;color:#3b82f6;text-decoration:none">
              {a.title or '(no title)'}
            </a>
            <div style="font-size:0.85em;color:#64748b;margin-top:4px">{a.url}</div>
          </td>
          <td style="padding:12px;border-bottom:1px solid #e2e8f0;color:#475569;vertical-align:top">
            {a.extracted_subject or '—'}
          </td>
          <td style="padding:12px;border-bottom:1px solid #e2e8f0;color:#475569;vertical-align:top;white-space:nowrap">
            {event_html}
          </td>
          <td style="padding:12px;border-bottom:1px solid #e2e8f0;color:#475569;vertical-align:top;white-space:nowrap">
            {a.extracted_place or '—'}
          </td>
          <td style="padding:12px;border-bottom:1px solid #e2e8f0;color:#475569;vertical-align:top;text-align:center">
            {score_html}
          </td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:system-ui,sans-serif;background:#f8fafc;padding:24px;margin:0">
  <div style="max-width:800px;margin:0 auto;background:white;border-radius:8px;
              box-shadow:0 1px 3px rgba(0,0,0,0.1);overflow:hidden">
    <div style="background:#1e293b;color:white;padding:20px 24px">
      <h1 style="margin:0;font-size:1.2rem">Public Consultation Alerts</h1>
      <p style="margin:4px 0 0;color:#94a3b8;font-size:0.9rem">{sent_at}</p>
    </div>
    <div style="padding:20px 24px">
      <p style="color:#475569">{len(alerts)} new public consultation(s) detected:</p>
      <table style="width:100%;border-collapse:collapse;font-size:0.9rem">
        <thead>
          <tr style="background:#f1f5f9;text-align:left">
            <th style="padding:10px 12px;color:#64748b;font-weight:600">Article</th>
            <th style="padding:10px 12px;color:#64748b;font-weight:600">Subject</th>
            <th style="padding:10px 12px;color:#64748b;font-weight:600">Event date</th>
            <th style="padding:10px 12px;color:#64748b;font-weight:600">Place</th>
            <th style="padding:10px 12px;color:#64748b;font-weight:600">Score</th>
          </tr>
        </thead>
        <tbody>
          {"".join(rows)}
        </tbody>
      </table>
    </div>
    <div style="padding:16px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;
                font-size:0.8rem;color:#94a3b8">
      Sent by your RAG notification service.
    </div>
  </div>
</body>
</html>"""


def build_message(
    alerts: list[ConsultationAlert],
    from_addr: str,
    to_addr: str,
    sent_at: str | None = None,
) -> MIMEMultipart:
    """Build a MIMEMultipart email message from a list of alerts."""
    if sent_at is None:
        sent_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = _build_subject(alerts)
    msg["From"] = from_addr
    msg["To"] = to_addr

    msg.attach(MIMEText(_build_text(alerts, sent_at), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(alerts, sent_at), "html", "utf-8"))
    return msg


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


def send_summary_email(new_article_count: int, config: NotifierConfig | None = None) -> None:
    """Send a brief summary email when no public consultations were detected."""
    if config is None:
        config = NotifierConfig()
    config.validate()

    sent_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    subject = "[RAG] Cycle complete — no new public consultations"
    text = (
        f"Scheduler cycle complete — {sent_at}\n"
        f"{'=' * 60}\n"
        f"{new_article_count} new article(s) parsed.\n"
        f"No new public consultations detected.\n\n"
        f"—\nSent by your RAG notification service."
    )
    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:system-ui,sans-serif;background:#f8fafc;padding:24px;margin:0">
  <div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;
              box-shadow:0 1px 3px rgba(0,0,0,0.1);overflow:hidden">
    <div style="background:#1e293b;color:white;padding:20px 24px">
      <h1 style="margin:0;font-size:1.2rem">Scheduler Cycle Complete</h1>
      <p style="margin:4px 0 0;color:#94a3b8;font-size:0.9rem">{sent_at}</p>
    </div>
    <div style="padding:24px;color:#475569">
      <p style="margin:0 0 8px"><strong style="color:#1e293b">{new_article_count}</strong> new article(s) parsed.</p>
      <p style="margin:0;color:#64748b">No new public consultations detected.</p>
    </div>
    <div style="padding:16px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;
                font-size:0.8rem;color:#94a3b8">
      Sent by your RAG notification service.
    </div>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.from_addr
    msg["To"] = config.to_addr
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(config.smtp_user, config.smtp_password)
        server.sendmail(config.from_addr, config.to_addr, msg.as_string())


def send_digest(alerts: list[ConsultationAlert], config: NotifierConfig | None = None) -> None:
    """Send a digest email for the given alerts.

    Raises ``ValueError`` if config is invalid, ``smtplib.SMTPException`` on
    delivery failure.
    """
    if config is None:
        config = NotifierConfig()
    config.validate()

    msg = build_message(alerts, config.from_addr, config.to_addr)

    context = ssl.create_default_context()
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(config.smtp_user, config.smtp_password)
        server.sendmail(config.from_addr, config.to_addr, msg.as_string())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--test", "send_test", is_flag=True, default=False,
              help="Send a single test email with dummy data.")
@click.option("--to", "to_override", default=None, metavar="EMAIL",
              help="Override the recipient address for this send.")
def main(send_test: bool, to_override: str | None) -> None:
    """Send email notifications for public consultation alerts."""

    if not send_test:
        raise click.UsageError("Nothing to do. Use --test to send a test email.")

    config = NotifierConfig()
    if to_override:
        config.to_addr = to_override

    try:
        config.validate()
    except ValueError as e:
        raise click.ClickException(str(e))

    alerts = [
        ConsultationAlert(
            article_id=1,
            title="Consultare publică privind proiectul de buget 2026",
            url="https://example.com/article/1",
            date="2026-04-02",
            classifier_score=0.921,
            extracted_date="2026-04-15",
            extracted_time="14:00",
            extracted_place="Sala Mare, Primăria Municipiului",
            extracted_subject="Proiect de buget local pentru anul 2026",
        ),
        ConsultationAlert(
            article_id=2,
            title="Dezbatere publică PUZ zona industrială nord",
            url="https://example.com/article/2",
            date="2026-04-01",
            classifier_score=0.874,
            extracted_date="2026-04-20",
            extracted_time=None,
            extracted_place=None,
            extracted_subject="Plan Urbanistic Zonal zona industrială nord",
        ),
    ]

    click.echo(f"Sending test email to {config.to_addr} via {config.smtp_host}:{config.smtp_port}…")
    try:
        send_digest(alerts, config)
        click.echo(click.style("Email sent successfully.", fg="green", bold=True))
    except Exception as exc:
        raise click.ClickException(f"Failed to send: {exc}")


if __name__ == "__main__":
    main()
