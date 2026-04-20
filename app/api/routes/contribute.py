"""Public contribution form at ``/contribute`` (Phase 5.4)."""

from __future__ import annotations

import hashlib
import html
from datetime import UTC, date, datetime, time, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from slowapi.util import get_remote_address

from app.contrib.enrichment import enrich_contribution
from app.core.rate_limit import is_rate_limit_disabled
from app.db.contribution_store import (
    count_submissions_since_by_ip_hash,
    create_contribution,
    has_pending_or_approved_duplicate_url,
    normalize_submission_url,
)
from app.db.database import SessionLocal, get_db
from app.schemas.contribution import ContributionCreate

router = APIRouter(tags=["contribute"])

_MAX_NOTES = 2000

_RATE_MSG = "Thanks for your enthusiasm — please wait an hour between submissions."
_DUP_MSG = "We already have this in our review queue. Thanks though!"
_THIN_MSG = "Please add a short description or a URL — something so we know what this is about."
_SUCCESS_INTRO = (
    "Thanks! Your contribution is in our review queue. If you added an email, we'll come back to you "
    "if we have questions. Otherwise it'll show up in the catalog once approved."
)


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _ip_hash(request: Request) -> str:
    ip = get_remote_address(request) or ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _rate_limited(request: Request, db: Session) -> bool:
    if is_rate_limit_disabled():
        return False
    h = _ip_hash(request)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    return count_submissions_since_by_ip_hash(db, h, since) >= 1


def _parse_optional_date(raw: str | None) -> date | None:
    if raw is None or not str(raw).strip():
        return None
    return date.fromisoformat(str(raw).strip())


def _parse_optional_time(raw: str | None) -> time | None:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()
    if len(s) == 5:
        return time.fromisoformat(s + ":00")
    return time.fromisoformat(s)


