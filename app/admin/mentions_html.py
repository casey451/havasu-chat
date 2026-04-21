"""HTML admin UI for LLM-mentioned entities (Phase 5.5)."""

from __future__ import annotations

import html
from datetime import date, datetime, time
from typing import get_args
from urllib.parse import quote, urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.contrib.enrichment import enrich_contribution
from app.db.contribution_store import create_contribution
from app.db.database import SessionLocal, get_db
from app.db.llm_mention_store import (
    count_mentions,
    dismiss_mention,
    get_mention,
    list_mentions,
    promote_mention,
)
from app.db.models import ChatLog, Event, Program, Provider
from app.schemas.contribution import ContributionCreate
from app.schemas.llm_mention import DismissalReason

_VALID_LIST_STATUSES = frozenset({"unreviewed", "promoted", "dismissed", "all"})


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


def _catalog_hint_pill(db: Session, mentioned_name: str) -> str:
    """Non-authoritative substring hint vs provider/program/event names."""
    m = (mentioned_name or "").strip().lower()
    if len(m) < 3:
        return '<span class="pill pill-muted">?</span>'
    names: list[str] = []
    names.extend(str(x) for x in db.execute(select(Provider.provider_name)).scalars().all() if x)
    names.extend(str(x) for x in db.execute(select(Program.title)).scalars().all() if x)
    names.extend(str(x) for x in db.execute(select(Event.title)).scalars().all() if x)
    for c in names:
        cl = c.strip().lower()
        if len(cl) < 3:
            continue
        if m in cl or cl in m:
            return '<span class="pill pill-ok" title="Substring only — not authoritative">Possibly</span>'
    return '<span class="pill pill-muted">No hit</span>'


