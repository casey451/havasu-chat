"""Admin HTML UI for operator event edits (Phase 9a)."""

from __future__ import annotations

import html
from datetime import date, time
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.auth import admin_guard as _guard
from app.admin.nav_html import admin_phase5_nav_html
from app.admin.url_safety import safe_href
from app.core.field_tracking import EVENT_TRACKED_FIELDS
from app.db.database import get_db
from app.db.models import Event, FieldHistory
from app.events.recurrence import parsed_until_from_rrule
from app.events.time_labels import is_time_tbd

# Vision/flyer sources whose events most often land without a real time (a human
# has to read the start off the flyer image). Surfaced FIRST in the "Missing time"
# review queue so the highest-value rows are at the top.
_VISION_SOURCES: frozenset[str] = frozenset(
    {"parks_rec_calendar", "parks_rec_flyers", "senior_center_flyers"}
)



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
        # ``?lock=1`` (from the Missing-time queue) pre-checks operator_override so
        # the human filling a missing time locks it against the next re-scrape with
        # no extra click. ``?flash=saved`` confirms a prior save.
        force_lock = request.query_params.get("lock") in {"1", "true", "yes", "on"}
        flash = request.query_params.get("flash") or ""
        return HTMLResponse(
            _render_edit_form(
                event, freq=freq, byday=byday, until=until, exdates=exdates,
                force_lock=force_lock, saved=(flash == "saved"),
                error=(flash == "bad_datetime"),
            )
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
        # Malformed date/time input (direct POST bypasses the form's client
        # validation) re-renders the edit form with a flash instead of a 500.
        try:
            event.date = date.fromisoformat(event_date.strip())
            event.start_time = time.fromisoformat(start_time.strip()[:8])
            event.end_time = (
                time.fromisoformat(end_time.strip()[:8]) if end_time.strip() else None
            )
        except ValueError:
            db.rollback()
            return RedirectResponse(
                url=f"/admin/events/{event_id}/edit?flash=bad_datetime", status_code=303
            )
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

    @router.get("/events/missing-times", response_class=HTMLResponse)
    def admin_events_missing_times(request: Request, db: Session = Depends(get_db)):
        """Review queue of live/pending events whose start time is unknown (they
        render "Time TBD"). Each row links to its source/flyer so a human can read
        the real start off the image, and to the edit form with the operator lock
        pre-checked. Filling the time drops the row off this list. Human-entry
        only — no time is ever fabricated here."""
        if redir := _guard(request):
            return redir
        source = (request.query_params.get("source") or "").strip()
        # "pending_review" is the actual status vocabulary (ck_events_status);
        # a bare "pending" matches nothing, which silently hid every
        # pending-review event with a TBD time from this queue.
        rows = (
            db.query(Event)
            .filter(Event.status.in_(("live", "pending_review")))
            .order_by(Event.date.asc())
            .all()
        )
        tbd = [e for e in rows if is_time_tbd(e.start_time, e.end_time)]
        if source:
            tbd = [e for e in tbd if (e.source or "") == source]
        # Vision/flyer sources first (highest-value), then by source then date.
        tbd.sort(
            key=lambda e: (
                0 if (e.source or "") in _VISION_SOURCES else 1,
                e.source or "",
                e.date,
            )
        )
        return HTMLResponse(_render_missing_times(tbd, source=source))


def _render_edit_form(
    event: Event,
    *,
    freq: str,
    byday: str,
    until: str,
    exdates: str,
    force_lock: bool = False,
    saved: bool = False,
    error: bool = False,
) -> str:
    flash = (
        '<p style="color:#1a7f37;font-weight:600">✓ Saved.</p>' if saved else ""
    )
    if error:
        flash = (
            '<p style="color:#b42318;font-weight:600">✗ Not saved — the date or'
            " time was not valid (date YYYY-MM-DD, time HH:MM).</p>"
        )
    nav = admin_phase5_nav_html()
    lock_checked = "checked" if (event.operator_override or force_lock) else ""
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


def _missing_time_row_html(ev: Event) -> str:
    flyer = ev.source_url or ev.event_url or ""
    flyer_cell = (
        # safe_href, not just _esc: these URLs come from scrapers and html.escape
        # does not neutralize javascript:/data: URL schemes.
        f'<a href="{_esc(safe_href(flyer))}" target="_blank" rel="noopener">flyer/source ↗</a>'
        if flyer
        else '<span style="color:#999">none</span>'
    )
    vision = (ev.source or "") in _VISION_SOURCES
    src_cell = (
        f'<span title="vision/flyer source">🖼️ {_esc(ev.source)}</span>'
        if vision
        else _esc(ev.source)
    )
    return f"""<tr>
  <td>{_esc(ev.title)}</td>
  <td>{_esc(ev.date.isoformat())}</td>
  <td>{_esc(ev.location_name or "")}</td>
  <td>{src_cell}</td>
  <td>{flyer_cell}</td>
  <td><a href="/admin/events/{_esc(ev.id)}/edit?lock=1">Set time →</a></td>
</tr>"""


def _render_missing_times(events: list[Event], *, source: str = "") -> str:
    nav = admin_phase5_nav_html()
    n_vision = sum(1 for e in events if (e.source or "") in _VISION_SOURCES)
    filt = f' · filtered to source <code>{_esc(source)}</code>' if source else ""
    if events:
        body = (
            "<table><thead><tr>"
            "<th>Title</th><th>Date</th><th>Venue</th><th>Source</th>"
            "<th>Flyer/source</th><th></th></tr></thead><tbody>"
            + "\n".join(_missing_time_row_html(e) for e in events)
            + "</tbody></table>"
        )
    else:
        body = '<p class="empty">No events are missing a start time. 🎉</p>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Missing event times</title>
<style>body{{font-family:system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%;margin-top:1rem}}
th,td{{border-bottom:1px solid #ddd;padding:0.4rem 0.5rem;text-align:left;font-size:0.9rem}}
th{{background:#f6f6f6}} .empty{{color:#666;margin-top:1.5rem}}
.sub{{color:#666}}</style></head><body>
{nav}
<h1>Missing event times</h1>
<p class="sub">{len(events)} event(s) render <strong>"Time TBD"</strong> — {n_vision} from
vision/flyer sources (shown first){filt}. Open the flyer, read the real start time,
and set it; the operator lock is pre-checked so the next re-scrape can't wipe it.
No time is ever auto-filled here.</p>
{body}
</body></html>"""
