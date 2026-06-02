"""Render + dry-run delivery for the weekend digest (Phase A3).

Renders the :class:`app.digest.builder.WeekendDigest` into (subject, html, text)
using Jinja templates, mirroring ``app.alerts.render``'s approach. A DRY-RUN
path builds + renders WITHOUT sending. Real delivery reuses
``app.auth.email_sender.send_alert_email`` but is gated behind an explicit
``dry_run=False`` so the default posture never sends — send cadence/cron is a
flagged Casey decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.digest.builder import WeekendDigest

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
)

_SUBJECT = "This weekend in Havasu"


def _format_date_safe(d) -> str:
    # e.g. "Fri Jun 6". %-d is not portable to Windows; format the day manually.
    try:
        return d.strftime("%a %b ") + str(d.day)
    except Exception:  # pragma: no cover - defensive
        return str(d)


def _event_rows(events) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for ev in events:
        rows.append(
            {
                "title": ev.title,
                "date_label": _format_date_safe(ev.occurrence_date),
                "location_name": ev.location_name,
                "event_url": ev.event_url,
            }
        )
    return rows


def render_weekend_digest(digest: WeekendDigest, *, digest_url: str) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) for the digest."""
    ctx = {
        "window_start_label": _format_date_safe(digest.window_start),
        "window_end_label": _format_date_safe(digest.window_end),
        "weekend_events": _event_rows(digest.weekend_events),
        "saved_venue_events": _event_rows(digest.saved_venue_events),
        "has_content": digest.has_content,
        "has_saved_venue_events": digest.has_saved_venue_events,
        "digest_url": digest_url,
    }
    html_body = _env.get_template("weekend_digest.html.j2").render(**ctx)
    text_body = _env.get_template("weekend_digest.txt.j2").render(**ctx)
    return _SUBJECT, html_body, text_body


@dataclass(frozen=True)
class DigestRenderResult:
    """Outcome of building + rendering a digest (dry-run friendly)."""

    subject: str
    html_body: str
    text_body: str
    sent: bool
    has_content: bool


def build_render_digest(
    db,
    user_id: str,
    *,
    to_email: str | None = None,
    digest_url: str = "",
    today=None,
    dry_run: bool = True,
) -> DigestRenderResult:
    """Build + render a user's weekend digest.

    DRY-RUN by default: returns the rendered bodies and ``sent=False`` without
    contacting the email sender. When ``dry_run=False`` AND ``to_email`` is
    provided, delivers via ``send_alert_email`` (which itself logs instead of
    sends when AUTH_DEV_MODE is on). We never send an empty-state digest.
    """
    from app.digest.builder import build_weekend_digest

    digest = build_weekend_digest(db, user_id, today=today)
    subject, html_body, text_body = render_weekend_digest(digest, digest_url=digest_url)

    sent = False
    if not dry_run and to_email and digest.has_content:
        from app.auth.email_sender import send_alert_email

        send_alert_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
        sent = True

    return DigestRenderResult(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        sent=sent,
        has_content=digest.has_content,
    )
