"""Admin feedback analytics view (Phase 6.2.3)."""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.db.database import get_db
from app.db.models import ChatLog

_WINDOW_DAYS: dict[str, int | None] = {
    "7d": 7,
    "30d": 30,
    "all": None,
}
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


def _pct(n: int, d: int) -> str:
    if d <= 0:
        return "—"
    return f"{(100.0 * n / d):.1f}%"


def _snippet(value: str | None, limit: int) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    if len(raw) <= limit:
        return raw
    return raw[:limit].rstrip() + "..."


def _window_links(active: str) -> str:
    parts: list[str] = []
    for key, label in (("7d", "7d"), ("30d", "30d"), ("all", "all")):
        cls = "active" if key == active else ""
        parts.append(f'<a class="wbtn {cls}" href="/admin/feedback?window={key}">{label}</a>')
    return "".join(parts)


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
    .empty {{ color: #6c757d; padding: 12px 0; font-size: 0.92rem; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <div class="wrap">
    <nav class="nav">
      <a href="/admin?tab=queue">Admin home</a>
      <a href="/admin/analytics">Analytics</a>
      <a href="/admin/feedback">Feedback</a>
      <a href="/admin/contributions">Contributions</a>
      <a href="/admin/mentioned-entities">Mentioned entities</a>
      <a href="/admin/categories">Categories</a>
    </nav>
    {inner}
  </div>
</body>
</html>"""


def register_feedback_html_routes(router: APIRouter) -> None:
    @router.get("/feedback", response_class=HTMLResponse, response_model=None)
    def feedback_page(
        request: Request,
        window: str = _DEFAULT_WINDOW,
        db: Session = Depends(get_db),
    ) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir

        win = window if window in _WINDOW_DAYS else _DEFAULT_WINDOW
        days = _WINDOW_DAYS[win]
        cutoff = None
        if days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        positive_cnt = func.sum(case((ChatLog.feedback_signal == "positive", 1), else_=0)).label("positive")
        negative_cnt = func.sum(case((ChatLog.feedback_signal == "negative", 1), else_=0)).label("negative")
        total_cnt = func.count().label("total")
        summary_stmt = (
            select(
                ChatLog.mode,
                ChatLog.sub_intent,
                total_cnt,
                positive_cnt,
                negative_cnt,
            )
            .where(ChatLog.tier_used == "3")
            .group_by(ChatLog.mode, ChatLog.sub_intent)
            .order_by(desc(total_cnt), ChatLog.mode, ChatLog.sub_intent)
        )
        if cutoff is not None:
            summary_stmt = summary_stmt.where(ChatLog.created_at >= cutoff)
        summary_rows = db.execute(summary_stmt).all()

        neg_stmt = (
            select(
                ChatLog.id,
                ChatLog.created_at,
                ChatLog.mode,
                ChatLog.sub_intent,
                ChatLog.normalized_query,
                ChatLog.message,
            )
            .where(ChatLog.tier_used == "3", ChatLog.feedback_signal == "negative")
            .order_by(desc(ChatLog.created_at))
            .limit(25)
        )
        neg_rows = db.execute(neg_stmt).all()

        if not summary_rows:
            summary_html = '<p class="empty">No Tier 3 responses in this window.</p>'
        else:
            body = ""
            for mode, sub, total, pos, neg in summary_rows:
                total_i = int(total or 0)
                pos_i = int(pos or 0)
                neg_i = int(neg or 0)
                rated = pos_i + neg_i
                body += (
                    "<tr>"
                    f"<td>{_esc(mode or '(null)')}</td>"
                    f"<td>{_esc(sub or '(null)')}</td>"
                    f"<td>{total_i}</td>"
                    f"<td>{pos_i}</td>"
                    f"<td>{neg_i}</td>"
                    f"<td>{_pct(rated, total_i)}</td>"
                    f"<td>{_pct(pos_i, rated)}</td>"
                    "</tr>"
                )
            summary_html = (
                "<table><thead><tr>"
                "<th>Mode</th><th>Sub-intent</th><th>Total Tier 3</th><th>Positive</th><th>Negative</th>"
                "<th>Feedback rate</th><th>Positive rate</th>"
                f"</tr></thead><tbody>{body}</tbody></table>"
            )

        if not neg_rows:
            negatives_html = (
                "<table><thead><tr><th>Created</th><th>Mode / sub-intent</th><th>Query</th>"
                "<th>Response</th><th>chat_log_id</th></tr></thead>"
                '<tbody><tr><td colspan="5">No negative feedback yet.</td></tr></tbody></table>'
            )
        else:
            nbody = ""
            for log_id, created_at, mode, sub, normalized_query, message in neg_rows:
                query_source = normalized_query or message
                nbody += (
                    "<tr>"
                    f"<td>{_esc(_fmt_dt(created_at))}</td>"
                    f"<td>{_esc(mode or '(null)')} / {_esc(sub or '(null)')}</td>"
                    f"<td>{_esc(_snippet(query_source, 80))}</td>"
                    f"<td>{_esc(_snippet(message, 160))}</td>"
                    f'<td class="mono">{_esc(str(log_id))}</td>'
                    "</tr>"
                )
            negatives_html = (
                "<table><thead><tr><th>Created</th><th>Mode / sub-intent</th><th>Query</th>"
                "<th>Response</th><th>chat_log_id</th></tr></thead>"
                f"<tbody>{nbody}</tbody></table>"
            )

        inner = f"""<h1>Feedback analytics</h1>
<p class="sub">Tier 3 feedback summary by mode/sub-intent plus most recent negatives.</p>
<div class="window">{_window_links(win)}</div>

<h2>Summary (Tier 3 only)</h2>
{summary_html}

<h2>Recent negatives (latest 25)</h2>
{negatives_html}
"""
        return HTMLResponse(_nav_shell("Feedback", inner))
