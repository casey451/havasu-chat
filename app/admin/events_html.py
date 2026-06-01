"""Admin HTML UI for operator event edits (Phase 9a)."""

from __future__ import annotations

import html
from datetime import date, time
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.admin.nav_html import admin_phase5_nav_html
from app.core.field_tracking import EVENT_TRACKED_FIELDS
from app.db.database import get_db
from app.db.models import Event, FieldHistory
from app.events.recurrence import parsed_until_from_rrule


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _build_rrule(freq: str, byday: str, until: str) -> str | None:
    freq = (freq or "").strip().upper()
    if not freq or freq == "NONE":
        return None
    parts = [f"FREQ={freq}"]
    if byday.strip():
        parts.append(f"BYDAY={byday.strip().upper()}")
    if until.strip():
        d = date.fromisoformat(until.strip())
        parts.append(f"UNTIL={d.strftime('%Y%m%d')}T000000Z")
    return ";".join(parts)


def _parse_rrule_form(rrule: str | None) -> tuple[str, str, str]:
    """Best-effort split for form repopulation."""
    if not rrule:
        return ("NONE", "", "")
    freq = "WEEKLY"
    byday = ""
    until = ""
    for part in rrule.split(";"):
        if part.upper().startswith("FREQ="):
            freq = part.split("=", 1)[1].upper()
        elif part.upper().startswith("BYDAY="):
            byday = part.split("=", 1)[1]
        elif part.upper().startswith("UNTIL="):
            u = parsed_until_from_rrule(part)
            if u:
                until = u.isoformat()
    return (freq, byday, until)


def _record_field_changes(
    db: Session,
    event: Event,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    source: str,
) -> None:
    for field in EVENT_TRACKED_FIELDS:
        old_v = before.get(field)
        new_v = after.get(field)
        if old_v == new_v:
            continue
        db.add(
            FieldHistory(
                entity_type="event",
                entity_id=event.id,
                field_name=field,
                old_value=None if old_v is None else str(old_v),
                new_value=None if new_v is None else str(new_v),
                source=source,
                state="confirmed",
            )
        )


def register_events_html_routes(router: APIRouter) -> None:
    @router.get("/events/{event_id}/edit", response_class=HTMLResponse)
    def admin_event_edit_form(event_id: str, request: Request, db: Session = Depends(get_db)):
        if redir := _guard(request):
            return redir
        event = db.get(Event, event_id)
        if event is None:
            return HTMLResponse("<p>Event not found.</p>", status_code=404)
        freq, byday, until = _parse_rrule_form(event.rrule)
        exdates = ", ".join(event.exdate or [])
        return HTMLResponse(
            _render_edit_form(event, freq=freq, byday=byday, until=until, exdates=exdates)
        )

    @router.post("/events/{event_id}/edit")
    def admin_event_edit_save(
        event_id: str,
        request: Request,
        db: Session = Depends(get_db),
        title: str = Form(...),
        event_date: str = Form(..., alias="date"),
        start_time: str = Form(...),
        end_time: str = Form(""),
        description: str = Form(""),
        status: str = Form("live"),
        cancellation_reason: str = Form(""),
        rrule_freq: str = Form("NONE"),
        rrule_byday: str = Form(""),
        rrule_until: str = Form(""),
        exdate_raw: str = Form(""),
        operator_override: str = Form(""),
    ) -> RedirectResponse:
        if redir := _guard(request):
            return redir
        event = db.get(Event, event_id)
        if event is None:
            return RedirectResponse(url="/admin/contributions", status_code=303)

        before = {
            "date": event.date,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "location_name": event.location_name,
        }
        event.title = title.strip()
        event.normalized_title = event.title.lower()
        event.date = date.fromisoformat(event_date.strip())
        event.start_time = time.fromisoformat(start_time.strip()[:8])
        event.end_time = time.fromisoformat(end_time.strip()[:8]) if end_time.strip() else None
        event.description = description.strip()
        event.status = status.strip() or "live"
        event.cancellation_reason = (
            cancellation_reason.strip() if event.status == "cancelled" else None
        )
        new_rrule = _build_rrule(rrule_freq, rrule_byday, rrule_until)
        event.rrule = new_rrule
        event.is_recurring = bool(new_rrule or event.rdate)
        ex_list = [x.strip()[:10] for x in exdate_raw.replace("\n", ",").split(",") if x.strip()]
        event.exdate = ex_list or None
        event.operator_override = operator_override.strip().lower() in {
            "1",
            "true",
            "on",
            "yes",
        }
        after = {
            "date": event.date,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "location_name": event.location_name,
        }
        _record_field_changes(db, event, before=before, after=after, source="operator")
        db.commit()
        return RedirectResponse(url=f"/admin/events/{event_id}/edit?flash=saved", status_code=303)


