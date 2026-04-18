from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import Date, and_, asc, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from app.admin.auth import (
    COOKIE_NAME,
    MAX_AGE_SECONDS,
    admin_password_debug_info,
    admin_password_ok,
    sign_admin_cookie,
    verify_admin_cookie,
)
from app.db.database import DATABASE_URL, get_db
from app.db.models import ChatLog, Event, Program
from app.db.seed import run_seed
from app.schemas.program import ProgramCreate

router = APIRouter(prefix="/admin", tags=["admin"])


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _analytics_cutoff(days: int) -> datetime:
    return _utc_now() - timedelta(days=days)


def _zero_result_assistant_condition(message_col):
    """Heuristic: assistant reply text suggests no events (chat_logs has no structured count)."""
    mlow = func.lower(message_col)
    zeroish = or_(
        mlow.like("%in the system yet%"),
        mlow.like("%nothing on for that time%"),
        mlow.like("%nothing yet!%"),
        mlow.like("%events on right now%"),
        mlow.like("%permanent spot in havasu%"),
        mlow.like("%nothing is scheduled right now%"),
        mlow.like("%want me to broaden the search%"),
        mlow.like("%want me to show you other%"),
    )
    has_event_listing = or_(
        mlow.like("%here's what i found:%"),
        mlow.like("%found one that might work:%"),
    )
    return and_(zeroish, ~has_event_listing)


