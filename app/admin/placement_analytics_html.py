"""Admin read-only analytics over the ``analytics_events`` table (Phase G).

The existing ``/admin/analytics`` page reports chat-query demand and the event
moderation funnel. This page complements it with the placement / sponsor /
chat-surface render+click telemetry that lands in ``analytics_events`` — "which
slot, which surface, which provider, how often, and what's the click-through" —
the data an operator needs to judge whether a paid placement is performing.

Read-only by construction: every query is a SELECT, no row is written or
mutated, and the page is admin-cookie gated like every other Phase 5 admin view.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.admin.nav_html import admin_phase5_nav_html
from app.db.database import get_db
from app.db.models import AnalyticsEvent, Provider

_WINDOW_DAYS: dict[str, int | None] = {"7d": 7, "30d": 30, "all": None}
_DEFAULT_WINDOW = "7d"


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%b %d, %Y %I:%M %p")


def _ctr(clicks: int, impressions: int) -> str:
    if impressions <= 0:
        return "—"
    return f"{(100.0 * clicks / impressions):.1f}%"


def _snippet(value: str | None, limit: int) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    return raw if len(raw) <= limit else raw[:limit].rstrip() + "..."


def _window_links(active: str) -> str:
    parts: list[str] = []
    for key in ("7d", "30d", "all"):
        cls = "active" if key == active else ""
        parts.append(
            f'<a class="wbtn {cls}" href="/admin/placement-analytics?window={key}">{key}</a>'
        )
    return "".join(parts)


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]], empty: str) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    if not rows:
        return (
            f"<table><thead><tr>{head}</tr></thead><tbody>"
            f'<tr><td colspan="{len(headers)}" class="empty">{_esc(empty)}</td></tr>'
            "</tbody></table>"
        )
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _nav_shell(title: str, inner: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_esc(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #212529;
      line-height: 1.45; padding-bottom: 48px; }}
    .wrap {{ max-width: 980px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
    h2 {{ font-size: 1.05rem; margin: 28px 0 10px; color: #343a40; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; margin-bottom: 14px; }}
    .nav {{ margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .nav a {{ color: #0d6efd; font-weight: 600; text-decoration: none; }}
    .window {{ margin: 8px 0 14px; display: flex; gap: 8px; }}
    .wbtn {{ color: #0d6efd; text-decoration: none; border: 1px solid #dee2e6; border-radius: 999px;
      padding: 4px 10px; font-size: 0.88rem; }}
    .wbtn.active {{ font-weight: 700; text-decoration: underline; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-bottom: 8px; }}
    th, td {{ border: 1px solid #dee2e6; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f8f9fa; font-weight: 600; }}
    tbody tr:nth-child(even) {{ background: #fcfcfc; }}
    .empty {{ color: #6c757d; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.82rem; }}
  </style>
</head>
<body>
  <div class="wrap">
{admin_phase5_nav_html()}
    {inner}
  </div>
</body>
</html>"""


