"""Public contribution form at ``/contribute`` (Phase 5.4)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.contrib.enrichment import enrich_contribution
from app.core.background import with_retry
from app.core.rate_limit import is_rate_limit_disabled
from app.core.templates import make_templates
from app.db.contribution_store import (
    count_submissions_since_by_ip_hash,
    create_contribution,
    has_pending_or_approved_duplicate_url,
    normalize_submission_url,
)
from app.db.database import SessionLocal, get_db
from app.schemas.contribution import ContributionCreate

router = APIRouter(tags=["contribute"])

templates = make_templates()

_MAX_NOTES = 2000

_RATE_MSG = "Thanks for your enthusiasm — please wait an hour between submissions."
_DUP_MSG = "We already have this in our review queue. Thanks though!"
_THIN_MSG = "Please add a short description or a URL — something so we know what this is about."
_SUCCESS_INTRO = (
    "Thanks! Your contribution is in our review queue. If you added an email, we'll come back to you "
    "if we have questions. Otherwise it'll show up in the catalog once approved."
)


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
    request: Request,
    *,
    submitted: bool = False,
    error_banner: str | None = None,
    field_errors: dict[str, str] | None = None,
    preserve: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the "Add to Hava" form on the v4 shell (v4.6: base_redesign, Jinja).

    Field ids/names, the ``/contribute`` action, and the entity-type toggle JS are
    preserved verbatim from the prior standalone page; Jinja autoescapes the
    preserved values. All call sites thread ``request`` for the shell globals.
    """
    p = preserve or {}
    return templates.TemplateResponse(
        request=request,
        name="contribute_redesign.html",
        context={
            "submitted": submitted,
            "error_banner": error_banner,
            "field_errors": field_errors or None,
            "ent": p.get("entity_type", "provider"),
            "p": p,
            "success_intro": _SUCCESS_INTRO,
            "max_notes": _MAX_NOTES,
        },
        status_code=status_code,
    )


_PREFILL_KINDS = frozenset({"provider", "program", "event", "tip"})


@router.get("/contribute", response_class=HTMLResponse, response_model=None)
def get_contribute(
    request: Request,
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
    return _render_contribute_page(request, submitted=bool(submitted), preserve=preserve or None)


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
        return _render_contribute_page(request, error_banner=_RATE_MSG, preserve=preserve, status_code=429)

    notes = (description or "").strip()
    if len(notes) > _MAX_NOTES:
        return _render_contribute_page(request,
            field_errors={"description": f"Please keep notes to {_MAX_NOTES} characters or fewer."},
            preserve=preserve,
        )

    url_s = (submission_url or "").strip()
    et = entity_type.strip().lower()
    if et not in ("provider", "program", "event", "tip"):
        return _render_contribute_page(request,
            field_errors={"entity_type": "Choose a valid submission type."},
            preserve=preserve,
        )
    if et in ("provider", "program") and not url_s:
        return _render_contribute_page(request,
            field_errors={"submission_url": "A URL is required for businesses and programs."},
            preserve=preserve,
        )

    if not url_s and not notes:
        return _render_contribute_page(request, error_banner=_THIN_MSG, preserve=preserve)

    norm_dup = normalize_submission_url(url_s if url_s else None)
    if norm_dup and has_pending_or_approved_duplicate_url(db, norm_dup):
        return _render_contribute_page(request, error_banner=_DUP_MSG, preserve=preserve)

    ev_d: date | None = None
    ev_st: time | None = None
    ev_en: time | None = None
    if et == "event":
        try:
            ev_d = _parse_optional_date(event_date)
            ev_st = _parse_optional_time(event_start_time)
            ev_en = _parse_optional_time(event_end_time)
        except ValueError:
            return _render_contribute_page(request,
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
            return _render_contribute_page(request, field_errors=ev_field_errors, preserve=preserve)

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
        return _render_contribute_page(request, field_errors=fe, preserve=preserve)

    row = create_contribution(db, body, submitter_ip_hash=_ip_hash(request))
    background_tasks.add_task(with_retry, enrich_contribution, row.id, SessionLocal)
    return RedirectResponse(url="/contribute?submitted=1", status_code=302)
