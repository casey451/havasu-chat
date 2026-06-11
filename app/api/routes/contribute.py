"""Public contribution form at ``/contribute`` (Phase 5.4)."""

from __future__ import annotations

import hashlib
import html
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.contrib.enrichment import enrich_contribution
from app.core.background import with_retry
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
        err_html = f'<div class="banner err" role="alert">{_esc(error_banner)}</div>'
    if fe:
        ul = "".join(f"<li><strong>{_esc(k)}</strong>: {_esc(v)}</li>" for k, v in fe.items())
        err_html += f'<div class="banner err" role="alert"><ul class="err-list">{ul}</ul></div>'
    ok_html = ""
    if submitted:
        ok_html = f'<div class="banner ok" role="status">{_esc(_SUCCESS_INTRO)}</div>'
    ent = p.get("entity_type", "provider")
    event_css_display = "block" if ent == "event" else "none"
    url_val = _esc(p.get("submission_url", ""))
    # BUILD.md step 1.5: visual restyle to match /home design system. Form
    # behavior, field IDs/names, and JS are unchanged from the prior version
    # — only markup wrapping and CSS were touched.
    return HTMLResponse(
        status_code=status_code,
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Add to Hava — Ask Hava</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;1,9..144,400&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="/static/styles/contribute.css"/>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="page">
    <header class="topbar">
      <a class="wordmark" href="/home">
        <span class="mark"></span>
        <span>Hava</span>
      </a>
      <div class="topbar-meta">
        <a href="/home">Back to Hava</a>
      </div>
    </header>

    <main id="main">
    <section class="head">
      <p class="eyebrow">Add to Hava</p>
      <h1>Tell me what <em>belongs</em>.</h1>
      <p class="lede">Hava grows from what locals share. Suggest a business, program, event, or tip — I'll review and add it if it fits.</p>
    </section>

    {ok_html}
    {err_html}

    <form class="form-card" method="post" action="/contribute" id="contrib-form">
      <fieldset class="type-fieldset">
      <legend>What are you submitting?</legend>
      <div class="row-radio">
        <label><input type="radio" name="entity_type" value="provider" {"checked" if ent == "provider" else ""}/> Business</label>
        <label><input type="radio" name="entity_type" value="program" {"checked" if ent == "program" else ""}/> Program</label>
        <label><input type="radio" name="entity_type" value="event" {"checked" if ent == "event" else ""}/> Event</label>
        <label><input type="radio" name="entity_type" value="tip" {"checked" if ent == "tip" else ""}/> Tip</label>
      </div>
      </fieldset>

      <label for="submission_name">Name <span class="req" aria-hidden="true">*</span></label>
      <input type="text" name="submission_name" id="submission_name" maxlength="200" required aria-required="true" value="{_esc(p.get("submission_name", ""))}"/>

      <label for="submission_url">Website or listing URL <span class="req" id="url-req" aria-hidden="true" {"" if ent in ("provider", "program") else "hidden"}>*</span></label>
      <input type="url" name="submission_url" id="submission_url" value="{url_val}" placeholder="https://…" data-url-required-for="provider program"/>

      <label for="category_hint">Category hint (optional)</label>
      <input type="text" name="category_hint" id="category_hint" maxlength="200" placeholder="BMX, gymnastics, dance studio, restaurant" value="{_esc(p.get("category_hint", ""))}"/>

      <label for="description">Description / notes (optional)</label>
      <textarea name="description" id="description" maxlength="{_MAX_NOTES}" placeholder="What should we know about this?">{_esc(p.get("description", ""))}</textarea>

      <div id="event-fields" style="display: {event_css_display};">
        <label for="event_date">Event date <span class="req" id="event-date-req" aria-hidden="true" {"" if ent == "event" else "hidden"}>*</span></label>
        <input type="date" name="event_date" id="event_date" value="{_esc(p.get("event_date", ""))}"/>

        <label for="event_start_time">Start time <span class="req" id="event-start-req" aria-hidden="true" {"" if ent == "event" else "hidden"}>*</span></label>
        <input type="time" name="event_start_time" id="event_start_time" value="{_esc(p.get("event_start_time", ""))}"/>

        <label for="event_end_time">End time (optional)</label>
        <input type="time" name="event_end_time" id="event_end_time" value="{_esc(p.get("event_end_time", ""))}"/>
      </div>

      <label for="submitter_email">Email (optional)</label>
      <input type="email" name="submitter_email" id="submitter_email" autocomplete="email" placeholder="So we can reach you if we have questions" value="{_esc(p.get("submitter_email", ""))}"/>
      <p class="field-note">We only use your email to follow up on this submission -- never for marketing.</p>

      <p class="req-legend"><span class="req" aria-hidden="true">*</span> Required</p>
      <button type="submit" class="submit">Submit for review</button>
      <p class="review-note">We review most submissions within a few days.</p>
    </form>

    <p class="foot"><a href="/home">← Back to Hava</a></p>
    </main>
  </div>

  <script>
(function () {{
  var form = document.getElementById("contrib-form");
  var eventBlock = document.getElementById("event-fields");
  var urlInput = document.getElementById("submission_url");
  var urlReq = document.getElementById("url-req");
  var eventDate = document.getElementById("event_date");
  var eventStart = document.getElementById("event_start_time");
  var eventDateReq = document.getElementById("event-date-req");
  var eventStartReq = document.getElementById("event-start-req");
  function entityType() {{
    var r = form.querySelector('input[name="entity_type"]:checked');
    return r ? r.value : "provider";
  }}
  function setRequired(el, badge, on) {{
    if (el) {{
      if (on) {{ el.setAttribute("required", "required"); }}
      else {{ el.removeAttribute("required"); }}
    }}
    if (badge) {{ badge.hidden = !on; }}
  }}
  function sync() {{
    var et = entityType();
    var isEvent = et === "event";
    eventBlock.style.display = isEvent ? "block" : "none";
    var urlRequired = et === "provider" || et === "program";
    if (urlRequired) {{ urlInput.setAttribute("required", "required"); }}
    else {{ urlInput.removeAttribute("required"); }}
    if (urlReq) {{ urlReq.hidden = !urlRequired; }}
    // Event date + start time are required only while "Event" is selected.
    // Hidden, non-required fields can't block submission of the other types.
    setRequired(eventDate, eventDateReq, isEvent);
    setRequired(eventStart, eventStartReq, isEvent);
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


_PREFILL_KINDS = frozenset({"provider", "program", "event", "tip"})


@router.get("/contribute", response_class=HTMLResponse, response_model=None)
def get_contribute(
    submitted: int | None = None,
    name: str | None = None,
    url: str | None = None,
    kind: str | None = None,
    category: str | None = None,
    note: str | None = None,
) -> HTMLResponse:
    """The contribute form. Optional query params let calm-texture "suggest an
    edit" links on provider/category pages open the form pre-filled, so a local
    who spots a stale listing lands one click from describing the fix. Prefill is
    cosmetic — the same reviewed POST pipeline handles the submission."""
    preserve: dict[str, str] = {}
    if kind and kind in _PREFILL_KINDS:
        preserve["entity_type"] = kind
    if name:
        preserve["submission_name"] = name.strip()[:200]
    if url:
        preserve["submission_url"] = url.strip()[:2048]
    if category:
        preserve["category_hint"] = category.strip()[:200]
    if note:
        preserve["description"] = note.strip()[:_MAX_NOTES]
    return _render_contribute_page(submitted=bool(submitted), preserve=preserve or None)


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
        # Date + start time are required for events. The client marks them
        # ``required`` via sync(), but JS can be bypassed, so enforce here too.
        ev_field_errors: dict[str, str] = {}
        if ev_d is None:
            ev_field_errors["event_date"] = "An event needs a date."
        if ev_st is None:
            ev_field_errors["event_start_time"] = "An event needs a start time."
        if ev_field_errors:
            return _render_contribute_page(field_errors=ev_field_errors, preserve=preserve)

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
    background_tasks.add_task(with_retry, enrich_contribution, row.id, SessionLocal)
    return RedirectResponse(url="/contribute?submitted=1", status_code=302)
