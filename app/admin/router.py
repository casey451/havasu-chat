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
from app.db.models import ChatLog, Event
from app.db.seed import run_seed

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
    <a class="{('active' if tab != 'live' else '')}" href="{pending_href}">Pending review</a>
    <a class="{('active' if tab == 'live' else '')}" href="{live_href}">Live events</a>
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
    preview = ""
    if mode == "live":
        preview = (
            f'<a href="/events/{_escape(ev.id)}" target="_blank" rel="noopener">Preview as user</a>'
        )
    badges_cell = f'<div class="card-badges">{badge_html}'
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
    if tab not in ("pending", "live"):
        tab = "pending"

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