def _render_contribute_page(
    *,
    submitted: bool = False,
    error_banner: str | None = None,
    field_errors: dict[str, str] | None = None,
    preserve: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    p = preserve or {}
    fe = field_errors or {}
    err_html = ""
    if error_banner:
        err_html = f'<div class="banner err">{_esc(error_banner)}</div>'
    if fe:
        ul = "".join(f"<li><strong>{_esc(k)}</strong>: {_esc(v)}</li>" for k, v in fe.items())
        err_html += f'<div class="banner err"><ul class="err-list">{ul}</ul></div>'
    ok_html = ""
    if submitted:
        ok_html = f'<div class="banner ok">{_esc(_SUCCESS_INTRO)}</div>'
    ent = p.get("entity_type", "provider")
    event_css_display = "block" if ent == "event" else "none"
    url_val = _esc(p.get("submission_url", ""))
    return HTMLResponse(
        status_code=status_code,
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Contribute — Havasu Chat</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #212529;
      line-height: 1.45; padding-bottom: 48px; }}
    .wrap {{ max-width: 640px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
    .intro {{ color: #495057; font-size: 0.95rem; margin-bottom: 18px; }}
    .banner {{ padding: 12px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 0.92rem; }}
    .banner.ok {{ background: #d1e7dd; color: #0f5132; }}
    .banner.err {{ background: #f8d7da; color: #842029; }}
    .err-list {{ margin: 0; padding-left: 18px; }}
    label {{ display: block; font-weight: 600; font-size: 0.88rem; margin: 12px 0 4px; }}
    input[type=text], input[type=url], input[type=email], input[type=date], input[type=time], textarea, select {{
      width: 100%; max-width: 100%; padding: 10px 12px; border: 1px solid #ced4da; border-radius: 8px; font-size: 1rem; }}
    textarea {{ min-height: 120px; }}
    .row-radio {{ display: flex; flex-wrap: wrap; gap: 10px 16px; margin-top: 6px; }}
    .row-radio label {{ font-weight: 500; margin: 0; }}
    button.submit {{ margin-top: 18px; width: 100%; padding: 14px; font-size: 1.05rem; font-weight: 600;
      background: #0d6efd; color: #fff; border: none; border-radius: 10px; cursor: pointer; }}
    .foot {{ margin-top: 22px; font-size: 0.88rem; }}
    .foot a {{ color: #0d6efd; font-weight: 600; }}
    #event-fields {{ display: {event_css_display}; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Suggest something for the catalog</h1>
    <p class="intro">Havasu Chat grows from what locals contribute. Suggest a business, program, event, or tip you think belongs in the catalog. We'll review and add it if it fits.</p>
    {ok_html}
    {err_html}
    <form method="post" action="/contribute" id="contrib-form">
      <label>What are you submitting?</label>
      <div class="row-radio">
        <label><input type="radio" name="entity_type" value="provider" {"checked" if ent=="provider" else ""}/> Business</label>
        <label><input type="radio" name="entity_type" value="program" {"checked" if ent=="program" else ""}/> Program</label>
        <label><input type="radio" name="entity_type" value="event" {"checked" if ent=="event" else ""}/> Event</label>
        <label><input type="radio" name="entity_type" value="tip" {"checked" if ent=="tip" else ""}/> Tip</label>
      </div>
      <label for="submission_name">Name</label>
      <input type="text" name="submission_name" id="submission_name" maxlength="200" required value="{_esc(p.get("submission_name", ""))}"/>
      <label for="submission_url">Website or listing URL</label>
      <input type="url" name="submission_url" id="submission_url" value="{url_val}" placeholder="https://…" data-url-required-for="provider program"/>
      <label for="category_hint">Category hint (optional)</label>
      <input type="text" name="category_hint" id="category_hint" maxlength="200" placeholder="BMX, gymnastics, dance studio, restaurant" value="{_esc(p.get("category_hint", ""))}"/>
      <label for="description">Description / notes (optional)</label>
      <textarea name="description" id="description" maxlength="{_MAX_NOTES}" placeholder="What should we know about this?">{_esc(p.get("description", ""))}</textarea>
      <div id="event-fields">
        <label for="event_date">Event date</label>
        <input type="date" name="event_date" id="event_date" value="{_esc(p.get("event_date", ""))}"/>
        <label for="event_start_time">Start time</label>
        <input type="time" name="event_start_time" id="event_start_time" value="{_esc(p.get("event_start_time", ""))}"/>
        <label for="event_end_time">End time (optional)</label>
        <input type="time" name="event_end_time" id="event_end_time" value="{_esc(p.get("event_end_time", ""))}"/>
      </div>
      <label for="submitter_email">Email (optional)</label>
      <input type="email" name="submitter_email" id="submitter_email" placeholder="So we can reach you if we have questions" value="{_esc(p.get("submitter_email", ""))}"/>
      <button type="submit" class="submit">Submit for review</button>
    </form>
    <p class="foot"><a href="/">← Back to chat</a></p>
  </div>
  <script>
(function () {{
  var form = document.getElementById("contrib-form");
  var eventBlock = document.getElementById("event-fields");
  var urlInput = document.getElementById("submission_url");
  function entityType() {{
    var r = form.querySelector('input[name="entity_type"]:checked');
    return r ? r.value : "provider";
  }}
  function sync() {{
    var et = entityType();
    eventBlock.style.display = et === "event" ? "block" : "none";
    if (et === "provider" || et === "program") {{ urlInput.setAttribute("required", "required"); }}
    else {{ urlInput.removeAttribute("required"); }}
  }}
  form.querySelectorAll('input[name="entity_type"]').forEach(function (el) {{
    el.addEventListener("change", sync);
  }});
  sync();
}})();
  </script>
</body>
</html>""",
    )


@router.get("/contribute", response_class=HTMLResponse, response_model=None)
def get_contribute(submitted: int | None = None) -> HTMLResponse:
    return _render_contribute_page(submitted=bool(submitted))


@router.post("/contribute", response_class=HTMLResponse, response_model=None)
def post_contribute(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    entity_type: str = Form(...),
    submission_name: str = Form(...),
    submission_url: str | None = Form(None),
    category_hint: str | None = Form(None),
    description: str | None = Form(None),
    event_date: str | None = Form(None),
    event_start_time: str | None = Form(None),
    event_end_time: str | None = Form(None),
    submitter_email: str | None = Form(None),
) -> HTMLResponse | RedirectResponse:
    preserve = {
        "entity_type": entity_type.strip(),
        "submission_name": submission_name,
        "submission_url": submission_url or "",
        "category_hint": category_hint or "",
        "description": description or "",
        "event_date": event_date or "",
        "event_start_time": event_start_time or "",
        "event_end_time": event_end_time or "",
        "submitter_email": submitter_email or "",
    }
    if _rate_limited(request, db):
        return _render_contribute_page(error_banner=_RATE_MSG, preserve=preserve, status_code=429)

    notes = (description or "").strip()
    if len(notes) > _MAX_NOTES:
        return _render_contribute_page(
            field_errors={"description": f"Please keep notes to {_MAX_NOTES} characters or fewer."},
            preserve=preserve,
        )

    url_s = (submission_url or "").strip()
    et = entity_type.strip().lower()
    if et not in ("provider", "program", "event", "tip"):
        return _render_contribute_page(
            field_errors={"entity_type": "Choose a valid submission type."},
            preserve=preserve,
        )
    if et in ("provider", "program") and not url_s:
        return _render_contribute_page(
            field_errors={"submission_url": "A URL is required for businesses and programs."},
            preserve=preserve,
        )

    if not url_s and not notes:
        return _render_contribute_page(error_banner=_THIN_MSG, preserve=preserve)

    norm_dup = normalize_submission_url(url_s if url_s else None)
    if norm_dup and has_pending_or_approved_duplicate_url(db, norm_dup):
        return _render_contribute_page(error_banner=_DUP_MSG, preserve=preserve)

    ev_d: date | None = None
    ev_st: time | None = None
    ev_en: time | None = None
    if et == "event":
        try:
            ev_d = _parse_optional_date(event_date)
            ev_st = _parse_optional_time(event_start_time)
            ev_en = _parse_optional_time(event_end_time)
        except ValueError:
            return _render_contribute_page(
                field_errors={"event_date": "Use a valid date and times."},
                preserve=preserve,
            )

    url_for_model: str | None = url_s if url_s else None
    try:
        body = ContributionCreate(
            entity_type=et,  # type: ignore[arg-type]
            submission_name=submission_name.strip(),
            submission_url=url_for_model,  # type: ignore[arg-type]
            submission_category_hint=(category_hint or "").strip() or None,
            submission_notes=notes or None,
            event_date=ev_d,
            event_time_start=ev_st,
            event_time_end=ev_en,
            submitter_email=(submitter_email or "").strip() or None,  # type: ignore[arg-type]
            source="user_submission",
        )
    except ValidationError as e:
        fe: dict[str, str] = {}
        for err in e.errors():
            loc = ".".join(str(x) for x in err.get("loc", ()))
            fe[loc or "form"] = err.get("msg", "Invalid value")
        return _render_contribute_page(field_errors=fe, preserve=preserve)

    row = create_contribution(db, body, submitter_ip_hash=_ip_hash(request))
    background_tasks.add_task(enrich_contribution, row.id, SessionLocal)
    return RedirectResponse(url="/contribute?submitted=1", status_code=302)