def _render_edit_form(
    event: Event,
    *,
    freq: str,
    byday: str,
    until: str,
    exdates: str,
) -> str:
    flash = ""
    nav = admin_phase5_nav_html()
    lock_checked = "checked" if event.operator_override else ""
    cancelled_sel = "selected" if event.status == "cancelled" else ""
    live_sel = "selected" if event.status != "cancelled" else ""
    end_t = event.end_time.strftime("%H:%M") if event.end_time else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Edit event</title>
<style>body{{font-family:system-ui;max-width:720px;margin:2rem auto;padding:0 1rem}}
label{{display:block;margin-top:1rem;font-weight:600}} input,textarea,select{{width:100%;padding:0.4rem}}
.btn{{margin-top:1.5rem;padding:0.5rem 1rem}}</style></head><body>
{nav}
<h1>Edit event</h1>
<p class="sub">Source: {_esc(event.source)} · entity {_esc(event.entity_id[:8])}…</p>
{flash}
<form method="post" action="/admin/events/{_esc(event.id)}/edit">
<label>Title <input name="title" value="{_esc(event.title)}" required></label>
<label>Date <input type="date" name="date" value="{event.date.isoformat()}" required></label>
<label>Start time <input type="time" name="start_time" value="{event.start_time.strftime("%H:%M")}" required></label>
<label>End time <input type="time" name="end_time" value="{end_t}"></label>
<label>Description <textarea name="description" rows="4">{_esc(event.description)}</textarea></label>
<label>Recurrence frequency
<select name="rrule_freq">
<option value="NONE"{" selected" if freq == "NONE" else ""}>None</option>
<option value="DAILY"{" selected" if freq == "DAILY" else ""}>Daily</option>
<option value="WEEKLY"{" selected" if freq == "WEEKLY" else ""}>Weekly</option>
<option value="MONTHLY"{" selected" if freq == "MONTHLY" else ""}>Monthly</option>
</select></label>
<label>BYDAY (e.g. TU,FR) <input name="rrule_byday" value="{_esc(byday)}"></label>
<label>UNTIL <input type="date" name="rrule_until" value="{_esc(until)}"></label>
<label>EXDATE (comma-separated ISO dates) <input name="exdate_raw" value="{_esc(exdates)}"></label>
<label>Status
<select name="status">
<option value="live" {live_sel}>Live</option>
<option value="cancelled" {cancelled_sel}>Cancelled</option>
</select></label>
<label>Cancellation reason <textarea name="cancellation_reason" rows="2">{_esc(event.cancellation_reason or "")}</textarea></label>
<label><input type="checkbox" name="operator_override" value="1" {lock_checked}> Lock my edits (operator_override)</label>
<button class="btn" type="submit">Save</button>
<a href="/admin/contributions" style="margin-left:1rem">Cancel</a>
</form>
<p style="margin-top:2rem"><small>RRULE stored: {_esc(event.rrule or "(none)")}</small></p>
</body></html>"""