def _render(db: Session, win: str) -> str:
    days = _WINDOW_DAYS[win]
    cutoff = None if days is None else datetime.now(timezone.utc) - timedelta(days=days)

    def _scoped(stmt):
        return stmt if cutoff is None else stmt.where(AnalyticsEvent.created_at >= cutoff)

    total = int(db.execute(_scoped(select(func.count(AnalyticsEvent.id)))).scalar() or 0)

    # By event name.
    by_name = db.execute(
        _scoped(
            select(AnalyticsEvent.event_name, func.count().label("n"))
            .group_by(AnalyticsEvent.event_name)
        ).order_by(desc("n")).limit(30)
    ).all()
    name_rows = [(_esc(n or "(none)"), str(int(c))) for n, c in by_name]

    # By render surface (slot_origin).
    by_surface = db.execute(
        _scoped(
            select(func.coalesce(AnalyticsEvent.slot_origin, "(none)"), func.count().label("n"))
            .group_by(AnalyticsEvent.slot_origin)
        ).order_by(desc("n")).limit(30)
    ).all()
    surface_rows = [(_esc(str(s)), str(int(c))) for s, c in by_surface]

    # Impressions vs clicks (CTR) by slot — event_name carries the ".impression"
    # / ".click" suffix, slot is the inventory unit (marquee / spotlight / ...).
    imp = func.sum(case((AnalyticsEvent.event_name.like("%impression%"), 1), else_=0)).label("imp")
    clk = func.sum(case((AnalyticsEvent.event_name.like("%click%"), 1), else_=0)).label("clk")
    ctr = db.execute(
        _scoped(
            select(func.coalesce(AnalyticsEvent.slot, "(none)"), imp, clk)
            .group_by(AnalyticsEvent.slot)
        ).order_by(desc("imp"))
    ).all()
    ctr_rows = [
        (_esc(str(slot)), str(int(i or 0)), str(int(k or 0)), _ctr(int(k or 0), int(i or 0)))
        for slot, i, k in ctr
    ]

    # Top providers by event volume.
    top_prov = db.execute(
        _scoped(
            select(
                AnalyticsEvent.provider_id,
                func.coalesce(Provider.provider_name, "(unknown)"),
                func.count().label("n"),
            )
            .join(Provider, Provider.id == AnalyticsEvent.provider_id, isouter=True)
            .where(AnalyticsEvent.provider_id.is_not(None))
            .group_by(AnalyticsEvent.provider_id, Provider.provider_name)
        ).order_by(desc("n")).limit(25)
    ).all()
    prov_rows = [
        (_esc(name), f'<span class="mono">{_esc(str(pid))}</span>', str(int(c)))
        for pid, name, c in top_prov
    ]

    # Recent events.
    recent = db.execute(
        _scoped(
            select(
                AnalyticsEvent.created_at,
                AnalyticsEvent.event_name,
                AnalyticsEvent.slot,
                AnalyticsEvent.slot_origin,
                AnalyticsEvent.provider_id,
                AnalyticsEvent.payload_json,
            )
        ).order_by(desc(AnalyticsEvent.created_at)).limit(25)
    ).all()
    recent_rows: list[tuple[str, ...]] = []
    for created_at, name, slot, origin, pid, payload in recent:
        try:
            payload_s = json.dumps(payload, default=str) if payload else "—"
        except (TypeError, ValueError):
            payload_s = "—"
        recent_rows.append(
            (
                _esc(_fmt_dt(created_at)),
                _esc(name or "(none)"),
                _esc(slot or "—"),
                _esc(origin or "—"),
                f'<span class="mono">{_esc(str(pid) if pid else "—")}</span>',
                f'<span class="mono">{_esc(_snippet(payload_s, 80))}</span>',
            )
        )

    inner = f"""<h1>Placement &amp; surface analytics</h1>
<p class="sub">Read-only over <code>analytics_events</code> — render/click telemetry by event,
surface, slot, and provider. {total} events in window.</p>
<div class="window">{_window_links(win)}</div>

<h2>Events by name</h2>
{_table(("Event name", "Count"), name_rows, "No analytics events in this window.")}

<h2>By render surface</h2>
{_table(("Surface (slot_origin)", "Count"), surface_rows, "No surface data in this window.")}

<h2>Impressions, clicks &amp; CTR by slot</h2>
{_table(("Slot", "Impressions", "Clicks", "CTR"), ctr_rows, "No impression/click data in this window.")}

<h2>Top providers by event volume</h2>
{_table(("Provider", "provider_id", "Events"), prov_rows, "No provider-attributed events in this window.")}

<h2>Recent events (latest 25)</h2>
{_table(
        ("Created", "Event", "Slot", "Surface", "provider_id", "Payload"),
        recent_rows,
        "No recent events.",
    )}
"""
    return _nav_shell("Placement analytics", inner)


def register_placement_analytics_html_routes(router: APIRouter) -> None:
    @router.get("/placement-analytics", response_class=HTMLResponse, response_model=None)
    def placement_analytics_page(
        request: Request,
        window: str = _DEFAULT_WINDOW,
        db: Session = Depends(get_db),
    ) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        win = window if window in _WINDOW_DAYS else _DEFAULT_WINDOW
        return HTMLResponse(_render(db, win))
