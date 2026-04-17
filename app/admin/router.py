from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import asc
from sqlalchemy.orm import Session

from app.admin.auth import (
    COOKIE_NAME,
    MAX_AGE_SECONDS,
    admin_password_ok,
    sign_admin_cookie,
    verify_admin_cookie,
)
from app.db.database import get_db
from app.db.models import Event
from app.db.seed import run_seed

router = APIRouter(prefix="/admin", tags=["admin"])


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%b %d, %Y %I:%M %p")


def _countdown(admin_review_by: datetime | None) -> str:
    if not admin_review_by:
        return "—"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end = admin_review_by
    if end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    sec = (end - now).total_seconds()
    if sec <= 0:
        return "Overdue"
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    if h >= 48:
        d = int(sec // 86400)
        return f"{d} days left"
    if h > 0:
        return f"{h} hours left"
    if m > 0:
        return f"{m} minutes left"
    return "Under a minute left"


def _escape(s: str | None) -> str:
    if s is None:
        return "—"
    return html.escape(s, quote=True)


def _login_html(error: bool = False) -> str:
    err = (
        '<p class="err">That password does not match. Try again.</p>'
        if error
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Admin login</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #f8f9fa; color: #212529; }}
    .box {{ max-width: 400px; margin: 40px auto; background: #fff; padding: 28px; border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    h1 {{ font-size: 1.25rem; margin: 0 0 8px; }}
    p {{ color: #6c757d; font-size: 0.95rem; margin: 0 0 20px; }}
    label {{ display: block; font-weight: 600; margin-bottom: 8px; }}
    input[type=password] {{ width: 100%; padding: 14px 16px; font-size: 1.05rem; border: 1px solid #dee2e6;
      border-radius: 10px; min-height: 48px; }}
    button {{ margin-top: 16px; width: 100%; padding: 14px 20px; font-size: 1.05rem; font-weight: 600;
      border: none; border-radius: 10px; background: #0d6efd; color: #fff; min-height: 48px; cursor: pointer; }}
    .err {{ color: #b02a37; font-weight: 500; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>Admin</h1>
    <p>Enter the admin password to continue.</p>
    {err}
    <form method="post" action="/admin/login">
      <label for="pw">Password</label>
      <input id="pw" name="password" type="password" autocomplete="current-password" required />
      <button type="submit">Sign in</button>
    </form>
  </div>
</body>
</html>"""


def _dashboard_html_simple(pending: list[Event], live: list[Event], tab: str) -> str:
    if tab == "live":
        body_inner = "\n".join(_card_html(e, "live") for e in live) or '<p class="empty">No live events.</p>'
        title = "Live events"
    else:
        body_inner = "\n".join(_card_html(e, "pending") for e in pending) or '<p class="empty">No events pending review.</p>'
        title = "Pending review"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Admin — {title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #212529;
      line-height: 1.45; padding-bottom: 48px; }}
    header {{ max-width: 720px; margin: 0 auto 16px; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 4px; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; }}
    .tabs {{ display: flex; gap: 8px; max-width: 720px; margin: 0 auto 16px; flex-wrap: wrap; }}
    .tabs a {{
      flex: 1; min-width: 140px; text-align: center; padding: 14px 16px; border-radius: 10px;
      text-decoration: none; font-weight: 600; border: 2px solid #dee2e6; color: #495057; background: #f8f9fa;
      min-height: 48px; display: flex; align-items: center; justify-content: center;
    }}
    .tabs a.active {{ border-color: #0d6efd; background: #e7f1ff; color: #0a58ca; }}
    .panel {{ max-width: 720px; margin: 0 auto; }}
    .card {{ border: 1px solid #e9ecef; border-radius: 12px; padding: 16px; margin-bottom: 14px; background: #fafafa; }}
    .card h3 {{ margin: 0 0 8px; font-size: 1.1rem; }}
    .meta {{ margin: 6px 0; font-size: 0.92rem; color: #495057; word-break: break-word; }}
    .label {{ color: #868e96; font-weight: 600; margin-right: 6px; }}
    .desc {{ white-space: pre-wrap; margin: 10px 0; }}
    .actions {{ margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap; }}
    .btn {{ min-height: 48px; min-width: 120px; padding: 12px 18px; font-size: 1rem; font-weight: 600;
      border: none; border-radius: 10px; cursor: pointer; }}
    .btn.ok {{ background: #198754; color: #fff; }}
    .btn.bad {{ background: #dc3545; color: #fff; }}
    .empty {{ color: #6c757d; padding: 24px; text-align: center; }}
    a {{ color: #0d6efd; }}
  </style>
</head>
<body>
  <header>
    <h1>Events</h1>
    <p class="sub">{title}</p>
  </header>
  <nav class="tabs">
    <a class="{('active' if tab != 'live' else '')}" href="/admin?tab=pending">Pending review</a>
    <a class="{('active' if tab == 'live' else '')}" href="/admin?tab=live">Live events</a>
  </nav>
  <div class="panel">
    {body_inner}
  </div>
</body>
</html>"""


def _card_html(ev: Event, mode: Literal["pending", "live"]) -> str:
    url = (ev.event_url or "").strip()
    link = (
        f'<a href="{_escape(url)}" target="_blank" rel="noopener">{_escape(url)}</a>'
        if url
        else "—"
    )
    if mode == "pending":
        actions = f"""
      <form method="post" action="/admin/event/{_escape(ev.id)}/approve" style="display:inline">
        <button type="submit" class="btn ok">Approve</button>
      </form>
      <form method="post" action="/admin/event/{_escape(ev.id)}/reject" style="display:inline">
        <button type="submit" class="btn bad">Reject</button>
      </form>"""
        cd = _countdown(ev.admin_review_by)
        cd_row = f'<p class="meta"><span class="label">Deadline</span> {_fmt_dt(ev.admin_review_by)} · <strong>{_escape(cd)}</strong></p>'
    else:
        actions = f"""
      <form method="post" action="/admin/event/{_escape(ev.id)}/delete" style="display:inline"
            onsubmit="return confirm('Delete this event?');">
        <button type="submit" class="btn bad">Delete</button>
      </form>"""
        cd_row = ""

    return f"""
    <article class="card">
      <h3>{_escape(ev.title)}</h3>
      {cd_row}
      <p class="meta"><span class="label">When</span> {_escape(ev.date.isoformat())} · {_escape(ev.start_time.isoformat())}</p>
      <p class="meta"><span class="label">Where</span> {_escape(ev.location_name)}</p>
      <p class="desc">{_escape(ev.description)}</p>
      <p class="meta"><span class="label">Link</span> {link}</p>
      <p class="meta"><span class="label">Contact</span> {_escape(ev.contact_name)} · {_escape(ev.contact_phone)}</p>
      <p class="meta"><span class="label">Submitted</span> {_fmt_dt(ev.created_at)}</p>
      <div class="actions">{actions}</div>
    </article>"""


@router.get("/login", response_class=HTMLResponse)
def admin_login_page() -> HTMLResponse:
    return HTMLResponse(_login_html(error=False))


@router.post("/login", response_model=None)
def admin_login_submit(
    request: Request,
    password: str = Form(...),
) -> RedirectResponse | HTMLResponse:
    if not admin_password_ok(password.strip()):
        return HTMLResponse(_login_html(error=True), status_code=401)
    resp = RedirectResponse(url="/admin?tab=pending", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        sign_admin_cookie(),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("", response_class=HTMLResponse, response_model=None)
@router.get("/", response_class=HTMLResponse, response_model=None)
def admin_dashboard(
    request: Request,
    tab: str = "pending",
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    if tab not in ("pending", "live"):
        tab = "pending"

    pending = (
        db.query(Event)
        .filter(Event.status == "pending_review")
        .order_by(asc(Event.admin_review_by))
        .all()
    )
    live = db.query(Event).filter(Event.status == "live").order_by(asc(Event.date), asc(Event.start_time)).all()

    return HTMLResponse(_dashboard_html_simple(pending, live, tab))


def _apply_status(event_id: str, db: Session, status: str) -> None:
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    ev.status = status
    db.commit()


@router.post("/event/{event_id}/approve", response_model=None)
def admin_approve(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    _apply_status(event_id, db, "live")
    return RedirectResponse(url="/admin?tab=pending", status_code=303)


@router.post("/event/{event_id}/reject", response_model=None)
def admin_reject(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    _apply_status(event_id, db, "deleted")
    return RedirectResponse(url="/admin?tab=pending", status_code=303)


@router.post("/event/{event_id}/delete", response_model=None)
def admin_delete(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    _apply_status(event_id, db, "deleted")
    return RedirectResponse(url="/admin?tab=live", status_code=303)


class AdminReviewBody(BaseModel):
    action: Literal["approve", "reject"]


@router.post("/review/{event_id}")
def admin_review_json(
    request: Request,
    event_id: str,
    body: AdminReviewBody,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """JSON API for tests / integrations — requires admin cookie."""
    redir = _guard(request)
    if redir:
        raise HTTPException(status_code=401, detail="Not authenticated")
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if body.action == "approve":
        event.status = "live"
    else:
        event.status = "deleted"
    db.commit()
    db.refresh(event)
    return {"id": event.id, "status": event.status}


@router.post("/reseed")
def admin_reseed(request: Request, db: Session = Depends(get_db)) -> dict[str, int]:
    """One-time ops: remove seed rows and re-insert with fresh embeddings (admin cookie)."""
    redir = _guard(request)
    if redir:
        raise HTTPException(status_code=401, detail="Not authenticated")
    deleted = db.query(Event).filter(Event.created_by == "seed").delete(synchronize_session=False)
    db.commit()
    inserted, skipped = run_seed(skip_init=True)
    return {"deleted": deleted, "inserted": inserted, "skipped": skipped}
