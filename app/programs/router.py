from __future__ import annotations

import html

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.models import Program
from app.schemas.program import ProgramCreate, ProgramRead

router = APIRouter()

_PROGRAM_DAYS_ORDER = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _program_from_create(payload: ProgramCreate) -> Program:
    # Admin-submitted entries are auto-verified; provider/parent stay unverified
    # until AA-3's claim flow promotes them.
    verified = payload.source == "admin"
    return Program(
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
        verified=verified,
        is_active=payload.is_active,
        tags=list(payload.tags),
        embedding=payload.embedding,
    )


@router.post("/programs", response_model=ProgramRead)
@limiter.limit("5/minute")
def create_program(
    request: Request, payload: ProgramCreate, db: Session = Depends(get_db)
) -> Program:
    program = _program_from_create(payload)
    db.add(program)
    db.commit()
    db.refresh(program)
    return program


@router.get("/programs", response_model=list[ProgramRead])
def list_programs(db: Session = Depends(get_db)) -> list[Program]:
    return (
        db.query(Program)
        .filter(Program.is_active.is_(True))
        .order_by(Program.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Public parent-submission flow (Session AA-2)
# ---------------------------------------------------------------------------
# NOTE: /programs/submit is declared before /programs/{program_id} so the
# literal path wins over the dynamic one in FastAPI's route table.


def _submit_form_html(
    *,
    error: str | None = None,
    values: dict | None = None,
) -> str:
    v = dict(values or {})
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

    def inp(name: str, *, kind: str = "text", placeholder: str = "") -> str:
        return (
            f'<input type="{kind}" id="{name}" name="{name}" '
            f'value="{html.escape(str(v.get(name, "")))}" '
            f'placeholder="{html.escape(placeholder)}" />'
        )

    selected_days: set[str] = {
        str(d).lower() for d in v.get("schedule_days", []) if isinstance(d, str)
    }
    day_boxes = "".join(
        f'<label class="day-opt"><input type="checkbox" name="schedule_days" value="{d}"'
        f'{" checked" if d in selected_days else ""}/> {d.capitalize()}</label>'
        for d in _PROGRAM_DAYS_ORDER
    )
    err_html = f'<p class="err">{html.escape(error)}</p>' if error else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Submit a program — Havasu Chat</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      margin: 0; padding: 20px; background: #fff; color: #212529; line-height: 1.5;
      padding-bottom: 48px; }}
    .wrap {{ max-width: 640px; margin: 0 auto; }}
    h1 {{ font-size: 1.4rem; margin: 0 0 6px; }}
    .intro {{ color: #495057; font-size: 0.95rem; margin: 0 0 20px; }}
    form label {{ display: block; font-weight: 600; margin: 14px 0 6px; color: #343a40; }}
    form input[type=text], form input[type=number],
    form input[type=email], form input[type=url], form textarea {{
      width: 100%; padding: 12px 14px; font-size: 1rem; border: 1px solid #ced4da;
      border-radius: 10px; min-height: 44px; font-family: inherit;
    }}
    form textarea {{ min-height: 110px; resize: vertical; }}
    form .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    form .row > div {{ flex: 1 1 160px; }}
    form .days {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; }}
    form .day-opt {{ display: inline-flex; align-items: center; gap: 6px; margin: 0;
      font-weight: 500; padding: 8px 12px; border: 1px solid #dee2e6; border-radius: 999px;
      background: #f8f9fa; min-height: 40px; }}
    .btn {{ min-height: 48px; min-width: 140px; padding: 12px 18px; font-size: 1rem;
      font-weight: 600; border: none; border-radius: 10px; cursor: pointer;
      background: #0d6efd; color: #fff; }}
    .btn-link {{ color: #0d6efd; text-decoration: none; padding: 12px 18px;
      min-height: 48px; display: inline-flex; align-items: center; }}
    .err {{ color: #b02a37; font-weight: 500; margin: 12px 0; padding: 12px 14px;
      background: #f8d7da; border-radius: 8px; }}
    .actions {{ margin: 20px 0; display: flex; gap: 10px; flex-wrap: wrap; }}
    .note {{ color: #6c757d; font-size: 0.82rem; margin-top: 18px; }}
    a {{ color: #0d6efd; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Submit a program</h1>
    <p class="intro">Know of a great class or program in Havasu? Fill this out and we'll review it. Nothing goes live until someone checks it first.</p>
    <form method="post" action="/programs/submit">
      {err_html}
      <label for="title">What's it called?</label>
      {inp("title", placeholder="e.g. Junior Golf Lessons")}

      <label for="description">Tell us about it</label>
      <textarea id="description" name="description"
        placeholder="Who is it for, what happens, how often (at least 20 characters)">{html.escape(v.get("description", ""))}</textarea>

      <label for="activity_category">Activity type</label>
      {inp("activity_category", placeholder="golf, swim, dance, martial arts, ...")}

      <div class="row">
        <div>
          <label for="age_min">Youngest age</label>
          {inp("age_min", kind="number", placeholder="6")}
        </div>
        <div>
          <label for="age_max">Oldest age</label>
          {inp("age_max", kind="number", placeholder="12")}
        </div>
      </div>

      <label>Which days?</label>
      <div class="days">{day_boxes}</div>

      <div class="row">
        <div>
          <label for="schedule_start_time">Start time (HH:MM)</label>
          {inp("schedule_start_time", placeholder="09:00")}
        </div>
        <div>
          <label for="schedule_end_time">End time (HH:MM)</label>
          {inp("schedule_end_time", placeholder="10:30")}
        </div>
      </div>

      <label for="location_name">Where does it happen?</label>
      {inp("location_name", placeholder="Havasu Golf Academy")}

      <label for="location_address">Street address (optional)</label>
      {inp("location_address", placeholder="Optional")}

      <label for="cost">Cost</label>
      {inp("cost", placeholder="$15/class, Free, varies, ...")}

      <label for="provider_name">Who runs it?</label>
      {inp("provider_name", placeholder="Name of the club, school, or instructor")}

      <div class="row">
        <div>
          <label for="contact_phone">Contact phone (optional)</label>
          {inp("contact_phone", placeholder="928-555-0101")}
        </div>
        <div>
          <label for="contact_email">Contact email (optional)</label>
          {inp("contact_email", kind="email", placeholder="coach@example.com")}
        </div>
      </div>

      <label for="contact_url">Website or sign-up link (optional)</label>
      {inp("contact_url", kind="url", placeholder="https://...")}

      <div class="actions">
        <button type="submit" class="btn">Submit for review</button>
        <a class="btn-link" href="/">Back to chat</a>
      </div>
      <p class="note">Submissions are held for admin review and don't show up in search until approved. Thanks for helping keep this list useful for other parents.</p>
    </form>
  </div>
</body>
</html>"""


def _submit_success_html(program_title: str) -> str:
    safe_title = html.escape(program_title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Thanks — Havasu Chat</title>
  <style>
    body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      margin: 0; padding: 40px 20px; background: #fff; color: #212529; line-height: 1.5; }}
    .wrap {{ max-width: 520px; margin: 0 auto; text-align: center; }}
    h1 {{ font-size: 1.5rem; margin: 0 0 12px; }}
    p {{ color: #495057; margin: 0 0 16px; }}
    .title {{ font-weight: 600; color: #212529; }}
    .actions {{ margin-top: 24px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }}
    .btn {{ min-height: 48px; padding: 12px 18px; font-size: 1rem; font-weight: 600;
      border: none; border-radius: 10px; background: #0d6efd; color: #fff; text-decoration: none;
      display: inline-flex; align-items: center; }}
    .btn-outline {{ background: #fff; color: #0d6efd; border: 1px solid #0d6efd; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Thanks! We got it.</h1>
    <p>Your submission for <span class="title">{safe_title}</span> is in the review queue. Once an admin gives it a look, it'll start showing up when people ask about classes and programs in Havasu.</p>
    <div class="actions">
      <a class="btn" href="/">Back to chat</a>
      <a class="btn btn-outline" href="/programs/submit">Submit another</a>
    </div>
  </div>
</body>
</html>"""


@router.get("/programs/submit", response_class=HTMLResponse)
def program_submit_form(request: Request) -> HTMLResponse:
    return HTMLResponse(_submit_form_html())


@router.post("/programs/submit", response_class=HTMLResponse)
@limiter.limit("3/minute")
def program_submit(
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
    db: Session = Depends(get_db),
) -> HTMLResponse:
    def _maybe_int(s: str) -> int | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def _nonempty(s: str) -> str | None:
        s = (s or "").strip()
        return s or None

    raw = {
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
        # Submitter cannot self-declare source/active/verified — forced server-side.
        "source": "parent",
        "is_active": False,
    }
    try:
        payload = ProgramCreate(**raw)
    except Exception as exc:
        return HTMLResponse(
            _submit_form_html(error=str(exc), values=raw),
            status_code=400,
        )
    # Force parent semantics regardless of what Pydantic coerced.
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
        source="parent",
        verified=False,
        is_active=False,
        tags=list(payload.tags),
        embedding=None,
    )
    db.add(program)
    db.commit()
    db.refresh(program)
    return HTMLResponse(_submit_success_html(program.title))


@router.get("/programs/{program_id}", response_model=ProgramRead)
def get_program(program_id: str, db: Session = Depends(get_db)) -> Program:
    program = db.query(Program).filter(Program.id == program_id).first()
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program
