"""Public feedback form at ``/feedback`` (P5, §2.4).

GET renders the form (prefillable via query params from the per-page "Report
wrong or missing info" controls); POST persists a row, fires one operator
notification in the background, and PRG-redirects with a success flag.

Rate limiting is in-memory and keyed on a hashed IP that is **never persisted**
(the ``Feedback`` table stores no IP/UA/user-id), keeping the channel as
anonymized as ``QueryLog``.
"""

from __future__ import annotations

import hashlib
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.provider_name import register_template_filters, register_template_globals
from app.core.rate_limit import is_rate_limit_disabled
from app.db.database import SessionLocal, get_db
from app.db.models import Feedback
from app.feedback.store import VALID_KINDS, create_feedback, notify_feedback

router = APIRouter(tags=["feedback"])

_templates = Jinja2Templates(directory="app/templates")
# Match the other page routers: register the shared filters (clean_name) +
# globals (static_url, plausible_domain) so base_lake/desert_base render.
register_template_filters(_templates)
register_template_globals(_templates)

_MAX_MESSAGE = 4000
_RATE_WINDOW_SECONDS = 60.0
# Process-local throttle: hashed-IP -> last submit monotonic time. Bounded by
# eviction on each call so it can't grow without limit.
_last_submit: dict[str, float] = {}


def _ip_hash(request: Request) -> str:
    return hashlib.sha256((get_remote_address(request) or "").encode("utf-8")).hexdigest()


def _rate_limited(request: Request) -> bool:
    if is_rate_limit_disabled():
        return False
    now = time.monotonic()
    # Evict stale entries so the dict stays small.
    for key, ts in list(_last_submit.items()):
        if now - ts > _RATE_WINDOW_SECONDS:
            _last_submit.pop(key, None)
    h = _ip_hash(request)
    if h in _last_submit:
        return True
    _last_submit[h] = now
    return False


def _theme(request: Request) -> str:
    return getattr(request.state, "theme", "lake") or "lake"


def _template_name(request: Request) -> str:
    return "feedback_lake.html" if _theme(request) == "lake" else "feedback.html"


@router.get("/feedback", response_class=HTMLResponse, response_model=None)
def feedback_form(
    request: Request,
    type: str = "",
    target_type: str = "",
    ref: str = "",
    name: str = "",
    submitted: int = 0,
) -> HTMLResponse:
    """Render the feedback form, prefilled from the per-page report controls."""
    kind = type if type in VALID_KINDS else "general"
    return _templates.TemplateResponse(
        request,
        _template_name(request),
        {
            "kind": kind,
            "target_type": target_type or "",
            "target_ref": ref or "",
            "subject_name": name or "",
            "submitted": bool(submitted),
            "error": None,
        },
    )


@router.post("/feedback", response_class=HTMLResponse, response_model=None)
def post_feedback(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    message: str = Form(...),
    kind: str = Form("general"),
    target_type: str = Form(""),
    target_ref: str = Form(""),
    email: str = Form(""),
    page_url: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    """Persist feedback, forward it to the operator, and redirect on success."""
    msg = (message or "").strip()
    if not msg:
        return _templates.TemplateResponse(
            request,
            _template_name(request),
            {
                "kind": kind if kind in VALID_KINDS else "general",
                "target_type": target_type,
                "target_ref": target_ref,
                "subject_name": "",
                "submitted": False,
                "error": "Please tell us what's wrong or missing so we can fix it.",
            },
            status_code=400,
        )
    if _rate_limited(request):
        return _templates.TemplateResponse(
            request,
            _template_name(request),
            {
                "kind": kind if kind in VALID_KINDS else "general",
                "target_type": target_type,
                "target_ref": target_ref,
                "subject_name": "",
                "submitted": False,
                "error": "Thanks — please wait a moment before sending more feedback.",
            },
            status_code=429,
        )

    row = create_feedback(
        db,
        kind=kind,
        message=msg[:_MAX_MESSAGE],
        target_type=target_type or None,
        target_ref=target_ref or None,
        page_url=page_url or None,
        email=email or None,
    )
    # Forward in the background so a Resend hiccup never blocks the submit. Use a
    # fresh session-bound row id so the request's session can close cleanly.
    background_tasks.add_task(_notify_in_background, row.id)
    return RedirectResponse(url="/feedback?submitted=1", status_code=302)


def _notify_in_background(feedback_id: int) -> None:
    with SessionLocal() as db:
        row = db.get(Feedback, feedback_id)
        if row is not None:
            notify_feedback(row)
