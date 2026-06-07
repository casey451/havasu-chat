"""Monthly sponsor performance report (VPS rollout HANDOFF #4).

For each sponsor whose booking window overlapped the prior calendar month:
impressions, clicks, and CTR by slot tier, vs. the month before. Renders a
simple HTML + text email.

**READ-ONLY** against the DB (SELECTs only). ``--dry-run`` (the default) prints
the report to stdout; ``--execute`` sends it via the existing Resend sender
(:func:`app.auth.email_sender.send_alert_email`) to ``REPORT_RECIPIENT`` (or
``--to``). On the VPS this is cron'd from a repo checkout (see
``outputs/vps-rollout/crontab.txt``).

Usage::

    python -m scripts.sponsor_monthly_report                 # dry-run, prior month
    python -m scripts.sponsor_monthly_report --month 2026-05 # a specific month
    python -m scripts.sponsor_monthly_report --execute       # send the email

Data caveat (measured 2026-06-06): per-event impressions are only recorded for
the **spotlight** tier (``home.spotlight.impression``). Marquee / promoted /
supporter have no per-event impression rows yet, so their impressions/CTR show
as "n/a" until that instrumentation is added. Clicks (``home.sponsor.click``)
cover every tier. The report reads ``home.<slot>.impression`` generically, so it
fills in automatically once the other tiers are instrumented.

Exit status: 0 normal; 1 unexpected error; 2 bad arguments / missing recipient.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone

logger = logging.getLogger("scripts.sponsor_monthly_report")

# Slot tiers in presentation order (marquee = most premium).
_TIER_ORDER = ["marquee", "spotlight", "promoted", "supporter"]


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """[start, end) naive-UTC datetimes for the given calendar month.

    ``analytics_events.created_at`` is stored naive-UTC, so windows are naive-UTC
    too (half-open: start inclusive, end exclusive).
    """
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def prior_month(ref: datetime) -> tuple[int, int]:
    """(year, month) of the calendar month before ``ref``."""
    if ref.month == 1:
        return ref.year - 1, 12
    return ref.year, ref.month - 1


def _month_before(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


@dataclass
class SponsorRow:
    sponsor_id: str
    name: str
    slot: str
    impressions: int
    clicks: int
    prev_impressions: int
    prev_clicks: int

    @property
    def ctr(self) -> float | None:
        return (self.clicks / self.impressions) if self.impressions else None

    @property
    def prev_ctr(self) -> float | None:
        return (self.prev_clicks / self.prev_impressions) if self.prev_impressions else None


@dataclass
class Report:
    year: int
    month: int
    rows: list[SponsorRow] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{calendar.month_name[self.month]} {self.year}"

    @property
    def rows_by_tier(self) -> list[tuple[str, list[SponsorRow]]]:
        grouped: dict[str, list[SponsorRow]] = {}
        for r in self.rows:
            grouped.setdefault(r.slot, []).append(r)
        ordered = [(t, grouped[t]) for t in _TIER_ORDER if t in grouped]
        # Any non-canonical slot value still gets reported, after the known tiers.
        ordered += [(t, grouped[t]) for t in sorted(grouped) if t not in _TIER_ORDER]
        return ordered


def _count_events(db, *, sponsor_id, name_eq=None, name_like=None, start, end) -> int:
    from sqlalchemy import func, select

    from app.db.models import AnalyticsEvent

    stmt = select(func.count()).select_from(AnalyticsEvent).where(
        AnalyticsEvent.sponsor_id == sponsor_id,
        AnalyticsEvent.created_at >= start,
        AnalyticsEvent.created_at < end,
    )
    if name_eq is not None:
        stmt = stmt.where(AnalyticsEvent.event_name == name_eq)
    if name_like is not None:
        stmt = stmt.where(AnalyticsEvent.event_name.like(name_like))
    return int(db.scalar(stmt) or 0)


def gather_report(db, year: int, month: int) -> Report:
    """Build the report for the given calendar month (read-only)."""
    from sqlalchemy import or_, select

    from app.db.models import Sponsor

    m_start, m_end = month_bounds(year, month)
    p_year, p_month = _month_before(year, month)
    p_start, p_end = month_bounds(p_year, p_month)

    # Sponsor.starts_at/ends_at are TZAwareDateTime (reject naive); analytics
    # created_at is a plain naive-UTC DateTime. Use aware bounds for the overlap
    # query, the naive bounds (above) for the event-count windows.
    m_start_aware = m_start.replace(tzinfo=UTC)
    m_end_aware = m_end.replace(tzinfo=UTC)

    # Sponsors whose booking window overlapped the report month. Null bounds are
    # treated as open (active from/through forever).
    active = db.scalars(
        select(Sponsor).where(
            or_(Sponsor.starts_at.is_(None), Sponsor.starts_at < m_end_aware),
            or_(Sponsor.ends_at.is_(None), Sponsor.ends_at >= m_start_aware),
        )
    ).all()

    report = Report(year=year, month=month)
    for sp in active:
        report.rows.append(
            SponsorRow(
                sponsor_id=sp.id,
                name=sp.name,
                slot=sp.slot,
                impressions=_count_events(
                    db, sponsor_id=sp.id, name_like="home.%.impression", start=m_start, end=m_end
                ),
                clicks=_count_events(
                    db, sponsor_id=sp.id, name_eq="home.sponsor.click", start=m_start, end=m_end
                ),
                prev_impressions=_count_events(
                    db, sponsor_id=sp.id, name_like="home.%.impression", start=p_start, end=p_end
                ),
                prev_clicks=_count_events(
                    db, sponsor_id=sp.id, name_eq="home.sponsor.click", start=p_start, end=p_end
                ),
            )
        )
    # Most active first within the report.
    report.rows.sort(key=lambda r: (r.clicks + r.impressions), reverse=True)
    return report


def _ctr_str(ctr: float | None) -> str:
    return f"{ctr:.1%}" if ctr is not None else "n/a"


def _delta_str(cur: int, prev: int) -> str:
    d = cur - prev
    sign = "+" if d >= 0 else ""
    return f"{sign}{d}"


def render_text(report: Report) -> str:
    lines = [f"Sponsor performance — {report.label}", "=" * 40]
    if not report.rows:
        lines.append("No sponsors active this month.")
        return "\n".join(lines)
    for tier, rows in report.rows_by_tier:
        lines.append(f"\n[{tier.upper()}]")
        for r in rows:
            lines.append(
                f"  {r.name}: {r.impressions} impr ({_delta_str(r.impressions, r.prev_impressions)}), "
                f"{r.clicks} clicks ({_delta_str(r.clicks, r.prev_clicks)}), "
                f"CTR {_ctr_str(r.ctr)} (prev {_ctr_str(r.prev_ctr)})"
            )
    lines.append(
        "\nNote: per-event impressions are currently tracked for the spotlight "
        "tier only; other tiers show CTR n/a until instrumented."
    )
    return "\n".join(lines)


def _esc(s: str) -> str:
    from html import escape

    return escape(s or "")


def render_html(report: Report) -> str:
    parts = [f"<h2>Sponsor performance — {_esc(report.label)}</h2>"]
    if not report.rows:
        parts.append("<p>No sponsors active this month.</p>")
        return "\n".join(parts)
    for tier, rows in report.rows_by_tier:
        parts.append(f"<h3>{_esc(tier.title())}</h3>")
        parts.append(
            "<table border='1' cellpadding='6' cellspacing='0'>"
            "<tr><th>Sponsor</th><th>Impressions</th><th>Clicks</th>"
            "<th>CTR</th><th>Prev CTR</th></tr>"
        )
        for r in rows:
            parts.append(
                "<tr>"
                f"<td>{_esc(r.name)}</td>"
                f"<td>{r.impressions} ({_delta_str(r.impressions, r.prev_impressions)})</td>"
                f"<td>{r.clicks} ({_delta_str(r.clicks, r.prev_clicks)})</td>"
                f"<td>{_ctr_str(r.ctr)}</td>"
                f"<td>{_ctr_str(r.prev_ctr)}</td>"
                "</tr>"
            )
        parts.append("</table>")
    parts.append(
        "<p><em>Per-event impressions are currently tracked for the spotlight "
        "tier only; other tiers show CTR n/a until instrumented.</em></p>"
    )
    return "\n".join(parts)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monthly sponsor performance report (read-only).")
    parser.add_argument(
        "--month",
        help="Report month as YYYY-MM (default: the prior calendar month).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send the report email. Default is dry-run (print to stdout).",
    )
    parser.add_argument(
        "--to",
        help="Recipient override (default: REPORT_RECIPIENT env).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="INFO logging to stderr.")
    return parser.parse_args(argv)


def _resolve_month(arg: str | None) -> tuple[int, int]:
    if arg:
        y, m = arg.split("-")
        return int(y), int(m)
    return prior_month(_utcnow_naive())


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    try:
        year, month = _resolve_month(args.month)
    except (ValueError, AttributeError):
        print("--month must be YYYY-MM", file=sys.stderr)
        return 2

    from app.db.database import SessionLocal

    try:
        with SessionLocal() as db:
            report = gather_report(db, year, month)
    except Exception:
        logger.exception("sponsor_monthly_report: failed to build report")
        return 1

    subject = f"Hava sponsor report — {report.label}"
    html_body = render_html(report)
    text_body = render_text(report)

    if not args.execute:
        print(subject)
        print(text_body)
        return 0

    recipient = (args.to or os.environ.get("REPORT_RECIPIENT") or "").strip()
    if not recipient:
        print("--execute requires --to or REPORT_RECIPIENT", file=sys.stderr)
        return 2

    from app.auth.email_sender import send_alert_email

    try:
        send_alert_email(
            to_email=recipient, subject=subject, html_body=html_body, text_body=text_body
        )
    except Exception:
        logger.exception("sponsor_monthly_report: send failed")
        return 1
    logger.info("sponsor report sent to %s for %s", recipient, report.label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
