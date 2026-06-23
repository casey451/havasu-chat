"""Feedback persistence + operator notification.

Two layers, mirroring ``app/billing/service.py``'s split:

* DB helpers (:func:`create_feedback`, :func:`list_feedback`, ...) move no mail
  and are fully testable with a row.
* :func:`notify_feedback` forwards one row to the operator via Resend
  (``app.auth.email_sender.send_alert_email``). It is best-effort: the DB row is
  the source of truth, so a missing key / failed send never loses feedback.
"""

from __future__ import annotations

import html
import logging
import os

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.auth.email_sender import send_alert_email
from app.db.models import Feedback

logger = logging.getLogger(__name__)

VALID_KINDS = frozenset({"wrong_info", "missing_info", "general", "bug"})
VALID_STATUSES = frozenset({"new", "reviewed", "resolved", "spam"})
MAX_MESSAGE = 4000
MAX_FIELD = 255


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v[:limit] if v else None


def create_feedback(
    db: Session,
    *,
    kind: str,
    message: str,
    target_type: str | None = None,
    target_ref: str | None = None,
    page_url: str | None = None,
    email: str | None = None,
) -> Feedback:
    """Persist one feedback submission and return the row (committed)."""
    row = Feedback(
        kind=kind if kind in VALID_KINDS else "general",
        message=(message or "").strip()[:MAX_MESSAGE],
        target_type=_clip(target_type, 32),
        target_ref=_clip(target_ref, MAX_FIELD),
        page_url=_clip(page_url, 2048),
        email=_clip(email, 320),
        status="new",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def feedback_notify_email() -> str:
    """The dedicated inbox/alias to forward feedback to (Casey provides via env)."""
    return (os.environ.get("FEEDBACK_NOTIFY_EMAIL") or "").strip()


def _render_notification(row: Feedback) -> tuple[str, str]:
    """Return (html_body, text_body) for the operator forward."""
    where = " · ".join(
        p
        for p in (
            f"{row.target_type}:{row.target_ref}" if row.target_type else None,
            row.page_url,
        )
        if p
    )
    reply = row.email or "(no reply address given)"
    text = (
        f"New feedback ({row.kind}) #{row.id}\n\n"
        f"{row.message}\n\n"
        f"Reply to: {reply}\n"
        f"From: {where or '(site footer)'}\n\n"
        f"Manage at /admin/portal/feedback\n"
    )
    html_body = (
        "<!DOCTYPE html><html><body>"
        f"<p><strong>New feedback</strong> ({html.escape(row.kind)}) #{row.id}</p>"
        f"<blockquote>{html.escape(row.message)}</blockquote>"
        f"<p>Reply to: {html.escape(reply)}<br>"
        f"From: {html.escape(where or '(site footer)')}</p>"
        '<p><a href="/admin/portal/feedback">Manage in admin</a></p>'
        "</body></html>"
    )
    return html_body, text


def notify_feedback(row: Feedback) -> bool:
    """Forward one feedback row to the operator (best-effort).

    Returns True if a send was attempted (i.e. a recipient is configured). When
    ``FEEDBACK_NOTIFY_EMAIL`` is unset, logs and returns False — the row is
    already persisted, so nothing is lost. A Resend failure is swallowed (logged)
    so the caller's request never 500s.
    """
    to = feedback_notify_email()
    if not to:
        logger.info(
            "feedback %s saved; FEEDBACK_NOTIFY_EMAIL unset — skipping forward", row.id
        )
        return False
    html_body, text_body = _render_notification(row)
    try:
        send_alert_email(
            to_email=to,
            subject=f"[Hava feedback] {row.kind} #{row.id}",
            html_body=html_body,
            text_body=text_body,
        )
    except Exception:  # noqa: BLE001 — a send failure must not lose the row
        logger.exception("feedback %s email forward failed", row.id)
    return True


# --------------------------------------------------------------------------- #
# Admin-queue reads/writes.
# --------------------------------------------------------------------------- #


def list_feedback(
    db: Session, *, status: str | None = None, limit: int = 100, offset: int = 0
) -> list[Feedback]:
    stmt = select(Feedback).order_by(desc(Feedback.created_at))
    if status:
        stmt = stmt.where(Feedback.status == status)
    return list(db.execute(stmt.offset(offset).limit(limit)).scalars().all())


def count_feedback(db: Session, *, status: str | None = None) -> int:
    stmt = select(func.count()).select_from(Feedback)
    if status:
        stmt = stmt.where(Feedback.status == status)
    return int(db.execute(stmt).scalar() or 0)


def status_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Feedback.status, func.count()).group_by(Feedback.status)
    ).all()
    return {str(s): int(n) for s, n in rows}


def update_feedback_status(
    db: Session, feedback_id: int, *, status: str, admin_note: str | None = None
) -> Feedback | None:
    row = db.get(Feedback, feedback_id)
    if row is None:
        return None
    if status in VALID_STATUSES:
        row.status = status
    if admin_note is not None:
        row.admin_note = admin_note.strip()[:MAX_MESSAGE] or None
    from datetime import UTC, datetime

    row.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(row)
    db.commit()
    return row
