"""Master spec §5 admin dashboard — at-a-glance ops view."""

from __future__ import annotations

import html
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.admin.nav_html import admin_phase5_nav_html
from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS, SOURCE_KEYS
from app.conditions.staleness import staleness_label
from app.contrib.gas_prices import run_pull
from app.contrib.golakehavasu_pull import run_pull as golake_pull
from app.contrib.river_scene_pull import run_pull as river_scene_pull
from app.core.timezone import now_lake_havasu
from app.db.contribution_store import count_contributions
from app.db.database import get_db
from app.db.models import Event, Provider, QueryLog
from app.monitoring.freshness import evaluate as evaluate_freshness
from app.monitoring.freshness import fmt_age

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


@router.get("/overview", response_class=HTMLResponse)
def admin_v1_overview(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    redir = _guard(request)
    if redir:
        return redir

    now = datetime.now(UTC).replace(tzinfo=None)
    pending = count_contributions(db, status="pending")
    businesses = int(
        db.scalar(
            select(func.count())
            .select_from(Provider)
            .where(Provider.is_active.is_(True), Provider.draft.is_(False))
        )
        or 0
    )
    events = int(
        db.scalar(select(func.count()).select_from(Event).where(Event.status == "live")) or 0
    )
    gas_row = read_source(db, SOURCE_GAS, now=now)
    gas_label, gas_stale = (
        staleness_label(gas_row.fetched_at, now) if gas_row and gas_row.fetched_at else ("—", True)
    )
    week_ago = now - timedelta(days=7)
    queries = list(
        db.scalars(
            select(QueryLog)
            .where(QueryLog.created_at >= week_ago)
            .order_by(desc(QueryLog.created_at))
            .limit(15)
        ).all()
    )
    sources_rows = []
    for key in SOURCE_KEYS:
        row = read_source(db, key, now=now)
        if row is None:
            sources_rows.append((key, "never", "—"))
        else:
            label, _ = staleness_label(row.fetched_at, now)
            sources_rows.append((key, label, row.fetched_at.isoformat() if row.fetched_at else "—"))

    q_rows = (
        "".join(
            f"<tr><td>{_esc(q.normalized_intent)}</td><td>{_esc(q.category)}</td>"
            f"<td>{q.result_count}</td><td>{_esc(q.created_at.isoformat() if q.created_at else '')}</td></tr>"
            for q in queries
        )
        or "<tr><td colspan='4'>No query_log rows yet.</td></tr>"
    )

    src_rows = "".join(
        f"<tr><td><code>{_esc(k)}</code></td><td>{_esc(st)}</td><td>{_esc(at)}</td></tr>"
        for k, st, at in sources_rows
    )

    # P6: unified feed-freshness health — the same grading the staleness cron
    # (scripts/data_freshness_monitor.py) pages on. A STALE/MISSING row here
    # means a scraper silently froze (the P0 date-desync class of bug).
    feed_statuses = evaluate_freshness(db, now=now)
    any_stale = any(not s.ok for s in feed_statuses)
    feed_rows = "".join(
        f"<tr><td>{_esc(s.label)}</td>"
        f"<td>{'OK' if s.ok else _esc(s.status)}</td>"
        f"<td>{_esc(fmt_age(s.age_hours))}</td>"
        f"<td>budget {s.max_age_hours / 24:.0f}d</td></tr>"
        for s in feed_statuses
    )

    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Admin overview — Hava</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; max-width: 960px; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; font-size: 14px; }}
.stat {{ display: inline-block; margin-right: 24px; }}
.stat strong {{ font-size: 28px; display: block; }}
.nav a {{ margin-right: 12px; }}
</style></head><body>
<h1>Ask Hava — v1 dashboard</h1>
{admin_phase5_nav_html()}
<div class="stat"><strong>{pending}</strong> pending contributions</div>
<div class="stat"><strong>{businesses}</strong> businesses</div>
<div class="stat"><strong>{events}</strong> live events</div>
<div class="stat"><strong>{_esc(gas_label)}</strong> gas freshness{" (stale)" if gas_stale else ""}</div>
<p><a href="/admin/contributions">Open approval queue →</a></p>
<form method="post" action="/admin/overview/sync">
  <button type="submit">Run sync now</button> (gas + River Scene + GoLakeHavasu)
</form>
<h2>Recent searches (query_log)</h2>
<table><thead><tr><th>Intent</th><th>Category</th><th>Results</th><th>At</th></tr></thead>
<tbody>{q_rows}</tbody></table>
<h2>Feed freshness (system health){"" if not any_stale else " — ⚠ STALE FEED"}</h2>
<p style="font-size:13px;color:#555">A STALE/MISSING row means a scraper silently stopped landing rows — the P0
date-desync class of bug. The daily <code>data-freshness-check</code> workflow
pages on the same grading.</p>
<table><thead><tr><th>Feed</th><th>Status</th><th>Freshest row</th><th>Budget</th></tr></thead>
<tbody>{feed_rows}</tbody></table>
<h2>Data sources</h2>
<table><thead><tr><th>Source</th><th>Staleness</th><th>Last fetch</th></tr></thead>
<tbody>{src_rows}</tbody></table>
</body></html>"""
    return HTMLResponse(body)


@router.post("/overview/sync")
def admin_overview_sync(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    today = now_lake_havasu().date()
    try:
        run_pull(dry_run=False)
    except Exception:
        # OPS-8 (audit :221): keep best-effort behavior but stop swallowing silently.
        logger.exception("admin overview sync: gas pull failed")
    try:
        river_scene_pull(today, dry_run=False)
    except Exception:
        # OPS-8 (audit :221): keep best-effort behavior but stop swallowing silently.
        logger.exception("admin overview sync: river_scene pull failed")
    try:
        golake_pull(today, dry_run=False)
    except Exception:
        # OPS-8 (audit :221): keep best-effort behavior but stop swallowing silently.
        logger.exception("admin overview sync: golakehavasu pull failed")
    return RedirectResponse(url="/admin/overview?synced=1", status_code=303)