def _query_top_user_messages(db: Session, *, days: int, limit: int) -> list[tuple[str, int]]:
    cutoff = _analytics_cutoff(days)
    qkey = func.lower(func.trim(ChatLog.message)).label("qkey")
    cnt = func.count().label("cnt")
    stmt = (
        select(qkey, cnt)
        .where(ChatLog.role == "user")
        .where(ChatLog.created_at >= cutoff)
        .where(func.length(func.trim(ChatLog.message)) >= 2)
        .group_by(qkey)
        .order_by(desc(cnt), qkey)
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    out: list[tuple[str, int]] = []
    for qkey_v, cnt in rows:
        if not qkey_v or not str(qkey_v).strip():
            continue
        out.append((str(qkey_v).strip(), int(cnt)))
    return out


def _query_zero_result_user_messages(db: Session, *, days: int, limit: int) -> list[tuple[str, int]]:
    """Pairs prior user message with assistant reply using LAG (same session, ordered by time)."""
    cutoff = _analytics_cutoff(days)
    lag_role = (
        func.lag(ChatLog.role).over(partition_by=ChatLog.session_id, order_by=ChatLog.created_at).label("prev_role")
    )
    lag_msg = (
        func.lag(ChatLog.message)
        .over(partition_by=ChatLog.session_id, order_by=ChatLog.created_at)
        .label("prev_msg")
    )
    # LAG must see full session history so the row before each assistant reply is correct.
    subq = (
        select(
            ChatLog.role,
            ChatLog.message,
            ChatLog.intent,
            ChatLog.created_at,
            lag_role,
            lag_msg,
        ).subquery("clw")
    )
    prev_msg = subq.c.prev_msg
    qkey = func.lower(func.trim(prev_msg)).label("qk")
    cnt = func.count().label("cnt")
    stmt = (
        select(qkey, cnt)
        .where(subq.c.role == "assistant")
        .where(subq.c.created_at >= cutoff)
        .where(subq.c.prev_role == "user")
        .where(prev_msg.isnot(None))
        .where(func.length(func.trim(prev_msg)) >= 2)
        .where(subq.c.intent.in_(("SEARCH_EVENTS", "REFINEMENT", "LISTING_INTENT")))
        .where(_zero_result_assistant_condition(subq.c.message))
        .group_by(qkey)
        .order_by(desc(cnt), qkey)
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    out: list[tuple[str, int]] = []
    for qkey_v, cnt in rows:
        if not qkey_v or not str(qkey_v).strip():
            continue
        out.append((str(qkey_v).strip(), int(cnt)))
    return out


def _chatlog_day_column():
    """SQLite stores datetimes in a shape where cast-as-Date can confuse processors; use strftime on SQLite."""
    if DATABASE_URL.strip().lower().startswith("sqlite"):
        return func.strftime("%Y-%m-%d", ChatLog.created_at).label("day")
    return cast(ChatLog.created_at, Date).label("day")


def _query_daily_active_sessions(db: Session, *, days: int) -> list[tuple[date | str, int]]:
    cutoff = _analytics_cutoff(days)
    day_col = _chatlog_day_column()
    inner = (
        select(day_col, ChatLog.session_id)
        .where(ChatLog.created_at >= cutoff)
        .group_by(day_col, ChatLog.session_id)
        .subquery("das")
    )
    stmt = (
        select(inner.c.day, func.count().label("n"))
        .select_from(inner)
        .group_by(inner.c.day)
        .order_by(inner.c.day)
    )
    rows = db.execute(stmt).all()
    out: list[tuple[date | str, int]] = []
    for d, n in rows:
        if d is None:
            continue
        if isinstance(d, datetime):
            out.append((d.date(), int(n)))
        elif isinstance(d, date) and not isinstance(d, datetime):
            out.append((d, int(n)))
        else:
            out.append((str(d), int(n)))
    return out


def _query_event_funnel_30d(db: Session) -> dict[str, int]:
    cutoff = _analytics_cutoff(30)
    stmt = select(Event.status, func.count().label("n")).where(Event.created_at >= cutoff).group_by(Event.status)
    rows = db.execute(stmt).all()
    by_status = {str(status or ""): int(n) for status, n in rows}
    return {
        "total": sum(by_status.values()),
        "pending_review": by_status.get("pending_review", 0),
        "live": by_status.get("live", 0),
        "deleted": by_status.get("deleted", 0),
    }


def _bar_chars(count: int, max_count: int, width: int = 32) -> str:
    if max_count <= 0 or count <= 0:
        return ""
    filled = max(1, int(round(width * count / max_count)))
    return "█" * min(filled, width)


def _table_rows_html(rows: list[tuple[str, ...]], headers: tuple[str, ...]) -> str:
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    if not rows:
        return f"<thead><tr>{th}</tr></thead><tbody><tr><td colspan=\"{len(headers)}\">No data yet</td></tr></tbody>"
    body = ""
    for tup in rows:
        body += "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in tup) + "</tr>"
    return f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody>"


def _analytics_page_html(db: Session) -> str:
    top_q = _query_top_user_messages(db, days=7, limit=20)
    top_z = _query_zero_result_user_messages(db, days=7, limit=20)
    daily = _query_daily_active_sessions(db, days=30)
    funnel = _query_event_funnel_30d(db)

    top_rows = [(q, str(c)) for q, c in top_q]
    zero_rows = [(q, str(c)) for q, c in top_z]

    max_sess = max((n for _, n in daily), default=0)
    daily_rows: list[tuple[str, str, str]] = []
    for d, n in daily:
        day_s = d.isoformat() if hasattr(d, "isoformat") else str(d)
        daily_rows.append((day_s, str(n), _bar_chars(n, max_sess)))

    total_ev = funnel["total"]
    approved = funnel["live"]
    pending = funnel["pending_review"]
    rejected = funnel["deleted"]
    decided = approved + rejected
    rate_s = f"{100.0 * approved / decided:.1f}%" if decided > 0 else "—"

    funnel_rows = [
        ("Total events created (30d)", str(total_ev)),
        ("Live (approved)", str(approved)),
        ("Pending review", str(pending)),
        ("Rejected / removed (deleted)", str(rejected)),
        ("Approval rate (live / (live + deleted))", rate_s),
    ]

    finding = (
        "<p class=\"note\"><strong>Note on zero-result queries:</strong> <code>chat_logs</code> stores "
        "<code>session_id</code>, <code>message</code>, <code>role</code>, <code>intent</code>, and "
        "<code>created_at</code> only — there is no stored event count. This section pairs each assistant "
        "reply with the immediately preceding user message in the same session (SQL <code>LAG</code>) and "
        "filters assistant text with substring heuristics for honest no-match / empty-window copy. "
        "It excludes replies that look like a populated results list "
        "(<code>Here's what I found:</code>, <code>Found one that might work</code>). "
        "Some edge cases (e.g. unusual wording) may be misclassified.</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Admin — Analytics</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #212529;
      line-height: 1.45; padding-bottom: 48px; }}
    .wrap {{ max-width: 900px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
    h2 {{ font-size: 1.05rem; margin: 28px 0 10px; color: #343a40; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-bottom: 8px; }}
    th, td {{ border: 1px solid #dee2e6; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f8f9fa; font-weight: 600; }}
    tbody tr:nth-child(even) {{ background: #fcfcfc; }}
    .nav {{ margin-bottom: 20px; }}
    .nav a {{ color: #0d6efd; font-weight: 600; text-decoration: none; }}
    .nav a:hover {{ text-decoration: underline; }}
    .note {{ font-size: 0.82rem; color: #6c757d; margin-top: 32px; line-height: 1.5; }}
    code {{ font-size: 0.85em; background: #f1f3f5; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <nav class="nav"><a href="/admin?tab=pending&amp;sort=newest">Back to events</a></nav>
    <h1>Analytics</h1>
    <p class="sub">Last 7 days for queries · last 30 days for sessions and event funnel. Aggregates run in SQL.</p>

    <h2>Top user queries (7 days)</h2>
    <p class="sub">Grouped by lowercased, trimmed message (≥2 characters).</p>
    <table>{_table_rows_html([(a, b) for a, b in top_rows], ("Query", "Count"))}</table>

    <h2>Zero-result queries (7 days)</h2>
    <p class="sub">User message before an assistant reply that looks like no matching events (heuristic; see note below).</p>
    <table>{_table_rows_html([(a, b) for a, b in zero_rows], ("Query", "Count"))}</table>

    <h2>Daily active sessions (30 days)</h2>
    <p class="sub">Distinct <code>session_id</code> per calendar day.</p>
    <table>{_table_rows_html(daily_rows, ("Date", "Sessions", "Trend"))}</table>

    <h2>Event funnel (30 days)</h2>
    <p class="sub">Rows in <code>events</code> created in the last 30 days by status.</p>
    <table>{_table_rows_html(funnel_rows, ("Metric", "Value"))}</table>

    {finding}
  </div>
</body>
</html>"""


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%b %d, %Y %I:%M %p")


def _countdown(admin_review_by: datetime | None) -> str:
    if not admin_review_by:
        return "—"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end = admin_review_by
    if end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    sec = (end - now).total_seconds()
    if sec <= 0:
        return "Overdue"
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    if h >= 48:
        d = int(sec // 86400)
        return f"{d} days left"
    if h > 0:
        return f"{h} hours left"
    if m > 0:
        return f"{m} minutes left"
    return "Under a minute left"


def _escape(s: str | None) -> str:
    if s is None:
        return "—"
    return html.escape(s, quote=True)


def _embedding_matches_deterministic_1536(ev: Event) -> bool:
    """True when stored vector equals search.py's deterministic 1536 path for this event's fields."""
    emb = ev.embedding
    if not emb or not isinstance(emb, list) or len(emb) != 1536:
        return False
    from app.core.extraction import _embedding_input
    from app.core.search import _deterministic_embedding_1536

    text = _embedding_input(
        {
            "title": ev.title or "",
            "location_name": ev.location_name or "",
            "description": ev.description or "",
            "event_url": ev.event_url or "",
        }
    )
    synthetic = _deterministic_embedding_1536(text)
    if len(synthetic) != len(emb):
        return False
    return all(abs(float(a) - float(b)) < 1e-4 for a, b in zip(synthetic, emb))


def _embedding_badge_html(ev: Event) -> str:
    """Badge for semantic search readiness: OpenAI 1536 vs deterministic fallbacks."""
    emb = ev.embedding
    if not emb or not isinstance(emb, list) or len(emb) == 0:
        return '<span class="embed-badge embed-none">No embedding</span>'
    if len(emb) == 32:
        # extraction._deterministic_embedding dimensions
        return '<span class="embed-badge embed-fallback">Fallback embedding</span>'
    if len(emb) == 1536:
        if _embedding_matches_deterministic_1536(ev):
            return '<span class="embed-badge embed-fallback">Fallback embedding</span>'
        return '<span class="embed-badge embed-ok">AI-indexed</span>'
    return f'<span class="embed-badge embed-warn">Embedding ({len(emb)} dims)</span>'


def _tags_pills_html(ev: Event) -> str:
    """Tag pills matching /events/{{id}} permalink styling; empty if no tags."""
    raw = ev.tags or []
    labels = [str(t).strip() for t in raw if str(t).strip()]
    if not labels:
        return ""
    nodes = "".join(f'<span class="tag">{_escape(t)}</span>' for t in labels)
    return f'<div class="tag-wrap">{nodes}</div>'


def _card_metadata_row(ev: Event, mode: Literal["pending", "live"]) -> str:
    parts: list[str] = []
    parts.append(f"Submitted {_fmt_dt(ev.created_at)}")
    if mode == "pending" and ev.admin_review_by:
        cd = _countdown(ev.admin_review_by)
        parts.append(f"Review by {_fmt_dt(ev.admin_review_by)} · {_escape(cd)}")
    cn = (ev.contact_name or "").strip()
    cp = (ev.contact_phone or "").strip()
    if cn and cp:
        parts.append(f"Contact: {_escape(cn)} · {_escape(cp)}")
    elif cn:
        parts.append(f"Contact: {_escape(cn)}")
    elif cp:
        parts.append(f"Contact: {_escape(cp)}")
    inner = " · ".join(parts)
    return f'<p class="card-meta-muted">{inner}</p>'


def _sort_controls_html(tab: str, current_sort: str) -> str:
    """Links to reorder the active tab's list."""
    opts = [
        ("newest", "Newest first"),
        ("oldest", "Oldest first"),
        ("event_date", "Event date ↑"),
    ]
    links: list[str] = []
    for key, label in opts:
        active = " sort-opt-active" if key == current_sort else ""
        href = f"/admin?tab={tab}&sort={key}"
        links.append(f'<a class="sort-opt{active}" href="{href}">{html.escape(label)}</a>')
    joined = " · ".join(links)
    return f'<div class="sort-bar"><span class="sort-label">Sort:</span> {joined}</div>'


def _login_html(error: bool = False) -> str:
    err = (
        '<p class="err">That password does not match. Try again.</p>'
        if error
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Admin login</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #f8f9fa; color: #212529; }}
    .box {{ max-width: 400px; margin: 40px auto; background: #fff; padding: 28px; border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    h1 {{ font-size: 1.25rem; margin: 0 0 8px; }}
    p {{ color: #6c757d; font-size: 0.95rem; margin: 0 0 20px; }}
    label {{ display: block; font-weight: 600; margin-bottom: 8px; }}
    input[type=password] {{ width: 100%; padding: 14px 16px; font-size: 1.05rem; border: 1px solid #dee2e6;
      border-radius: 10px; min-height: 48px; }}
    button {{ margin-top: 16px; width: 100%; padding: 14px 20px; font-size: 1.05rem; font-weight: 600;
      border: none; border-radius: 10px; background: #0d6efd; color: #fff; min-height: 48px; cursor: pointer; }}
    .err {{ color: #b02a37; font-weight: 500; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>Admin</h1>
    <p>Enter the admin password to continue.</p>
    {err}
    <form method="post" action="/admin/login">
      <label for="pw">Password</label>
      <input id="pw" name="password" type="password" autocomplete="current-password" required />
      <button type="submit">Sign in</button>
    </form>
  </div>
</body>
</html>"""


def _dashboard_html_simple(pending: list[Event], live: list[Event], tab: str, sort: str) -> str:
    if tab == "live":
        body_inner = "\n".join(_card_html(e, "live") for e in live) or '<p class="empty">No live events.</p>'
        title = "Live events"
    else:
        body_inner = "\n".join(_card_html(e, "pending") for e in pending) or '<p class="empty">No events pending review.</p>'
        title = "Pending review"

    sort_bar = _sort_controls_html(tab, sort)
    pending_href = "/admin?tab=pending&sort=newest"
    live_href = "/admin?tab=live&sort=event_date"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Admin — {title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #212529;
      line-height: 1.45; padding-bottom: 48px; }}
    header {{ max-width: 720px; margin: 0 auto 16px; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 4px; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; }}
    .tabs {{ display: flex; gap: 8px; max-width: 720px; margin: 0 auto 16px; flex-wrap: wrap; }}
    .tabs a {{
      flex: 1; min-width: 140px; text-align: center; padding: 14px 16px; border-radius: 10px;
      text-decoration: none; font-weight: 600; border: 2px solid #dee2e6; color: #495057; background: #f8f9fa;
      min-height: 48px; display: flex; align-items: center; justify-content: center;
    }}
    .tabs a.active {{ border-color: #0d6efd; background: #e7f1ff; color: #0a58ca; }}
    .sort-bar {{ max-width: 720px; margin: 0 auto 14px; font-size: 0.88rem; color: #495057; }}
    .sort-label {{ font-weight: 600; color: #868e96; margin-right: 6px; }}
    .sort-opt {{ color: #0d6efd; text-decoration: none; }}
    .sort-opt:hover {{ text-decoration: underline; }}
    .sort-opt-active {{ font-weight: 700; color: #0a58ca; text-decoration: underline; }}
    .panel {{ max-width: 720px; margin: 0 auto; }}
    .card {{ border: 1px solid #e9ecef; border-radius: 12px; padding: 16px; margin-bottom: 14px; background: #fafafa; }}
    .card h3 {{ margin: 0 0 8px; font-size: 1.1rem; }}
    .card-top {{ display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 8px; }}
    .card-top .tag-wrap {{ flex: 1 1 auto; min-width: 0; }}
    .card-badges {{ flex: 0 0 auto; text-align: right; font-size: 0.82rem; }}
    .tag-wrap {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .tag {{
      display: inline-flex; align-items: center; padding: 4px 10px; border: 1px solid #dee2e6;
      background: #fff; border-radius: 999px; font-size: 0.85rem; color: #495057;
    }}
    .embed-badge {{ display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 600; }}
    .embed-ok {{ background: #d1e7dd; color: #0f5132; }}
    .embed-fallback {{ background: #fff3cd; color: #664d03; }}
    .embed-none {{ background: #e2e3e5; color: #41464b; }}
    .embed-warn {{ background: #f8d7da; color: #842029; }}
    .pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }}
    .pill-ok {{ background: #d1e7dd; color: #0f5132; }}
    .pill-info {{ background: #cfe2ff; color: #084298; }}
    .pill-warn {{ background: #fff3cd; color: #664d03; }}
    .pill-muted {{ background: #e2e3e5; color: #41464b; }}
    .card-meta-muted {{ margin: 0 0 10px; font-size: 0.82rem; color: #868e96; line-height: 1.4; word-break: break-word; }}
    .meta {{ margin: 6px 0; font-size: 0.92rem; color: #495057; word-break: break-word; }}
    .label {{ color: #868e96; font-weight: 600; margin-right: 6px; }}
    .desc {{ white-space: pre-wrap; margin: 10px 0; }}
    .actions {{ margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
    .btn {{ min-height: 48px; min-width: 120px; padding: 12px 18px; font-size: 1rem; font-weight: 600;
      border: none; border-radius: 10px; cursor: pointer; }}
    .btn.ok {{ background: #198754; color: #fff; }}
    .btn.bad {{ background: #dc3545; color: #fff; }}
    .empty {{ color: #6c757d; padding: 24px; text-align: center; }}
    a {{ color: #0d6efd; }}
  </style>
</head>
<body>
  <header>
    <h1>Events</h1>
    <p class="sub">{title}</p>
  </header>
  <nav class="tabs">
    <a class="{('active' if tab == 'pending' else '')}" href="{pending_href}">Pending review</a>
    <a class="{('active' if tab == 'live' else '')}" href="{live_href}">Live events</a>
    <a class="{('active' if tab == 'programs' else '')}" href="/admin?tab=programs">Programs</a>
    <a href="/admin/analytics">Analytics</a>
  </nav>
  <div class="panel">
    {sort_bar}
    {body_inner}
  </div>
</body>
</html>"""


def _card_html(ev: Event, mode: Literal["pending", "live"]) -> str:
    url = (ev.event_url or "").strip()
    link = (
        f'<a href="{_escape(url)}" target="_blank" rel="noopener">{_escape(url)}</a>'
        if url
        else "—"
    )
    if mode == "pending":
        actions = f"""
      <form method="post" action="/admin/event/{_escape(ev.id)}/approve" style="display:inline">
        <button type="submit" class="btn ok">Approve</button>
      </form>
      <form method="post" action="/admin/event/{_escape(ev.id)}/reject" style="display:inline">
        <button type="submit" class="btn bad">Reject</button>
      </form>"""
    else:
        actions = f"""
      <form method="post" action="/admin/event/{_escape(ev.id)}/delete" style="display:inline"
            onsubmit="return confirm('Delete this event?');">
        <button type="submit" class="btn bad">Delete</button>
      </form>"""

    tags_block = _tags_pills_html(ev)
    badge_html = _embedding_badge_html(ev)
    source_badge = _source_verified_badge(
        getattr(ev, "source", None), bool(getattr(ev, "verified", False))
    )
    preview = ""
    if mode == "live":
        preview = (
            f'<a href="/events/{_escape(ev.id)}" target="_blank" rel="noopener">Preview as user</a>'
        )
    badges_cell = f'<div class="card-badges">{source_badge} {badge_html}'
    if preview:
        badges_cell += f'<div style="margin-top:6px">{preview}</div>'
    badges_cell += "</div>"

    top_row = f'<div class="card-top">{tags_block}{badges_cell}</div>' if tags_block else f'<div class="card-top"><div></div>{badges_cell}</div>'

    meta_row = _card_metadata_row(ev, mode)

    return f"""
    <article class="card">
      <h3>{_escape(ev.title)}</h3>
      {top_row}
      {meta_row}
      <p class="meta"><span class="label">When</span> {_escape(ev.date.isoformat())} · {_escape(ev.start_time.isoformat())}</p>
      <p class="meta"><span class="label">Where</span> {_escape(ev.location_name)}</p>
      <p class="desc">{_escape(ev.description)}</p>
      <p class="meta"><span class="label">Link</span> {link}</p>
      <div class="actions">{actions}</div>
    </article>"""


@router.get("/debug-pw")
def admin_debug_pw() -> dict[str, bool | int]:
    """Temporary: confirm ADMIN_PASSWORD is visible to the process (no secret leaked)."""
    return admin_password_debug_info()


@router.get("/login", response_class=HTMLResponse)
def admin_login_page() -> HTMLResponse:
    return HTMLResponse(_login_html(error=False))


@router.post("/login", response_model=None)
def admin_login_submit(
    request: Request,
    password: str = Form(...),
) -> RedirectResponse | HTMLResponse:
    if not admin_password_ok(password):
        return HTMLResponse(_login_html(error=True), status_code=401)
    resp = RedirectResponse(url="/admin?tab=pending", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        sign_admin_cookie(),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp


def _effective_sort(tab: str, sort: str | None) -> str:
    allowed = frozenset({"newest", "oldest", "event_date"})
    if sort in allowed:
        return sort
    return "newest" if tab == "pending" else "event_date"


@router.get("", response_class=HTMLResponse, response_model=None)
@router.get("/", response_class=HTMLResponse, response_model=None)
def admin_dashboard(
    request: Request,
    tab: str = "pending",
    sort: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    if tab not in ("pending", "live", "programs"):
        tab = "pending"

    if tab == "programs":
        programs = (
            db.query(Program)
            .order_by(desc(Program.is_active), desc(Program.updated_at))
            .all()
        )
        return HTMLResponse(_programs_tab_html(programs))

    sort_eff = _effective_sort(tab, sort)

    pending_q = db.query(Event).filter(Event.status == "pending_review")
    if sort_eff == "newest":
        pending = pending_q.order_by(desc(Event.created_at)).all()
    elif sort_eff == "oldest":
        pending = pending_q.order_by(asc(Event.created_at)).all()
    else:
        pending = pending_q.order_by(asc(Event.date), asc(Event.start_time)).all()

    live_q = db.query(Event).filter(Event.status == "live")
    if sort_eff == "newest":
        live = live_q.order_by(desc(Event.created_at)).all()
    elif sort_eff == "oldest":
        live = live_q.order_by(asc(Event.created_at)).all()
    else:
        live = live_q.order_by(asc(Event.date), asc(Event.start_time)).all()

    return HTMLResponse(_dashboard_html_simple(pending, live, tab, sort_eff))


@router.get("/analytics", response_class=HTMLResponse, response_model=None)
def admin_analytics(request: Request, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    return HTMLResponse(_analytics_page_html(db))


def _apply_status(event_id: str, db: Session, status: str) -> None:
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    ev.status = status
    db.commit()


@router.post("/event/{event_id}/approve", response_model=None)
def admin_approve(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    _apply_status(event_id, db, "live")
    return RedirectResponse(url="/admin?tab=pending", status_code=303)


@router.post("/event/{event_id}/reject", response_model=None)
def admin_reject(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    _apply_status(event_id, db, "deleted")
    return RedirectResponse(url="/admin?tab=pending", status_code=303)


@router.post("/event/{event_id}/delete", response_model=None)
def admin_delete(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    _apply_status(event_id, db, "deleted")
    return RedirectResponse(url="/admin?tab=live", status_code=303)


class AdminReviewBody(BaseModel):
    action: Literal["approve", "reject"]


@router.post("/review/{event_id}")
def admin_review_json(
    request: Request,
    event_id: str,
    body: AdminReviewBody,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """JSON API for tests / integrations — requires admin cookie."""
    redir = _guard(request)
    if redir:
        raise HTTPException(status_code=401, detail="Not authenticated")
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if body.action == "approve":
        event.status = "live"
    else:
        event.status = "deleted"
    db.commit()
    db.refresh(event)
    return {"id": event.id, "status": event.status}


@router.post("/reseed")
def admin_reseed(request: Request, db: Session = Depends(get_db)) -> dict[str, int]:
    """One-time ops: remove seed rows and re-insert with fresh embeddings (admin cookie)."""
    redir = _guard(request)
    if redir:
        raise HTTPException(status_code=401, detail="Not authenticated")
    deleted = db.query(Event).filter(Event.created_by == "seed").delete(synchronize_session=False)
    db.commit()
    inserted, skipped = run_seed(skip_init=True)
    return {"deleted": deleted, "inserted": inserted, "skipped": skipped}


@router.post("/reembed-all")
def admin_reembed_all(request: Request, db: Session = Depends(get_db)) -> dict[str, int]:
    """One-time ops: regenerate embeddings for every event using the real OpenAI model."""
    redir = _guard(request)
    if redir:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from app.core.extraction import _embedding_input, generate_embedding

    updated = 0
    for event in db.query(Event).all():
        partial = {
            "title": event.title or "",
            "location_name": event.location_name or "",
            "description": event.description or "",
            "event_url": event.event_url or "",
        }
        event.embedding = generate_embedding(_embedding_input(partial))
        updated += 1
    db.commit()
    return {"updated": updated}


@router.post("/retag-all")
def admin_retag_all(request: Request, db: Session = Depends(get_db)) -> dict[str, int]:
    """One-time ops: regenerate tags for every event using the AI tag model."""
    redir = _guard(request)
    if redir:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from app.core.extraction import generate_event_tags

    updated = 0
    for event in db.query(Event).all():
        partial = {
            "title": event.title or "",
            "location_name": event.location_name or "",
            "description": event.description or "",
            "event_url": event.event_url or "",
        }
        event.tags = generate_event_tags(partial)
        updated += 1
    db.commit()
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Programs admin (Session Z-3)
# ---------------------------------------------------------------------------

_PROGRAM_DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_PROGRAM_SOURCES = ("admin", "provider", "parent", "scraped")


def _program_status_badge(p: Program) -> str:
    if p.is_active:
        return '<span class="pill pill-ok">Active</span>'
    return '<span class="pill pill-muted">Inactive</span>'


def _source_verified_badge(source: str | None, verified: bool) -> str:
    """Two-tier source badge (Session AA-1).

    Green "Verified" for admin or claimed provider, yellow "Provider
    (unclaimed)" for provider-sourced but not yet verified, blue "Parent"
    for community submissions, gray "Scraped" for scraped rows.
    """
    src = (source or "admin").lower()
    if src == "admin":
        return '<span class="pill pill-ok">Verified</span>'
    if src == "provider":
        if verified:
            return '<span class="pill pill-ok">Verified provider</span>'
        return '<span class="pill pill-warn">Provider (unclaimed)</span>'
    if src == "parent":
        return '<span class="pill pill-info">Parent</span>'
    if src == "scraped":
        return '<span class="pill pill-muted">Scraped</span>'
    return f'<span class="pill pill-muted">{html.escape(src.capitalize())}</span>'


def _program_tag_pills(p: Program) -> str:
    tags = [str(t) for t in (p.tags or []) if str(t).strip()]
    if not tags:
        return ""
    parts = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)
    return f'<div class="tag-wrap">{parts}</div>'


def _format_schedule_days_admin(days: list[str]) -> str:
    if not days:
        return "schedule TBD"
    ordered = sorted(
        {str(d).lower() for d in days if isinstance(d, str)},
        key=lambda d: _PROGRAM_DAYS.index(d) if d in _PROGRAM_DAYS else 99,
    )
    labels = [d.capitalize() for d in ordered]
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} & {labels[1]}"
    return ", ".join(labels[:-1]) + f" & {labels[-1]}"


def _format_program_age(p: Program) -> str:
    if p.age_min is None and p.age_max is None:
        return "All ages"
    if p.age_min is not None and p.age_max is not None:
        return f"Ages {p.age_min}–{p.age_max}"
    if p.age_min is not None:
        return f"Ages {p.age_min}+"
    return f"Up to age {p.age_max}"


def _program_card_admin_html(p: Program) -> str:
    schedule_line = (
        f"Every {_format_schedule_days_admin(list(p.schedule_days or []))}"
        f" • {html.escape(p.schedule_start_time or '')}–{html.escape(p.schedule_end_time or '')}"
    )
    age_line = _format_program_age(p)
    cost_line = (p.cost or "").strip() or "—"
    location_line = p.location_name or "—"
    if p.location_address:
        location_line += f" · {p.location_address}"

    if p.is_active:
        toggle = f"""
      <form method="post" action="/admin/programs/{_escape(p.id)}/deactivate" style="display:inline">
        <button type="submit" class="btn bad">Deactivate</button>
      </form>"""
    else:
        toggle = f"""
      <form method="post" action="/admin/programs/{_escape(p.id)}/activate" style="display:inline">
        <button type="submit" class="btn ok">Activate</button>
      </form>"""

    edit_btn = (
        f'<a class="btn-link" href="/admin/programs/{_escape(p.id)}/edit">Edit</a>'
    )

    tag_pills = _program_tag_pills(p)
    desc = (p.description or "").strip()

    top_badges = (
        f'<div class="card-badges">{_program_status_badge(p)} '
        f'{_source_verified_badge(p.source, bool(p.verified))}</div>'
    )
    top_row = f'<div class="card-top">{tag_pills or "<div></div>"}{top_badges}</div>'

    return f"""
    <article class="card">
      <h3>{_escape(p.title)}</h3>
      {top_row}
      <p class="meta"><span class="label">Category</span> {_escape(p.activity_category or "")}</p>
      <p class="meta"><span class="label">Provider</span> {_escape(p.provider_name or "")}</p>
      <p class="meta"><span class="label">Schedule</span> {schedule_line}</p>
      <p class="meta"><span class="label">Age</span> {_escape(age_line)}</p>
      <p class="meta"><span class="label">Cost</span> {_escape(cost_line)}</p>
      <p class="meta"><span class="label">Where</span> {_escape(location_line)}</p>
      <p class="desc">{_escape(desc)}</p>
      <div class="actions">
        {edit_btn}
        {toggle}
      </div>
    </article>"""


def _programs_tab_shell(inner: str, title: str = "Programs") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Admin — {html.escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #212529;
      line-height: 1.45; padding-bottom: 48px; }}
    header {{ max-width: 720px; margin: 0 auto 16px; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 4px; }}
    h2 {{ font-size: 1.1rem; margin: 0 0 10px; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; }}
    .tabs {{ display: flex; gap: 8px; max-width: 720px; margin: 0 auto 16px; flex-wrap: wrap; }}
    .tabs a {{
      flex: 1; min-width: 140px; text-align: center; padding: 14px 16px; border-radius: 10px;
      text-decoration: none; font-weight: 600; border: 2px solid #dee2e6; color: #495057; background: #f8f9fa;
      min-height: 48px; display: flex; align-items: center; justify-content: center;
    }}
    .tabs a.active {{ border-color: #0d6efd; background: #e7f1ff; color: #0a58ca; }}
    .panel {{ max-width: 720px; margin: 0 auto; }}
    .toolbar {{ max-width: 720px; margin: 0 auto 16px; display: flex; gap: 10px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #e9ecef; border-radius: 12px; padding: 16px; margin-bottom: 14px; background: #fafafa; }}
    .card h3 {{ margin: 0 0 8px; font-size: 1.1rem; }}
    .card-top {{ display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 8px; }}
    .card-badges {{ flex: 0 0 auto; text-align: right; font-size: 0.82rem; display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }}
    .tag-wrap {{ display: flex; flex-wrap: wrap; gap: 8px; flex: 1 1 auto; min-width: 0; }}
    .tag {{ display: inline-flex; align-items: center; padding: 4px 10px; border: 1px solid #dee2e6;
      background: #fff; border-radius: 999px; font-size: 0.85rem; color: #495057; }}
    .pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }}
    .pill-ok {{ background: #d1e7dd; color: #0f5132; }}
    .pill-info {{ background: #cfe2ff; color: #084298; }}
    .pill-warn {{ background: #fff3cd; color: #664d03; }}
    .pill-muted {{ background: #e2e3e5; color: #41464b; }}
    .meta {{ margin: 6px 0; font-size: 0.92rem; color: #495057; word-break: break-word; }}
    .label {{ color: #868e96; font-weight: 600; margin-right: 6px; }}
    .desc {{ white-space: pre-wrap; margin: 10px 0; }}
    .actions {{ margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
    .btn {{ min-height: 48px; min-width: 120px; padding: 12px 18px; font-size: 1rem; font-weight: 600;
      border: none; border-radius: 10px; cursor: pointer; }}
    .btn.ok {{ background: #198754; color: #fff; }}
    .btn.bad {{ background: #dc3545; color: #fff; }}
    .btn-primary {{ background: #0d6efd; color: #fff; text-decoration: none; display: inline-flex;
      align-items: center; justify-content: center; min-height: 48px; min-width: 140px; padding: 12px 18px;
      font-size: 1rem; font-weight: 600; border-radius: 10px; }}
    .btn-link {{ color: #0d6efd; text-decoration: none; font-weight: 600; padding: 12px 18px;
      min-height: 48px; display: inline-flex; align-items: center; border: 1px solid #dee2e6;
      border-radius: 10px; background: #fff; }}
    .btn-link:hover {{ text-decoration: underline; }}
    .empty {{ color: #6c757d; padding: 24px; text-align: center; }}
    a {{ color: #0d6efd; }}
    form.program-form {{ max-width: 720px; margin: 0 auto; }}
    form.program-form label {{ display: block; font-weight: 600; margin: 14px 0 6px; color: #343a40; }}
    form.program-form input[type=text], form.program-form input[type=number],
    form.program-form input[type=email], form.program-form input[type=url],
    form.program-form textarea, form.program-form select {{
      width: 100%; padding: 12px 14px; font-size: 1rem; border: 1px solid #ced4da; border-radius: 10px;
      min-height: 44px; font-family: inherit;
    }}
    form.program-form textarea {{ min-height: 110px; resize: vertical; }}
    form.program-form .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    form.program-form .row > div {{ flex: 1 1 160px; }}
    form.program-form .days {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; }}
    form.program-form .days label {{ display: inline-flex; align-items: center; gap: 6px; margin: 0;
      font-weight: 500; padding: 8px 12px; border: 1px solid #dee2e6; border-radius: 999px;
      background: #f8f9fa; min-height: 40px; }}
    form.program-form .err {{ color: #b02a37; font-weight: 500; margin: 12px 0; }}
    .form-actions {{ margin: 20px 0; display: flex; gap: 10px; flex-wrap: wrap; }}
  </style>
</head>
<body>
  <header>
    <h1>Programs</h1>
    <p class="sub">{html.escape(title)}</p>
  </header>
  <nav class="tabs">
    <a href="/admin?tab=pending">Pending review</a>
    <a href="/admin?tab=live">Live events</a>
    <a class="active" href="/admin?tab=programs">Programs</a>
    <a href="/admin/analytics">Analytics</a>
  </nav>
  <div class="panel">
    {inner}
  </div>
</body>
</html>"""


def _programs_tab_html(programs: list[Program]) -> str:
    toolbar = (
        '<div class="toolbar">'
        '<a class="btn-primary" href="/admin/programs/new">+ Create program</a>'
        "</div>"
    )
    if not programs:
        cards_html = '<p class="empty">No programs yet — create the first one.</p>'
    else:
        cards_html = "\n".join(_program_card_admin_html(p) for p in programs)
    return _programs_tab_shell(toolbar + cards_html, title="All programs")


def _program_form_html(
    *,
    action: str,
    submit_label: str,
    program: Program | None = None,
    error: str | None = None,
    values: dict | None = None,
) -> str:
    v = dict(values or {})
    if program is not None and not values:
        v = {
            "title": program.title or "",
            "description": program.description or "",
            "activity_category": program.activity_category or "",
            "age_min": "" if program.age_min is None else str(program.age_min),
            "age_max": "" if program.age_max is None else str(program.age_max),
            "schedule_days": list(program.schedule_days or []),
            "schedule_start_time": program.schedule_start_time or "",
            "schedule_end_time": program.schedule_end_time or "",
            "location_name": program.location_name or "",
            "location_address": program.location_address or "",
            "cost": program.cost or "",
            "provider_name": program.provider_name or "",
            "contact_phone": program.contact_phone or "",
            "contact_email": program.contact_email or "",
            "contact_url": program.contact_url or "",
            "source": program.source or "admin",
            "is_active": program.is_active,
            "tags": ", ".join(str(t) for t in (program.tags or [])),
        }
    else:
        v.setdefault("title", "")
        v.setdefault("description", "")
        v.setdefault("activity_category", "")
        v.setdefault("age_min", "")
        v.setdefault("age_max", "")
        v.setdefault("schedule_days", [])
        v.setdefault("schedule_start_time", "")
        v.setdefault("schedule_end_time", "")
        v.setdefault("location_name", "")
        v.setdefault("location_address", "")
        v.setdefault("cost", "")
        v.setdefault("provider_name", "")
        v.setdefault("contact_phone", "")
        v.setdefault("contact_email", "")
        v.setdefault("contact_url", "")
        v.setdefault("source", "admin")
        v.setdefault("is_active", True)
        v.setdefault("tags", "")

    def inp(name: str, *, kind: str = "text", placeholder: str = "") -> str:
        return (
            f'<input type="{kind}" id="{name}" name="{name}" '
            f'value="{_escape(str(v.get(name, "")))}" '
            f'placeholder="{_escape(placeholder)}" />'
        )

    selected_days: set[str] = {
        str(d).lower() for d in v.get("schedule_days", []) if isinstance(d, str)
    }
    day_boxes = "".join(
        f'<label><input type="checkbox" name="schedule_days" value="{d}"'
        f'{" checked" if d in selected_days else ""}/> {d.capitalize()}</label>'
        for d in _PROGRAM_DAYS
    )

    source_options = "".join(
        f'<option value="{s}"{" selected" if v.get("source") == s else ""}>{s.capitalize()}</option>'
        for s in _PROGRAM_SOURCES
    )

    is_active_checked = " checked" if v.get("is_active") else ""
    err_html = f'<p class="err">{_escape(error)}</p>' if error else ""

    inner = f"""
    <form class="program-form" method="post" action="{action}">
      {err_html}
      <label for="title">Title</label>
      {inp("title", placeholder="e.g. Junior Golf Lessons")}

      <label for="description">Description</label>
      <textarea id="description" name="description"
        placeholder="What it is, who it's for (at least 20 characters)">{_escape(v.get("description", ""))}</textarea>

      <label for="activity_category">Activity category</label>
      {inp("activity_category", placeholder="golf, swim, dance, ...")}

      <div class="row">
        <div>
          <label for="age_min">Age min</label>
          {inp("age_min", kind="number", placeholder="6")}
        </div>
        <div>
          <label for="age_max">Age max</label>
          {inp("age_max", kind="number", placeholder="12")}
        </div>
      </div>

      <label>Days</label>
      <div class="days">{day_boxes}</div>

      <div class="row">
        <div>
          <label for="schedule_start_time">Start (HH:MM)</label>
          {inp("schedule_start_time", placeholder="09:00")}
        </div>
        <div>
          <label for="schedule_end_time">End (HH:MM)</label>
          {inp("schedule_end_time", placeholder="10:30")}
        </div>
      </div>

      <label for="location_name">Location name</label>
      {inp("location_name", placeholder="Havasu Golf Academy")}

      <label for="location_address">Location address</label>
      {inp("location_address", placeholder="Optional street address")}

      <label for="cost">Cost</label>
      {inp("cost", placeholder="$15/class or Free")}

      <label for="provider_name">Provider name</label>
      {inp("provider_name", placeholder="Organization running it")}

      <div class="row">
        <div>
          <label for="contact_phone">Contact phone</label>
          {inp("contact_phone", placeholder="928-555-0101")}
        </div>
        <div>
          <label for="contact_email">Contact email</label>
          {inp("contact_email", kind="email", placeholder="coach@example.com")}
        </div>
      </div>

      <label for="contact_url">Contact URL</label>
      {inp("contact_url", kind="url", placeholder="https://example.com")}

      <label for="tags">Tags (comma-separated)</label>
      {inp("tags", placeholder="kids, competitive, beginner")}

      <label for="source">Source</label>
      <select id="source" name="source">{source_options}</select>

      <label style="display:flex;align-items:center;gap:10px;margin-top:16px;">
        <input type="checkbox" name="is_active" value="1"{is_active_checked}/>
        Active (shows in search)
      </label>

      <div class="form-actions">
        <button type="submit" class="btn ok">{html.escape(submit_label)}</button>
        <a class="btn-link" href="/admin?tab=programs">Cancel</a>
      </div>
    </form>"""
    return _programs_tab_shell(inner, title=submit_label)


def _parse_program_form(
    *,
    title: str,
    description: str,
    activity_category: str,
    age_min: str | None,
    age_max: str | None,
    schedule_days: list[str],
    schedule_start_time: str,
    schedule_end_time: str,
    location_name: str,
    location_address: str | None,
    cost: str | None,
    provider_name: str,
    contact_phone: str | None,
    contact_email: str | None,
    contact_url: str | None,
    source: str,
    is_active: str | None,
    tags: str | None,
) -> dict:
    def _nonempty(s: str | None) -> str | None:
        if s is None:
            return None
        s = s.strip()
        return s or None

    def _maybe_int(s: str | None) -> int | None:
        if s is None:
            return None
        s = s.strip()
        if not s:
            return None
        return int(s)

    tag_list: list[str] = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    return {
        "title": title,
        "description": description,
        "activity_category": activity_category,
        "age_min": _maybe_int(age_min),
        "age_max": _maybe_int(age_max),
        "schedule_days": list(schedule_days or []),
        "schedule_start_time": schedule_start_time,
        "schedule_end_time": schedule_end_time,
        "location_name": location_name,
        "location_address": _nonempty(location_address),
        "cost": _nonempty(cost),
        "provider_name": provider_name,
        "contact_phone": _nonempty(contact_phone),
        "contact_email": _nonempty(contact_email),
        "contact_url": _nonempty(contact_url),
        "source": source or "admin",
        "is_active": bool(is_active),
        "tags": tag_list,
    }


@router.get("/programs/new", response_class=HTMLResponse, response_model=None)
def admin_program_new(request: Request) -> HTMLResponse | RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    return HTMLResponse(
        _program_form_html(action="/admin/programs", submit_label="Create program")
    )


@router.post("/programs", response_model=None)
def admin_program_create(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    activity_category: str = Form(""),
    age_min: str = Form(""),
    age_max: str = Form(""),
    schedule_days: list[str] = Form(default_factory=list),
    schedule_start_time: str = Form(""),
    schedule_end_time: str = Form(""),
    location_name: str = Form(""),
    location_address: str = Form(""),
    cost: str = Form(""),
    provider_name: str = Form(""),
    contact_phone: str = Form(""),
    contact_email: str = Form(""),
    contact_url: str = Form(""),
    source: str = Form("admin"),
    is_active: str | None = Form(None),
    tags: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse | HTMLResponse:
    redir = _guard(request)
    if redir:
        return redir
    raw = _parse_program_form(
        title=title,
        description=description,
        activity_category=activity_category,
        age_min=age_min,
        age_max=age_max,
        schedule_days=schedule_days,
        schedule_start_time=schedule_start_time,
        schedule_end_time=schedule_end_time,
        location_name=location_name,
        location_address=location_address,
        cost=cost,
        provider_name=provider_name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        contact_url=contact_url,
        source=source,
        is_active=is_active,
        tags=tags,
    )
    try:
        payload = ProgramCreate(**raw)
    except Exception as exc:
        return HTMLResponse(
            _program_form_html(
                action="/admin/programs",
                submit_label="Create program",
                values=raw,
                error=str(exc),
            ),
            status_code=400,
        )
    program = Program(
        title=payload.title,
        description=payload.description,
        activity_category=payload.activity_category,
        age_min=payload.age_min,
        age_max=payload.age_max,
        schedule_days=list(payload.schedule_days),
        schedule_start_time=payload.schedule_start_time,
        schedule_end_time=payload.schedule_end_time,
        location_name=payload.location_name,
        location_address=payload.location_address,
        cost=payload.cost,
        provider_name=payload.provider_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        contact_url=payload.contact_url,
        source=payload.source,
        verified=(payload.source == "admin"),
        is_active=payload.is_active,
        tags=list(payload.tags),
        embedding=None,
    )
    db.add(program)
    db.commit()
    return RedirectResponse(url="/admin?tab=programs", status_code=303)


@router.get("/programs/{program_id}/edit", response_class=HTMLResponse, response_model=None)
def admin_program_edit(
    request: Request, program_id: str, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return HTMLResponse(
        _program_form_html(
            action=f"/admin/programs/{program.id}/update",
            submit_label="Save changes",
            program=program,
        )
    )


@router.post("/programs/{program_id}/update", response_model=None)
def admin_program_update(
    request: Request,
    program_id: str,
    title: str = Form(""),
    description: str = Form(""),
    activity_category: str = Form(""),
    age_min: str = Form(""),
    age_max: str = Form(""),
    schedule_days: list[str] = Form(default_factory=list),
    schedule_start_time: str = Form(""),
    schedule_end_time: str = Form(""),
    location_name: str = Form(""),
    location_address: str = Form(""),
    cost: str = Form(""),
    provider_name: str = Form(""),
    contact_phone: str = Form(""),
    contact_email: str = Form(""),
    contact_url: str = Form(""),
    source: str = Form("admin"),
    is_active: str | None = Form(None),
    tags: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse | HTMLResponse:
    redir = _guard(request)
    if redir:
        return redir
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    raw = _parse_program_form(
        title=title,
        description=description,
        activity_category=activity_category,
        age_min=age_min,
        age_max=age_max,
        schedule_days=schedule_days,
        schedule_start_time=schedule_start_time,
        schedule_end_time=schedule_end_time,
        location_name=location_name,
        location_address=location_address,
        cost=cost,
        provider_name=provider_name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        contact_url=contact_url,
        source=source,
        is_active=is_active,
        tags=tags,
    )
    try:
        payload = ProgramCreate(**raw)
    except Exception as exc:
        return HTMLResponse(
            _program_form_html(
                action=f"/admin/programs/{program.id}/update",
                submit_label="Save changes",
                values=raw,
                error=str(exc),
            ),
            status_code=400,
        )
    program.title = payload.title
    program.description = payload.description
    program.activity_category = payload.activity_category
    program.age_min = payload.age_min
    program.age_max = payload.age_max
    program.schedule_days = list(payload.schedule_days)
    program.schedule_start_time = payload.schedule_start_time
    program.schedule_end_time = payload.schedule_end_time
    program.location_name = payload.location_name
    program.location_address = payload.location_address
    program.cost = payload.cost
    program.provider_name = payload.provider_name
    program.contact_phone = payload.contact_phone
    program.contact_email = payload.contact_email
    program.contact_url = payload.contact_url
    # If admin changed the source to 'admin', auto-verify; if they changed away
    # from admin, only reset verified when it was previously True by auto-verify.
    new_source = payload.source
    if program.source != new_source:
        if new_source == "admin":
            program.verified = True
        elif program.source == "admin" and not program.verified:
            # no change needed
            pass
        elif program.source == "admin":
            # moving away from admin: clear verified so future claim flow can set it
            program.verified = False
    program.source = new_source
    program.is_active = payload.is_active
    program.tags = list(payload.tags)
    db.commit()
    return RedirectResponse(url="/admin?tab=programs", status_code=303)


@router.post("/programs/{program_id}/deactivate", response_model=None)
def admin_program_deactivate(
    request: Request, program_id: str, db: Session = Depends(get_db)
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    program.is_active = False
    db.commit()
    return RedirectResponse(url="/admin?tab=programs", status_code=303)


@router.post("/programs/{program_id}/activate", response_model=None)
def admin_program_activate(
    request: Request, program_id: str, db: Session = Depends(get_db)
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    program.is_active = True
    db.commit()
    return RedirectResponse(url="/admin?tab=programs", status_code=303)
