"""Admin feedback analytics view (Phase 6.2.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.admin.auth import admin_guard as _guard
from app.admin.shell import admin_shell
from app.admin.shell import esc as _esc
from app.admin.shell import fmt_dt as _fmt_dt
from app.db.database import get_db
from app.db.models import ChatLog

_WINDOW_DAYS: dict[str, int | None] = {
    "7d": 7,
    "30d": 30,
    "all": None,
}
_DEFAULT_WINDOW = "7d"

# Page-specific CSS layered over the shared admin_shell base (window picker +
# mono cells).
_FEEDBACK_CSS = """    .window { margin: 8px 0 14px; display: flex; gap: 8px; }
    .wbtn { color: #0d6efd; text-decoration: none; border: 1px solid #dee2e6; border-radius: 999px;
      padding: 4px 10px; font-size: 0.88rem; }
    .wbtn.active { font-weight: 700; text-decoration: underline; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85rem; }"""


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

        positive_cnt = func.sum(case((ChatLog.feedback_signal == "positive", 1), else_=0)).label(
            "positive"
        )
        negative_cnt = func.sum(case((ChatLog.feedback_signal == "negative", 1), else_=0)).label(
            "negative"
        )
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
        return HTMLResponse(admin_shell("Feedback", inner, css=_FEEDBACK_CSS, max_width="980px"))
