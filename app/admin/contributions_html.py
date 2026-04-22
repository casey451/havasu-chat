"""HTML admin UI for contribution review (Phase 5.3). Inline HTML matches ``app.admin.router`` style."""

from __future__ import annotations

import html
from datetime import date, datetime, time
from typing import Any, get_args
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.admin.nav_html import admin_phase5_nav_html
from app.contrib.approval_service import (
    approve_contribution_as_event,
    approve_contribution_as_program,
    approve_contribution_as_provider,
    parse_comma_tags,
    parse_schedule_days_field,
)
from app.db.contribution_store import count_contributions, get_contribution, list_contributions, update_contribution_status
from app.db.database import get_db
from app.db.models import Contribution, Event, Program, Provider
from app.schemas.contribution import (
    EventApprovalFields,
    ProgramApprovalFields,
    ProviderApprovalFields,
    RejectionReason,
)

_VALID_LIST_STATUSES = frozenset({"pending", "approved", "rejected", "needs_info", "all"})


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _fmt_compact_ts(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    h24 = dt.hour
    h12 = h24 % 12 or 12
    ampm = "am" if h24 < 12 else "pm"
    mon = dt.strftime("%b")
    return f"{mon} {dt.day}, {h12}:{dt.minute:02d}{ampm}"


def _ip_display(h: str | None) -> str:
    if not h:
        return "—"
    if len(h) <= 8:
        return _esc(h)
    return f"{_esc(h[:8])}… ({len(h)} chars)"


def _places_dict(c: Contribution) -> dict[str, Any]:
    g = c.google_enriched_data
    return g if isinstance(g, dict) else {}


def _places_status(c: Contribution) -> str:
    ged = _places_dict(c)
    if not ged:
        return "N/A"
    st = ged.get("lookup_status")
    if isinstance(st, str) and st:
        return st
    if "error" in ged or ged.get("status") == "error":
        return "error"
    return "N/A"


def _url_fetch_display(c: Contribution) -> str:
    s = (c.url_fetch_status or "").strip()
    return s if s else ("N/A" if not c.submission_url else "—")


def _format_opening_hours(blob: Any) -> str:
    """Human-readable hours from Places ``regular_opening_hours`` JSON."""
    if not isinstance(blob, dict):
        return ""
    wd = blob.get("weekdayDescriptions")
    if isinstance(wd, list) and wd:
        lines: list[str] = []
        for line in wd:
            if isinstance(line, str) and line.strip():
                lines.append(line.strip())
        return "\n".join(lines)
    periods = blob.get("periods")
    if not isinstance(periods, list) or not periods:
        return ""

    day_names = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")

    def fmt_point(pt: Any) -> str | None:
        if not isinstance(pt, dict):
            return None
        h = int(pt.get("hour", 0))
        m = int(pt.get("minute", 0))
        h12 = h % 12 or 12
        ampm = "AM" if h < 12 else "PM"
        return f"{h12}:{m:02d} {ampm}"

    by_day: dict[int, list[str]] = {i: [] for i in range(7)}
    for per in periods:
        if not isinstance(per, dict):
            continue
        o = per.get("open")
        cl = per.get("close")
        if not isinstance(o, dict):
            continue
        day = int(o.get("day", 0)) % 7
        o_s = fmt_point(o)
        c_s = fmt_point(cl) if isinstance(cl, dict) else None
        if o_s and c_s:
            by_day[day].append(f"{o_s} – {c_s}")
        elif o_s:
            by_day[day].append(f"{o_s} – ?")
    lines_out: list[str] = []
    for i in range(7):
        label = day_names[i]
        slots = by_day.get(i) or []
        if slots:
            lines_out.append(f"{label}: " + "; ".join(slots))
        else:
            lines_out.append(f"{label}: —")
    return "\n".join(lines_out)


def _distinct_provider_categories(db: Session) -> list[str]:
    rows = db.execute(select(Provider.category).distinct().order_by(Provider.category)).scalars().all()
    return [str(r) for r in rows if r]


def _distinct_program_activity_categories(db: Session) -> list[str]:
    rows = db.execute(select(Program.activity_category).distinct().order_by(Program.activity_category)).scalars().all()
    return [str(r) for r in rows if r]


def _merged_category_suggestions(db: Session) -> list[str]:
    s = set(_distinct_provider_categories(db)) | set(_distinct_program_activity_categories(db))
    return sorted(s)


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
    .wrap {{ max-width: 920px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
    h2 {{ font-size: 1.05rem; margin: 22px 0 10px; color: #343a40; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; margin-bottom: 14px; }}
    .nav {{ margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .nav a {{ color: #0d6efd; font-weight: 600; text-decoration: none; }}
    .nav a:hover {{ text-decoration: underline; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-bottom: 12px; }}
    th, td {{ border: 1px solid #dee2e6; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f8f9fa; font-weight: 600; }}
    tbody tr:nth-child(even) {{ background: #fcfcfc; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
    .pill-pending {{ background: #fff3cd; color: #664d03; }}
    .pill-approved {{ background: #d1e7dd; color: #0f5132; }}
    .pill-rejected {{ background: #f8d7da; color: #842029; }}
    .pill-needs {{ background: #cff4fc; color: #055160; }}
    .pill-provider {{ background: #e7f1ff; color: #084298; }}
    .pill-program {{ background: #ede7f6; color: #4a148c; }}
    .pill-event {{ background: #e8f5e9; color: #1b5e20; }}
    .pill-tip {{ background: #fce4ec; color: #880e4f; }}
    .flash {{ padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 0.92rem; }}
    .flash-ok {{ background: #d1e7dd; color: #0f5132; }}
    .flash-err {{ background: #f8d7da; color: #842029; }}
    .section {{ border: 1px solid #e9ecef; border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; background: #fafafa; }}
    .kv {{ margin: 6px 0; font-size: 0.92rem; }}
    .kv .k {{ color: #868e96; font-weight: 600; margin-right: 6px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .btn {{ display: inline-block; padding: 10px 16px; border-radius: 8px; font-weight: 600; text-decoration: none;
      border: none; cursor: pointer; font-size: 0.95rem; }}
    .btn-primary {{ background: #198754; color: #fff; }}
    .btn-secondary {{ background: #6c757d; color: #fff; }}
    .btn-danger {{ background: #dc3545; color: #fff; }}
    .btn-info {{ background: #0dcaf0; color: #212529; }}
    .btn-muted {{ background: #e9ecef; color: #6c757d; cursor: not-allowed; }}
    label {{ display: block; font-weight: 600; font-size: 0.88rem; margin: 10px 0 4px; }}
    input[type=text], input[type=url], input[type=date], input[type=time], select, textarea {{
      width: 100%; max-width: 100%; padding: 8px 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 0.95rem; }}
    textarea {{ min-height: 90px; }}
    .empty {{ color: #6c757d; padding: 20px; text-align: center; }}
    .err {{ color: #842029; font-size: 0.88rem; margin-top: 4px; }}
    .pagination {{ margin-top: 12px; font-size: 0.9rem; }}
    pre.hours {{ white-space: pre-wrap; font-family: inherit; font-size: 0.88rem; margin: 0; }}
  </style>
</head>
<body>
  <div class="wrap">
{admin_phase5_nav_html()}
    {inner}
  </div>
</body>
</html>"""


def _status_pill(status: str) -> str:
    cls = {
        "pending": "pill-pending",
        "approved": "pill-approved",
        "rejected": "pill-rejected",
        "needs_info": "pill-needs",
    }.get(status, "pill-pending")
    return f'<span class="pill {cls}">{_esc(status)}</span>'


def _entity_pill(et: str) -> str:
    cls = {
        "provider": "pill-provider",
        "program": "pill-program",
        "event": "pill-event",
        "tip": "pill-tip",
    }.get(et, "pill-tip")
    return f'<span class="pill {cls}">{_esc(et)}</span>'


def register_contribution_html_routes(router: APIRouter) -> None:
    """Attach contribution review routes to the existing ``/admin`` router."""

    @router.get("/contributions", response_class=HTMLResponse, response_model=None)
    def contributions_list(
        request: Request,
        db: Session = Depends(get_db),
        status: str = Query("pending"),
        entity_type: str | None = Query(None),
        source: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        flash: str | None = None,
        flash_kind: str | None = Query(None, alias="kind"),
    ) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        st_key = status if status in _VALID_LIST_STATUSES else "pending"
        filter_status: str | None = None if st_key == "all" else st_key
        et = (entity_type or "").strip() or None
        src = (source or "").strip() or None
        rows = list_contributions(db, status=filter_status, entity_type=et, source=src, limit=limit, offset=offset)
        total = count_contributions(db, status=filter_status, entity_type=et, source=src)
        flash_html = ""
        if flash:
            fk = "flash-ok" if (flash_kind or "ok") == "ok" else "flash-err"
            flash_html = f'<div class="flash {fk}">{_esc(flash)}</div>'
        if total == 0:
            if count_contributions(db, status=None, entity_type=None, source=None) == 0:
                empty_msg = "No contributions yet. Check back after submissions arrive."
            else:
                empty_msg = "No contributions match these filters. Try widening the filter or clearing them."
            table_body = f'<p class="empty">{empty_msg}</p>'
        else:
            trs: list[str] = []
            for r in rows:
                link = f'<a href="/admin/contributions/{r.id}">{_esc(r.submission_name)}</a>'
                trs.append(
                    "<tr>"
                    f"<td>{_esc(_fmt_compact_ts(r.submitted_at))}</td>"
                    f"<td>{_entity_pill(r.entity_type)}</td>"
                    f"<td>{link}</td>"
                    f"<td>{_status_pill(r.status)}</td>"
                    f"<td>{_esc(r.source)}</td>"
                    f"<td>{_esc(_url_fetch_display(r))}</td>"
                    f"<td>{_esc(_places_status(r))}</td>"
                    "</tr>"
                )
            table_body = (
                "<table><thead><tr>"
                "<th>Submitted</th><th>Type</th><th>Name</th><th>Status</th>"
                "<th>Source</th><th>URL fetch</th><th>Places</th>"
                "</tr></thead><tbody>"
                + "".join(trs)
                + "</tbody></table>"
            )
        q_base: dict[str, str] = {}
        if st_key != "pending":
            q_base["status"] = st_key
        if et:
            q_base["entity_type"] = et
        if src:
            q_base["source"] = src
        filter_form = f"""
<form method="get" class="section" style="background:#fff">
  <label>Status</label>
  <select name="status">
    <option value="pending" {"selected" if st_key=="pending" else ""}>pending</option>
    <option value="approved" {"selected" if st_key=="approved" else ""}>approved</option>
    <option value="rejected" {"selected" if st_key=="rejected" else ""}>rejected</option>
    <option value="needs_info" {"selected" if st_key=="needs_info" else ""}>needs_info</option>
    <option value="all" {"selected" if st_key=="all" else ""}>all</option>
  </select>
  <label>Entity type</label>
  <select name="entity_type">
    <option value="">any</option>
    <option value="provider" {"selected" if et=="provider" else ""}>provider</option>
    <option value="program" {"selected" if et=="program" else ""}>program</option>
    <option value="event" {"selected" if et=="event" else ""}>event</option>
    <option value="tip" {"selected" if et=="tip" else ""}>tip</option>
  </select>
  <label>Source</label>
  <select name="source">
    <option value="">any</option>
    <option value="user_submission" {"selected" if src=="user_submission" else ""}>user_submission</option>
    <option value="llm_inferred" {"selected" if src=="llm_inferred" else ""}>llm_inferred</option>
    <option value="operator_backfill" {"selected" if src=="operator_backfill" else ""}>operator_backfill</option>
  </select>
  <label>Limit</label>
  <input type="text" name="limit" value="{limit}" inputmode="numeric" pattern="[0-9]+" />
  <div style="margin-top:12px">
    <button type="submit" class="btn btn-secondary">Apply filters</button>
  </div>
</form>"""
        pages = ""
        if total > limit:
            prev_off = max(0, offset - limit)
            next_off = offset + limit if offset + limit < total else offset
            q_prev = {**q_base, "limit": str(limit), "offset": str(prev_off)}
            q_next = {**q_base, "limit": str(limit), "offset": str(next_off)}
            prev_link = f'<a href="/admin/contributions?{urlencode(q_prev)}">Previous</a>' if offset > 0 else "Previous"
            next_link = (
                f'<a href="/admin/contributions?{urlencode(q_next)}">Next</a>' if offset + limit < total else "Next"
            )
            pages = f'<p class="pagination">{prev_link} · showing {offset + 1}–{min(offset + limit, total)} of {total} · {next_link}</p>'
        inner = f"""{flash_html}
<h1>Contributions</h1>
<p class="sub">Review community submissions. JSON API: <code>/admin/api/contributions</code>.</p>
{filter_form}
{table_body}
{pages}"""
        return HTMLResponse(_nav_shell("Contributions", inner))

    @router.get("/contributions/{contribution_id}", response_class=HTMLResponse, response_model=None)
    def contribution_detail(request: Request, contribution_id: int, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        c = get_contribution(db, contribution_id)
        if c is None:
            raise HTTPException(status_code=404, detail="Not found")
        ged = _places_dict(c)
        enrich_bits: list[str] = []
        if c.submission_url or c.url_fetch_status or c.url_title:
            enrich_bits.append(
                f'<div class="kv"><span class="k">URL fetch</span> {_esc(c.url_fetch_status or "—")}</div>'
            )
            if c.url_title:
                enrich_bits.append(f'<div class="kv"><span class="k">URL title</span> {_esc(c.url_title)}</div>')
            if c.url_description:
                enrich_bits.append(
                    f'<div class="kv"><span class="k">URL description</span> {_esc(c.url_description[:500])}</div>'
                )
            if c.url_fetched_at:
                enrich_bits.append(f'<div class="kv"><span class="k">Fetched at</span> {_esc(str(c.url_fetched_at))}</div>')
        if ged:
            enrich_bits.append(f'<div class="kv"><span class="k">Places status</span> {_esc(_places_status(c))}</div>')
            if ged.get("place_id"):
                enrich_bits.append(f'<div class="kv"><span class="k">place_id</span> {_esc(str(ged.get("place_id")))}</div>')
            if ged.get("display_name"):
                enrich_bits.append(f'<div class="kv"><span class="k">display_name</span> {_esc(str(ged.get("display_name")))}</div>')
            if ged.get("formatted_address"):
                enrich_bits.append(
                    f'<div class="kv"><span class="k">formatted_address</span> {_esc(str(ged.get("formatted_address")))}</div>'
                )
            if ged.get("phone"):
                enrich_bits.append(f'<div class="kv"><span class="k">phone</span> {_esc(str(ged.get("phone")))}</div>')
            if ged.get("website_uri"):
                enrich_bits.append(f'<div class="kv"><span class="k">website</span> {_esc(str(ged.get("website_uri")))}</div>')
            if ged.get("business_status"):
                enrich_bits.append(
                    f'<div class="kv"><span class="k">business_status</span> {_esc(str(ged.get("business_status")))}</div>'
                )
            if ged.get("types"):
                enrich_bits.append(f'<div class="kv"><span class="k">types</span> {_esc(str(ged.get("types")))}</div>')
            roh = ged.get("regular_opening_hours")
            hrs = _format_opening_hours(roh)
            if hrs:
                enrich_bits.append(f'<div class="kv"><span class="k">Hours</span><pre class="hours">{_esc(hrs)}</pre></div>')
            if ged.get("error"):
                enrich_bits.append(f'<div class="kv"><span class="k">Places error</span> {_esc(str(ged.get("error")))}</div>')
        enrich_section = ""
        if enrich_bits:
            enrich_section = f'<div class="section"><h2>Enrichment</h2>{"".join(enrich_bits)}</div>'
        sub_url = c.submission_url or ""
        url_line = (
            f'<a href="{_esc(sub_url)}" target="_blank" rel="noopener noreferrer">{_esc(sub_url)}</a>'
            if sub_url
            else "—"
        )
        llm_line = _esc(c.llm_source_chat_log_id or "—")
        if c.llm_source_chat_log_id:
            llm_line = _esc(c.llm_source_chat_log_id)
        sub = f"""<div class="section"><h2>Submission</h2>
<div class="kv"><span class="k">Submitter email</span> {_esc(c.submitter_email or "—")}</div>
<div class="kv"><span class="k">IP hash</span> {_ip_display(c.submitter_ip_hash)}</div>
<div class="kv"><span class="k">Entity type</span> {_entity_pill(c.entity_type)}</div>
<div class="kv"><span class="k">Name</span> {_esc(c.submission_name)}</div>
<div class="kv"><span class="k">URL</span> {url_line}</div>
<div class="kv"><span class="k">Category hint</span> {_esc(c.submission_category_hint or "—")}</div>
<div class="kv"><span class="k">Notes</span> {_esc(c.submission_notes or "—")}</div>
<div class="kv"><span class="k">Event date</span> {_esc(str(c.event_date) if c.event_date else "—")}</div>
<div class="kv"><span class="k">Event times</span> {_esc(str(c.event_time_start or "—"))} – {_esc(str(c.event_time_end or "—"))}</div>
<div class="kv"><span class="k">Source</span> {_esc(c.source)} · unverified={c.unverified}</div>
<div class="kv"><span class="k">llm_source_chat_log_id</span> {llm_line}</div>
<div class="kv"><span class="k">Submitted at</span> {_esc(str(c.submitted_at))}</div>
</div>"""
        actions = ""
        if c.status == "pending":
            if c.entity_type == "tip":
                approve_btn = (
                    '<button type="button" class="btn btn-muted" disabled>Tip approval not yet supported — '
                    "use Needs Info to flag for later processing</button>"
                )
            else:
                approve_btn = (
                    f'<a class="btn btn-primary" href="/admin/contributions/{c.id}/approve">Approve</a>'
                )
            actions = f"""<div class="section"><h2>Actions</h2>
<div class="actions">
  {approve_btn}
  <a class="btn btn-danger" href="/admin/contributions/{c.id}/reject">Reject</a>
  <a class="btn btn-info" href="/admin/contributions/{c.id}/needs-info">Needs info</a>
</div>
<p style="margin-top:14px;font-size:0.88rem">
  <form method="post" action="/admin/api/contributions/{c.id}/enrich" style="display:inline">
    <button type="submit" class="btn btn-secondary" style="font-size:0.85rem">Re-run enrichment</button>
  </form>
</p>
</div>"""
        else:
            actions = f"""<div class="section"><h2>Review state</h2>
<div class="kv"><span class="k">Status</span> {_status_pill(c.status)}</div>
<div class="kv"><span class="k">Reviewed at</span> {_esc(str(c.reviewed_at or "—"))}</div>
<div class="kv"><span class="k">Rejection reason</span> {_esc(c.rejection_reason or "—")}</div>
<div class="kv"><span class="k">Review notes</span> {_esc(c.review_notes or "—")}</div>
<div class="kv"><span class="k">Created IDs</span> provider={_esc(c.created_provider_id or "—")} · program={_esc(c.created_program_id or "—")} · event={_esc(c.created_event_id or "—")}</div>
</div>"""
        inner = f"""<h1>Contribution #{c.id}</h1>
<p class="sub"><a href="/admin/contributions">← Back to list</a></p>
{sub}
{enrich_section}
{actions}"""
        return HTMLResponse(_nav_shell(f"Contribution {c.id}", inner))

    def _datalist_categories(db: Session, list_id: str) -> str:
        opts = "".join(f'<option value="{_esc(v)}"/>' for v in _merged_category_suggestions(db))
        return f'<datalist id="{_esc(list_id)}">{opts}</datalist>'

    @router.get("/contributions/{contribution_id}/approve", response_class=HTMLResponse, response_model=None)
    def approve_get(request: Request, contribution_id: int, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        c = get_contribution(db, contribution_id)
        if c is None:
            raise HTTPException(status_code=404, detail="Not found")
        if c.status != "pending":
            return HTMLResponse(
                _nav_shell(
                    "Cannot approve",
                    f'<p class="sub">Contribution is not pending (status={_esc(c.status)}).</p><p><a href="/admin/contributions/{c.id}">Back</a></p>',
                ),
                status_code=400,
            )
        if c.entity_type == "tip":
            return HTMLResponse(
                _nav_shell(
                    "Tip approval",
                    "<p><strong>Tip approval is not supported in Phase 5.3.</strong> Use Needs Info to flag this tip for later processing.</p>"
                    f'<p><a href="/admin/contributions/{c.id}">Back to detail</a></p>',
                ),
                status_code=400,
            )
        ged = _places_dict(c)
        dl = _datalist_categories(db, "catlist")
        err_html = ""
        inner_body = ""
        if c.entity_type == "provider":
            name = (c.submission_name or "").strip() or str(ged.get("display_name") or "")
            addr = str(ged.get("formatted_address") or "").strip()
            phone = str(ged.get("phone") or "").strip()
            website = (c.submission_url or "").strip() or str(ged.get("website_uri") or "").strip()
            desc_parts = [x for x in (c.submission_notes, c.url_description) if x]
            description = "\n\n".join(str(p) for p in desc_parts if p)
            roh = ged.get("regular_opening_hours")
            hours = _format_opening_hours(roh)
            inner_body = f"""
{dl}
<form method="post" action="/admin/contributions/{c.id}/approve">
  <label>Name</label><input type="text" name="name" value="{_esc(name)}" required />
  <label>Address</label><input type="text" name="address" value="{_esc(addr)}" />
  <label>Phone</label><input type="text" name="phone" value="{_esc(phone)}" />
  <label>Hours</label><textarea name="hours">{_esc(hours)}</textarea>
  <label>Description</label><textarea name="description" required minlength="1">{_esc(description)}</textarea>
  <label>Website</label><input type="text" name="website" value="{_esc(website)}" />
  <label>Category</label><input type="text" name="category" value="{_esc(c.submission_category_hint or "")}" list="catlist" autocomplete="off" required />
  <div style="margin-top:14px"><button type="submit" class="btn btn-primary">Approve</button>
  <a href="/admin/contributions/{c.id}" style="margin-left:10px">Cancel</a></div>
</form>"""
        elif c.entity_type == "program":
            inner_body = f"""
{dl}
<form method="post" action="/admin/contributions/{c.id}/approve">
  <label>Title</label><input type="text" name="title" value="{_esc(c.submission_name)}" required />
  <label>Description</label><textarea name="description" required minlength="20">{_esc(c.submission_notes or "")}</textarea>
  <label>Age min</label><input type="text" name="age_min" value="" placeholder="optional" />
  <label>Age max</label><input type="text" name="age_max" value="" placeholder="optional" />
  <label>Schedule days (comma-separated, e.g. monday,wednesday)</label>
  <input type="text" name="schedule_days" value="monday" required />
  <label>Start time (HH:MM)</label><input type="text" name="schedule_start_time" value="09:00" required pattern="^([01]\\d|2[0-3]):[0-5]\\d$" />
  <label>End time (HH:MM)</label><input type="text" name="schedule_end_time" value="17:00" required pattern="^([01]\\d|2[0-3]):[0-5]\\d$" />
  <label>Location name</label><input type="text" name="location_name" value="{_esc(str(ged.get("display_name") or ""))}" required />
  <label>Location address</label><input type="text" name="location_address" value="{_esc(str(ged.get("formatted_address") or ""))}" />
  <label>Cost</label><input type="text" name="cost" value="" />
  <label>Provider name</label><input type="text" name="provider_name" value="{_esc(c.submission_name)}" required />
  <label>Contact phone</label><input type="text" name="contact_phone" value="" />
  <label>Contact email</label><input type="text" name="contact_email" value="" />
  <label>Contact URL</label><input type="text" name="contact_url" value="{_esc((c.submission_url or "").strip())}" />
  <label>Tags (comma-separated)</label><input type="text" name="tags" value="" />
  <label>Activity category</label><input type="text" name="category" value="{_esc(c.submission_category_hint or "")}" list="catlist" required />
  <div style="margin-top:14px"><button type="submit" class="btn btn-primary">Approve</button>
  <a href="/admin/contributions/{c.id}" style="margin-left:10px">Cancel</a></div>
</form>"""
        elif c.entity_type == "event":
            ev_date = c.event_date.isoformat() if c.event_date else date.today().isoformat()
            st = c.event_time_start.strftime("%H:%M") if c.event_time_start else "10:00"
            etv = c.event_time_end.strftime("%H:%M") if c.event_time_end else ""
            loc_name = str(ged.get("display_name") or c.submission_name or "").strip()
            loc_addr = str(ged.get("formatted_address") or "").strip()
            if len(loc_name) >= 3:
                loc_combined = loc_name
            elif len(loc_addr) >= 3:
                loc_combined = loc_addr
            else:
                loc_combined = "Location TBD"
            event_url = (c.submission_url or str(ged.get("website_uri") or "")).strip()
            inner_body = f"""
<form method="post" action="/admin/contributions/{c.id}/approve">
  <label>Title</label><input type="text" name="title" value="{_esc(c.submission_name)}" required />
  <label>Description</label><textarea name="description" required minlength="20">{_esc(c.submission_notes or "Community-submitted event. ")}</textarea>
  <label>Date</label><input type="date" name="event_date" value="{_esc(ev_date)}" required />
  <label>Start time</label><input type="time" name="start_time" value="{_esc(st)}" required />
  <label>End time</label><input type="time" name="end_time" value="{_esc(etv)}" />
  <label>Location name</label><input type="text" name="location_name" value="{_esc(loc_combined)}" required />
  <label>Event URL</label><input type="text" name="event_url" value="{_esc(event_url)}" required />
  <label>Tags (comma-separated)</label><input type="text" name="tags" value="" />
  <div style="margin-top:14px"><button type="submit" class="btn btn-primary">Approve</button>
  <a href="/admin/contributions/{c.id}" style="margin-left:10px">Cancel</a></div>
</form>"""
        else:
            inner_body = "<p>Unsupported entity type.</p>"
        inner = f"""<h1>Approve contribution #{c.id}</h1>
<p class="sub"><a href="/admin/contributions/{c.id}">← Detail</a></p>
{err_html}{inner_body}"""
        return HTMLResponse(_nav_shell("Approve", inner))

    @router.post("/contributions/{contribution_id}/approve", response_class=HTMLResponse, response_model=None)
    def approve_post(
        request: Request,
        contribution_id: int,
        db: Session = Depends(get_db),
        name: str | None = Form(None),
        address: str | None = Form(None),
        phone: str | None = Form(None),
        hours: str | None = Form(None),
        description: str | None = Form(None),
        website: str | None = Form(None),
        category: str | None = Form(None),
        title: str | None = Form(None),
        age_min: str | None = Form(None),
        age_max: str | None = Form(None),
        schedule_days: str | None = Form(None),
        schedule_start_time: str | None = Form(None),
        schedule_end_time: str | None = Form(None),
        location_name: str | None = Form(None),
        location_address: str | None = Form(None),
        cost: str | None = Form(None),
        provider_name: str | None = Form(None),
        contact_phone: str | None = Form(None),
        contact_email: str | None = Form(None),
        contact_url: str | None = Form(None),
        tags: str | None = Form(None),
        event_date: str | None = Form(None),
        start_time: str | None = Form(None),
        end_time: str | None = Form(None),
        event_url: str | None = Form(None),
    ) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        c = get_contribution(db, contribution_id)
        if c is None:
            raise HTTPException(status_code=404, detail="Not found")
        if c.entity_type == "tip":
            return HTMLResponse(
                _nav_shell(
                    "Tip approval",
                    "<p><strong>Tip approval is not supported in Phase 5.3.</strong> Use Needs Info to flag this tip for later processing.</p>"
                    f'<p><a href="/admin/contributions/{c.id}">Back</a></p>',
                ),
                status_code=400,
            )
        if c.status != "pending":
            return HTMLResponse(
                _nav_shell(
                    "Cannot approve",
                    f'<p>Contribution is not pending.</p><p><a href="/admin/contributions/{c.id}">Back</a></p>',
                ),
                status_code=400,
            )
        try:
            if c.entity_type == "provider":
                pf = ProviderApprovalFields(
                    name=name or "",
                    address=address,
                    phone=phone,
                    hours=hours,
                    description=description,
                    website=website,
                )
                p = approve_contribution_as_provider(db, contribution_id, pf, category or "")
                msg = f"Approved: {p.provider_name} is now in the catalog."
            elif c.entity_type == "program":
                def _opt_int(x: str | None) -> int | None:
                    if x is None or not str(x).strip():
                        return None
                    return int(str(x).strip())

                days = parse_schedule_days_field(schedule_days)
                pr = ProgramApprovalFields(
                    title=title or "",
                    description=description or "",
                    age_min=_opt_int(age_min),
                    age_max=_opt_int(age_max),
                    schedule_days=days,
                    schedule_start_time=schedule_start_time or "09:00",
                    schedule_end_time=schedule_end_time or "17:00",
                    location_name=location_name or "",
                    location_address=location_address,
                    cost=cost,
                    provider_name=provider_name or "",
                    contact_phone=contact_phone,
                    contact_email=contact_email,
                    contact_url=contact_url,
                    tags=parse_comma_tags(tags),
                )
                prog = approve_contribution_as_program(db, contribution_id, pr, category or "")
                msg = f"Approved: {prog.title} is now in the catalog."
            elif c.entity_type == "event":
                if not event_date:
                    raise ValueError("event_date required")
                d = date.fromisoformat(event_date)
                st_t = time.fromisoformat(start_time or "10:00")
                en_t = time.fromisoformat(end_time) if end_time and str(end_time).strip() else None
                evf = EventApprovalFields(
                    title=title or "",
                    description=description or "",
                    date=d,
                    start_time=st_t,
                    end_time=en_t,
                    location_name=location_name or "",
                    event_url=event_url or "",
                )
                tag_list = parse_comma_tags(tags)
                ev = approve_contribution_as_event(db, contribution_id, evf, tag_list)
                msg = f"Approved: {ev.title} is now in the catalog."
            else:
                raise ValueError("unsupported entity type")
        except (ValueError, ValidationError) as e:
            err = str(e)
            return HTMLResponse(
                _nav_shell(
                    "Approve — validation error",
                    f'<p class="flash flash-err">{_esc(err)}</p><p><a href="/admin/contributions/{contribution_id}/approve">Try again</a></p>',
                ),
                status_code=400,
            )
        q = urlencode({"flash": msg, "kind": "ok"})
        return RedirectResponse(url=f"/admin/contributions?{q}", status_code=303)

    @router.get("/contributions/{contribution_id}/reject", response_class=HTMLResponse, response_model=None)
    def reject_get(request: Request, contribution_id: int, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        c = get_contribution(db, contribution_id)
        if c is None:
            raise HTTPException(status_code=404, detail="Not found")
        if c.status != "pending":
            return HTMLResponse(
                _nav_shell("Reject", f'<p>Not pending.</p><p><a href="/admin/contributions/{c.id}">Back</a></p>'),
                status_code=400,
            )
        opts = "".join(
            f'<option value="{_esc(x)}">{_esc(x)}</option>'
            for x in ("duplicate", "out_of_area", "spam", "incomplete", "unverifiable", "other")
        )
        inner = f"""<h1>Reject contribution #{c.id}</h1>
<form method="post" action="/admin/contributions/{c.id}/reject">
  <label>Reason (required)</label>
  <select name="rejection_reason" required>{opts}</select>
  <label>Review notes (optional)</label>
  <textarea name="review_notes"></textarea>
  <div style="margin-top:14px">
    <button type="submit" class="btn btn-danger">Reject</button>
    <a href="/admin/contributions/{c.id}" style="margin-left:10px">Cancel</a>
  </div>
</form>"""
        return HTMLResponse(_nav_shell("Reject", inner))

    @router.post("/contributions/{contribution_id}/reject", response_class=HTMLResponse, response_model=None)
    def reject_post(
        request: Request,
        contribution_id: int,
        db: Session = Depends(get_db),
        rejection_reason: str = Form(...),
        review_notes: str | None = Form(None),
    ) -> RedirectResponse | HTMLResponse:
        redir = _guard(request)
        if redir:
            return redir
        c = get_contribution(db, contribution_id)
        if c is None:
            raise HTTPException(status_code=404, detail="Not found")
        if c.status != "pending":
            return HTMLResponse(
                _nav_shell("Reject", "<p>Not pending.</p>"),
                status_code=400,
            )
        if rejection_reason not in get_args(RejectionReason):
            return HTMLResponse(_nav_shell("Reject", "<p>Invalid reason.</p>"), status_code=400)
        update_contribution_status(
            db,
            contribution_id,
            "rejected",
            review_notes=(review_notes or "").strip() or None,
            rejection_reason=rejection_reason,
        )
        msg = quote("Contribution rejected.")
        return RedirectResponse(url=f"/admin/contributions?flash={msg}&kind=ok", status_code=303)

    @router.get("/contributions/{contribution_id}/needs-info", response_class=HTMLResponse, response_model=None)
    def needs_get(request: Request, contribution_id: int, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        c = get_contribution(db, contribution_id)
        if c is None:
            raise HTTPException(status_code=404, detail="Not found")
        if c.status != "pending":
            return HTMLResponse(
                _nav_shell("Needs info", f'<p>Not pending.</p><p><a href="/admin/contributions/{c.id}">Back</a></p>'),
                status_code=400,
            )
        inner = f"""<h1>Needs info — contribution #{c.id}</h1>
<form method="post" action="/admin/contributions/{c.id}/needs-info">
  <label>Review notes (required)</label>
  <textarea name="review_notes" required minlength="1"></textarea>
  <div style="margin-top:14px">
    <button type="submit" class="btn btn-info">Save</button>
    <a href="/admin/contributions/{c.id}" style="margin-left:10px">Cancel</a>
  </div>
</form>"""
        return HTMLResponse(_nav_shell("Needs info", inner))

    @router.post("/contributions/{contribution_id}/needs-info", response_class=HTMLResponse, response_model=None)
    def needs_post(
        request: Request,
        contribution_id: int,
        db: Session = Depends(get_db),
        review_notes: str = Form(...),
    ) -> RedirectResponse | HTMLResponse:
        redir = _guard(request)
        if redir:
            return redir
        c = get_contribution(db, contribution_id)
        if c is None:
            raise HTTPException(status_code=404, detail="Not found")
        if c.status != "pending":
            return HTMLResponse(
                _nav_shell("Needs info", "<p>Not pending.</p>"),
                status_code=400,
            )
        notes = (review_notes or "").strip()
        if not notes:
            return HTMLResponse(
                _nav_shell("Needs info", '<p class="err">Review notes are required.</p>'),
                status_code=400,
            )
        update_contribution_status(db, contribution_id, "needs_info", review_notes=notes)
        msg = quote("Marked as needs info.")
        return RedirectResponse(url=f"/admin/contributions?flash={msg}&kind=ok", status_code=303)