def _mention_status_pill(status: str) -> str:
    cls = {
        "unreviewed": "pill-pending",
        "promoted": "pill-approved",
        "dismissed": "pill-rejected",
    }.get(status, "pill-pending")
    return f'<span class="pill {cls}">{_esc(status)}</span>'


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
    .pill-muted {{ background: #e2e3e5; color: #41464b; }}
    .pill-ok {{ background: #cfe2ff; color: #084298; }}
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
    label {{ display: block; font-weight: 600; font-size: 0.88rem; margin: 10px 0 4px; }}
    input[type=text], input[type=url], input[type=date], select, textarea {{
      width: 100%; max-width: 100%; padding: 8px 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 0.95rem; }}
    textarea {{ min-height: 90px; }}
    .empty {{ color: #6c757d; padding: 20px; text-align: center; }}
    .err {{ color: #842029; font-size: 0.88rem; margin-top: 4px; }}
    .pagination {{ margin-top: 12px; font-size: 0.9rem; }}
    pre.msg {{ white-space: pre-wrap; font-family: inherit; font-size: 0.88rem; max-height: 220px; overflow: auto; }}
  </style>
</head>
<body>
  <div class="wrap">
    <nav class="nav">
      <a href="/admin?tab=queue">Admin home</a>
      <a href="/admin/contributions">Contributions</a>
      <a href="/admin/mentioned-entities">Mentioned entities</a>
    </nav>
    {inner}
  </div>
</body>
</html>"""


def register_mentions_html_routes(router: APIRouter) -> None:
    @router.get("/mentioned-entities", response_class=HTMLResponse, response_model=None)
    def mentions_list(
        request: Request,
        db: Session = Depends(get_db),
        status: str = Query("unreviewed"),
        detected_from: str | None = Query(None),
        detected_to: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        flash: str | None = None,
        flash_kind: str | None = Query(None, alias="kind"),
    ) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        st_key = status if status in _VALID_LIST_STATUSES else "unreviewed"
        filter_status: str | None = None if st_key == "all" else st_key
        lo: datetime | None = None
        hi: datetime | None = None
        if detected_from:
            try:
                y, mo, d = (int(x) for x in detected_from.split("-", 2))
                lo = datetime(y, mo, d)
            except Exception:
                raise HTTPException(status_code=422, detail="invalid detected_from") from None
        if detected_to:
            try:
                y, mo, d = (int(x) for x in detected_to.split("-", 2))
                hi = datetime.combine(date(y, mo, d), time(23, 59, 59))
            except Exception:
                raise HTTPException(status_code=422, detail="invalid detected_to") from None
        rows = list_mentions(
            db,
            status=filter_status,
            detected_from=lo,
            detected_to=hi,
            limit=limit,
            offset=offset,
        )
        total = count_mentions(db, status=filter_status, detected_from=lo, detected_to=hi)
        flash_html = ""
        if flash:
            fk = "flash-ok" if (flash_kind or "ok") == "ok" else "flash-err"
            flash_html = f'<div class="flash {fk}">{_esc(flash)}</div>'
        q_base: dict[str, str] = {}
        if st_key != "unreviewed":
            q_base["status"] = st_key
        if detected_from:
            q_base["detected_from"] = detected_from
        if detected_to:
            q_base["detected_to"] = detected_to
        if total == 0:
            empty_msg = (
                "No mentions logged yet."
                if count_mentions(db) == 0
                else "No mentions match these filters."
            )
            table_body = f'<p class="empty">{empty_msg}</p>'
        else:
            trs: list[str] = []
            for r in rows:
                link = f'<a href="/admin/mentioned-entities/{r.id}">{_esc(r.mentioned_name)}</a>'
                ctx = (r.context_snippet or "")[:80]
                if (r.context_snippet or "") and len(r.context_snippet) > 80:
                    ctx += "…"
                hint = _catalog_hint_pill(db, r.mentioned_name)
                actions = ""
                if r.status == "unreviewed":
                    actions = (
                        f'<a class="btn btn-info" href="/admin/mentioned-entities/{r.id}/promote">Promote</a> '
                        f'<a class="btn btn-secondary" href="/admin/mentioned-entities/{r.id}/dismiss">Dismiss</a>'
                    )
                trs.append(
                    "<tr>"
                    f"<td>{_esc(_fmt_compact_ts(r.detected_at))}</td>"
                    f"<td>{link}</td>"
                    f"<td>{_esc(ctx)}</td>"
                    f"<td>{_mention_status_pill(r.status)}</td>"
                    f"<td>{hint}</td>"
                    f"<td>{actions}</td>"
                    "</tr>"
                )
            table_body = (
                "<table><thead><tr>"
                "<th>Detected</th><th>Mention</th><th>Context</th><th>Status</th>"
                "<th>In catalog?</th><th>Actions</th>"
                "</tr></thead><tbody>"
                + "".join(trs)
                + "</tbody></table>"
            )
        filter_form = f"""
<form method="get" class="section" style="background:#fff">
  <label>Status</label>
  <select name="status">
    <option value="unreviewed" {"selected" if st_key=="unreviewed" else ""}>unreviewed</option>
    <option value="promoted" {"selected" if st_key=="promoted" else ""}>promoted</option>
    <option value="dismissed" {"selected" if st_key=="dismissed" else ""}>dismissed</option>
    <option value="all" {"selected" if st_key=="all" else ""}>all</option>
  </select>
  <label>Detected from (YYYY-MM-DD)</label>
  <input type="text" name="detected_from" value="{_esc(detected_from or "")}" placeholder="optional" />
  <label>Detected to (YYYY-MM-DD)</label>
  <input type="text" name="detected_to" value="{_esc(detected_to or "")}" placeholder="optional" />
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
            prev_link = f'<a href="/admin/mentioned-entities?{urlencode(q_prev)}">Previous</a>' if offset > 0 else "Previous"
            next_link = (
                f'<a href="/admin/mentioned-entities?{urlencode(q_next)}">Next</a>' if offset + limit < total else "Next"
            )
            pages = (
                f'<p class="pagination">{prev_link} · showing {offset + 1}–{min(offset + limit, total)} of {total} · {next_link}</p>'
            )
        inner = f"""{flash_html}
<h1>LLM-mentioned entities</h1>
<p class="sub">Tier 3 title-case candidates. JSON: <code>/admin/api/mentioned-entities</code>.</p>
{filter_form}
{table_body}
{pages}"""
        return HTMLResponse(_nav_shell("Mentioned entities", inner))

    @router.get("/mentioned-entities/{mention_id}", response_class=HTMLResponse, response_model=None)
    def mention_detail(request: Request, mention_id: int, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        row = get_mention(db, mention_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        log = db.get(ChatLog, row.chat_log_id)
        log_block = "<p>No matching chat log row.</p>"
        if log is not None:
            log_block = f"""<div class="section"><h2>Source assistant message (chat_logs)</h2>
<p class="kv"><span class="k">chat_log id</span> <code>{_esc(str(log.id))}</code></p>
<pre class="msg">{_esc(log.message or "")}</pre></div>"""
        actions = ""
        if row.status == "unreviewed":
            actions = f"""<div class="actions">
<a class="btn btn-info" href="/admin/mentioned-entities/{row.id}/promote">Promote to contribution</a>
<a class="btn btn-secondary" href="/admin/mentioned-entities/{row.id}/dismiss">Dismiss</a>
</div>"""
        promoted = ""
        if row.promoted_to_contribution_id:
            cid = row.promoted_to_contribution_id
            promoted = f'<p class="kv"><span class="k">Promoted to</span> <a href="/admin/contributions/{cid}">contribution #{cid}</a></p>'
        inner = f"""<h1>Mention #{row.id}</h1>
<div class="section">
<div class="kv"><span class="k">Name</span> {_esc(row.mentioned_name)}</div>
<div class="kv"><span class="k">Context</span> {_esc(row.context_snippet or "—")}</div>
<div class="kv"><span class="k">Detected</span> {_esc(_fmt_compact_ts(row.detected_at))}</div>
<div class="kv"><span class="k">Status</span> {_mention_status_pill(row.status)}</div>
<div class="kv"><span class="k">Catalog hint</span> {_catalog_hint_pill(db, row.mentioned_name)}</div>
{promoted}
</div>
{log_block}
{actions}
<p style="margin-top:18px"><a href="/admin/mentioned-entities">← Back to list</a></p>"""
        return HTMLResponse(_nav_shell(f"Mention {row.id}", inner))

    @router.get("/mentioned-entities/{mention_id}/promote", response_class=HTMLResponse, response_model=None)
    def promote_get(request: Request, mention_id: int, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        row = get_mention(db, mention_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status != "unreviewed":
            return HTMLResponse(_nav_shell("Promote", "<p>Not unreviewed.</p>"), status_code=400)
        notes_default = row.context_snippet or ""
        inner = f"""<h1>Promote mention</h1>
<p class="sub">Creates a contribution with <code>source=llm_inferred</code> and schedules enrichment.</p>
<form method="post" action="/admin/mentioned-entities/{row.id}/promote">
  <fieldset>
    <legend>Entity type</legend>
    <label><input type="radio" name="entity_type" value="provider" checked/> provider</label>
    <label><input type="radio" name="entity_type" value="program"/> program</label>
    <label><input type="radio" name="entity_type" value="event"/> event</label>
    <label><input type="radio" name="entity_type" value="tip"/> tip</label>
  </fieldset>
  <label>Name</label>
  <input type="text" name="submission_name" value="{_esc(row.mentioned_name)}" required maxlength="200" />
  <label>URL (required for provider / program)</label>
  <input type="url" name="submission_url" value="" />
  <label>Category hint (optional)</label>
  <input type="text" name="submission_category_hint" value="" maxlength="200" />
  <label>Notes (optional)</label>
  <textarea name="submission_notes">{_esc(notes_default)}</textarea>
  <label>Event date (optional, events)</label>
  <input type="date" name="event_date" value="" />
  <div style="margin-top:14px">
    <button type="submit" class="btn btn-primary">Create contribution</button>
    <a href="/admin/mentioned-entities/{row.id}" style="margin-left:10px">Cancel</a>
  </div>
</form>"""
        return HTMLResponse(_nav_shell("Promote", inner))

    @router.post("/mentioned-entities/{mention_id}/promote", response_class=HTMLResponse, response_model=None)
    def promote_post(
        request: Request,
        mention_id: int,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        entity_type: str = Form(...),
        submission_name: str = Form(...),
        submission_url: str = Form(""),
        submission_category_hint: str = Form(""),
        submission_notes: str | None = Form(None),
        event_date: str = Form(""),
    ) -> RedirectResponse | HTMLResponse:
        redir = _guard(request)
        if redir:
            return redir
        row = get_mention(db, mention_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status != "unreviewed":
            return HTMLResponse(_nav_shell("Promote", "<p>Not unreviewed.</p>"), status_code=400)
        et = (entity_type or "").strip()
        if et not in ("provider", "program", "event", "tip"):
            return HTMLResponse(_nav_shell("Promote", '<p class="err">Invalid entity type.</p>'), status_code=400)
        url_s = (submission_url or "").strip() or None
        if et in ("provider", "program") and not url_s:
            return HTMLResponse(
                _nav_shell(
                    "Promote",
                    '<p class="err">URL is required for provider and program.</p>'
                    f'<p><a href="/admin/mentioned-entities/{mention_id}/promote">Back</a></p>',
                ),
                status_code=400,
            )
        ev_date: date | None = None
        if (event_date or "").strip():
            try:
                ev_date = date.fromisoformat(event_date.strip())
            except ValueError:
                return HTMLResponse(_nav_shell("Promote", '<p class="err">Invalid event date.</p>'), status_code=400)
        hint = (submission_category_hint or "").strip() or None
        notes = (submission_notes or "").strip() or None
        try:
            body = ContributionCreate(
                entity_type=et,  # type: ignore[arg-type]
                submission_name=submission_name.strip(),
                submission_url=url_s,  # type: ignore[arg-type]
                submission_category_hint=hint,
                submission_notes=notes,
                event_date=ev_date,
                source="llm_inferred",
                llm_source_chat_log_id=row.chat_log_id,
            )
        except ValidationError as exc:
            return HTMLResponse(
                _nav_shell(
                    "Promote",
                    f'<p class="err">{_esc(str(exc))}</p><p><a href="/admin/mentioned-entities/{mention_id}/promote">Back</a></p>',
                ),
                status_code=400,
            )
        contrib = create_contribution(db, body, submitter_ip_hash=None)
        background_tasks.add_task(enrich_contribution, contrib.id, SessionLocal)
        promote_mention(db, mention_id, contrib.id)
        msg = quote("Contribution created from mention.")
        return RedirectResponse(url=f"/admin/mentioned-entities?flash={msg}&kind=ok", status_code=303)

    @router.get("/mentioned-entities/{mention_id}/dismiss", response_class=HTMLResponse, response_model=None)
    def dismiss_get(request: Request, mention_id: int, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        row = get_mention(db, mention_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status != "unreviewed":
            return HTMLResponse(_nav_shell("Dismiss", "<p>Not unreviewed.</p>"), status_code=400)
        opts = "".join(
            f'<option value="{_esc(r)}">{_esc(r)}</option>' for r in get_args(DismissalReason)
        )
        inner = f"""<h1>Dismiss mention</h1>
<form method="post" action="/admin/mentioned-entities/{row.id}/dismiss">
  <label>Reason</label>
  <select name="dismissal_reason" required>{opts}</select>
  <div style="margin-top:14px">
    <button type="submit" class="btn btn-secondary">Dismiss</button>
    <a href="/admin/mentioned-entities/{row.id}" style="margin-left:10px">Cancel</a>
  </div>
</form>"""
        return HTMLResponse(_nav_shell("Dismiss", inner))

    @router.post("/mentioned-entities/{mention_id}/dismiss", response_class=HTMLResponse, response_model=None)
    def dismiss_post(
        request: Request,
        mention_id: int,
        db: Session = Depends(get_db),
        dismissal_reason: str = Form(...),
    ) -> RedirectResponse | HTMLResponse:
        redir = _guard(request)
        if redir:
            return redir
        row = get_mention(db, mention_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status != "unreviewed":
            return HTMLResponse(_nav_shell("Dismiss", "<p>Not unreviewed.</p>"), status_code=400)
        if dismissal_reason not in get_args(DismissalReason):
            return HTMLResponse(_nav_shell("Dismiss", '<p class="err">Invalid reason.</p>'), status_code=400)
        dismiss_mention(db, mention_id, dismissal_reason)
        msg = quote("Mention dismissed.")
        return RedirectResponse(url=f"/admin/mentioned-entities?flash={msg}&kind=ok", status_code=303)
