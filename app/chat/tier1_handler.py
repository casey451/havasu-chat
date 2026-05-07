"""Tier 1 direct lookup glue (Phase 3.1 — handoff §3.3, §3.5, §8).

Resolves ``IntentResult`` + DB rows into a string via ``tier1_templates.render``,
or returns ``None`` to fall through to Tier 3.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.chat.normalizer import normalize
from app.chat.tier1_templates import CONTACT_FOR_PRICING, render
from app.contrib.hours_helper import (
    LAKE_HAVASU_TZ,
    is_open_at,
    places_hours_to_structured,
)
from app.core.timezone import now_lake_havasu
from app.db.models import Event, Program, Provider

_TIER1_SUB_INTENTS: frozenset[str] = frozenset(
    {
        "TIME_LOOKUP",
        "HOURS_LOOKUP",
        "PHONE_LOOKUP",
        "LOCATION_LOOKUP",
        "WEBSITE_LOOKUP",
        "COST_LOOKUP",
        "AGE_LOOKUP",
        "DATE_LOOKUP",
        "NEXT_OCCURRENCE",
        "OPEN_NOW",
        # Slice C — Google business retrieval
        "RATING_LOOKUP",
        "REVIEW_COUNT_LOOKUP",
    }
)


def _verified_suffix(provider: Provider) -> str:
    return " (confirmed)" if provider.verified else ""


def _append_voice(s: str, provider: Provider) -> str:
    base = (s or "").rstrip()
    return f"{base}{_verified_suffix(provider)}"


def _get_provider(db: Session, canonical_name: str) -> Provider | None:
    return db.scalars(select(Provider).where(Provider.provider_name == canonical_name)).first()


def _programs_for(db: Session, provider_id: str) -> list[Program]:
    return list(
        db.scalars(
            select(Program).where(Program.provider_id == provider_id, Program.is_active.is_(True))
        ).all()
    )


def _program_matching_query(programs: list[Program], normalized_query: str) -> Program | None:
    for p in programs:
        if p.title and normalize(p.title) in normalized_query:
            return p
    return None


def _primary_program(db: Session, provider: Provider, normalized_query: str) -> Program | None:
    programs = _programs_for(db, provider.id)
    if not programs:
        return None
    hit = _program_matching_query(programs, normalized_query)
    return hit or programs[0]


def _cost_program(db: Session, provider: Provider) -> Program | None:
    programs = _programs_for(db, provider.id)
    for p in programs:
        if p.cost and str(p.cost).strip():
            return p
    for p in programs:
        if p.show_pricing_cta:
            return p
    return None


def _age_program(db: Session, provider: Provider) -> Program | None:
    for p in _programs_for(db, provider.id):
        if p.age_min is not None or p.age_max is not None:
            return p
    return None


def _phone_for_query(db: Session, provider: Provider, normalized_query: str) -> str | None:
    programs = _programs_for(db, provider.id)
    hit = _program_matching_query(programs, normalized_query)
    if hit and hit.contact_phone and str(hit.contact_phone).strip():
        return str(hit.contact_phone).strip()
    if provider.phone and str(provider.phone).strip():
        return str(provider.phone).strip()
    for p in programs:
        if p.contact_phone and str(p.contact_phone).strip():
            return str(p.contact_phone).strip()
    return None


def _next_event(db: Session, provider: Provider) -> Event | None:
    today = now_lake_havasu().date()
    return db.scalars(
        select(Event)
        .where(
            Event.provider_id == provider.id,
            Event.status == "live",
            func.coalesce(Event.end_date, Event.date) >= today,
        )
        .order_by(Event.date.asc(), Event.start_time.asc())
        .limit(1)
    ).first()


def _clock_to_minutes(hour_12: int, minute: int, ampm: str) -> int:
    ap = ampm.lower()
    if ap == "am":
        h24 = 0 if hour_12 == 12 else hour_12
    else:
        h24 = 12 if hour_12 == 12 else hour_12 + 12
    return h24 * 60 + minute


def _hours_text_from_google(google_hours: dict | None) -> str | None:
    """Render ``google_hours.weekdayDescriptions`` as pipe-separated weekday rows.

    Google formats descriptions like ``"Monday: 9:00 AM – 5:00 PM"``. The colon after the
    weekday name confuses ``_first_token_weekday_index`` in tier1_templates (which expects
    the first token to be a bare weekday name), so we strip that one colon while leaving
    the rest of the string untouched. Returns ``None`` when descriptions are missing.

    Slice B (Google business retrieval): used as fallback when ``provider.hours`` is empty
    so HOURS_LOOKUP can still answer for Google-sourced rows.
    """
    if not isinstance(google_hours, dict):
        return None
    descriptions = google_hours.get("weekdayDescriptions")
    if not isinstance(descriptions, list) or not descriptions:
        return None
    cleaned: list[str] = []
    for d in descriptions:
        if not isinstance(d, str) or not d.strip():
            continue
        s = d.strip()
        # Only collapse a single ":" if it falls right after a single alpha word
        # (the weekday name). Time-of-day colons inside the description ("9:00") stay.
        head, sep, tail = s.partition(":")
        if sep and head.strip().isalpha() and (tail.startswith(" ") or tail == ""):
            cleaned.append(f"{head.strip()} {tail.strip()}".strip())
        else:
            cleaned.append(s)
    if not cleaned:
        return None
    return " | ".join(cleaned)


def _provider_hours_text(provider: Provider) -> str:
    """Hours string for templates: ``provider.hours`` first, ``google_hours`` fallback."""
    h = (provider.hours or "").strip()
    if h:
        return h
    return _hours_text_from_google(provider.google_hours) or ""


_PYTHON_WEEKDAY_TO_KEY: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _fmt_clock(hm: str) -> str:
    """``"09:00"`` → ``"9 AM"``; ``"17:30"`` → ``"5:30 PM"``; ``"00:00"`` → ``"12 AM"``."""
    if not isinstance(hm, str) or len(hm) != 5 or hm[2] != ":":
        return hm or ""
    try:
        h = int(hm[:2])
        m = int(hm[3:5])
    except ValueError:
        return hm
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    if m == 0:
        return f"{h12} {suffix}"
    return f"{h12}:{m:02d} {suffix}"


def _structured_for_provider(provider: Provider) -> dict | None:
    """Pick a non-empty weekday-segments dict for ``provider`` (Slice F1).

    Order: ``hours_structured`` (operator-curated) → ``places_hours_to_structured`` over
    ``google_hours`` (Google bulk import). Returns None when nothing parseable.
    """
    hs = provider.hours_structured
    if isinstance(hs, dict) and hs:
        return hs
    gh = provider.google_hours
    if isinstance(gh, dict):
        converted = places_hours_to_structured(gh)
        if converted:
            return converted
    return None


def _next_open_after(structured: dict, now_local: datetime) -> tuple[str, str, str] | None:
    """Return ``(day_label, open_clock, close_clock)`` for the next open segment, or None.

    Looks today (segments with open > now), then forward up to 6 days. ``day_label`` is
    ``"today"`` for same-day, ``"tomorrow"`` for the next calendar day, otherwise the
    capitalized weekday name (``"Monday"`` etc.).
    """
    cur_hm = f"{now_local.hour:02d}:{now_local.minute:02d}"
    today_key = _PYTHON_WEEKDAY_TO_KEY[now_local.weekday()]
    today_segs = structured.get(today_key) or []
    later_today = [
        s
        for s in today_segs
        if isinstance(s, dict)
        and isinstance(s.get("open"), str)
        and len(s.get("open", "")) == 5
        and s["open"] > cur_hm
    ]
    if later_today:
        seg = min(later_today, key=lambda s: s["open"])
        return ("today", str(seg["open"]), str(seg.get("close", "")))
    py_idx = now_local.weekday()
    for i in range(1, 7):
        next_idx = (py_idx + i) % 7
        key = _PYTHON_WEEKDAY_TO_KEY[next_idx]
        segs = structured.get(key) or []
        future = [
            s
            for s in segs
            if isinstance(s, dict) and isinstance(s.get("open"), str) and len(s.get("open", "")) == 5
        ]
        if future:
            seg = min(future, key=lambda s: s["open"])
            label = "tomorrow" if i == 1 else key.capitalize()
            return (label, str(seg["open"]), str(seg.get("close", "")))
    return None


def _current_segment_close(structured: dict, now_local: datetime) -> str | None:
    """If we're currently inside a segment today, return its close time (HH:MM); else None."""
    cur_hm = f"{now_local.hour:02d}:{now_local.minute:02d}"
    today_key = _PYTHON_WEEKDAY_TO_KEY[now_local.weekday()]
    for seg in structured.get(today_key) or []:
        if not isinstance(seg, dict):
            continue
        o = seg.get("open")
        c = seg.get("close")
        if isinstance(o, str) and isinstance(c, str) and len(o) == 5 and len(c) == 5:
            if o <= cur_hm <= c:
                return c
    return None


def _describe_open_state(provider: Provider, now: datetime) -> str | None:
    """Return a natural-voice open/closed message for ``provider`` at ``now``, or None.

    Slice F1 — replaces the sterile "in window for today" / "outside today's posted
    window" phrasings. Always includes either the current segment's close time (when
    open) or the next open boundary (when closed) so the user knows when to come back.
    """
    if now.tzinfo is None:
        local = now.replace(tzinfo=LAKE_HAVASU_TZ)
    else:
        local = now.astimezone(LAKE_HAVASU_TZ)

    structured = _structured_for_provider(provider)
    if structured:
        close_hm = _current_segment_close(structured, local)
        if close_hm is not None:
            return f"Open right now — until {_fmt_clock(close_hm)}."
        nxt = _next_open_after(structured, local)
        if nxt is not None:
            day_label, open_hm, close_hm = nxt
            window = (
                f"{_fmt_clock(open_hm)}–{_fmt_clock(close_hm)}"
                if close_hm
                else _fmt_clock(open_hm)
            )
            if day_label == "today":
                return f"Closed right now — opens at {_fmt_clock(open_hm)} today."
            if day_label == "tomorrow":
                return f"Closed today — open tomorrow {window}."
            return f"Closed today — open {day_label} {window}."
        return "Closed right now."

    free_text = (provider.hours or "").strip()
    if not free_text:
        return None
    state = _open_now_from_hours(free_text, local.replace(tzinfo=None))
    if state is True:
        # Try to extract close time from the free-text window.
        close = _free_text_close(free_text)
        if close:
            return f"Open right now — until {close}."
        return "Open right now."
    if state is False:
        opn = _free_text_open(free_text)
        if opn:
            cur_hm = f"{local.hour:02d}:{local.minute:02d}"
            opn_hm = _free_text_to_hm(opn)
            if opn_hm and cur_hm < opn_hm:
                return f"Closed right now — opens at {opn} today."
            return f"Closed right now — opens at {opn}."
        return "Closed right now."
    return None


def _free_text_close(hours: str) -> str | None:
    """Extract close-time clock string from a single-window free-text hours string."""
    m = re.search(
        r"(?P<o1>\d{1,2})(?::(?P<o2>\d{2}))?\s*(?P<oa>am|pm)\s*[-–]\s*"
        r"(?P<c1>\d{1,2})(?::(?P<c2>\d{2}))?\s*(?P<ca>am|pm)",
        hours,
        re.IGNORECASE,
    )
    if not m:
        return None
    c1 = int(m.group("c1"))
    c2 = int(m.group("c2") or 0)
    ca = m.group("ca").upper()
    if c2 == 0:
        return f"{c1} {ca}"
    return f"{c1}:{c2:02d} {ca}"


def _free_text_open(hours: str) -> str | None:
    m = re.search(
        r"(?P<o1>\d{1,2})(?::(?P<o2>\d{2}))?\s*(?P<oa>am|pm)\s*[-–]\s*"
        r"(?P<c1>\d{1,2})(?::(?P<c2>\d{2}))?\s*(?P<ca>am|pm)",
        hours,
        re.IGNORECASE,
    )
    if not m:
        return None
    o1 = int(m.group("o1"))
    o2 = int(m.group("o2") or 0)
    oa = m.group("oa").upper()
    if o2 == 0:
        return f"{o1} {oa}"
    return f"{o1}:{o2:02d} {oa}"


def _free_text_to_hm(clock: str) -> str | None:
    """``"9 AM"`` → ``"09:00"``; ``"5:30 PM"`` → ``"17:30"``."""
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$", clock.strip(), re.IGNORECASE)
    if not m:
        return None
    h = int(m.group(1))
    mm = int(m.group(2) or 0)
    ap = m.group(3).upper()
    if ap == "AM":
        h24 = 0 if h == 12 else h
    else:
        h24 = 12 if h == 12 else h + 12
    return f"{h24:02d}:{mm:02d}"


def _provider_open_now(provider: Provider, now: datetime) -> bool | None:
    """Return True/False if open-state is determinable for ``provider``; None otherwise.

    Tries ``provider.hours`` via :func:`_open_now_from_hours` first (existing path).
    Falls back to converting ``provider.google_hours`` (raw Google Places format) into
    the structured weekday dict via :func:`places_hours_to_structured` and checking with
    :func:`is_open_at`. The structured path correctly handles split-day windows
    (e.g. lunch + dinner) which the legacy regex parser cannot.
    """
    h = (provider.hours or "").strip()
    if h:
        state = _open_now_from_hours(h, now)
        if state is not None:
            return state
    gh = provider.google_hours
    if isinstance(gh, dict):
        structured = places_hours_to_structured(gh)
        if structured:
            return bool(is_open_at(structured, now))
    return None


def _open_now_from_hours(hours: str, now: datetime) -> bool | None:
    """Return True/False if parseable daily window; None if not parseable."""
    h = (hours or "").strip()
    if not h:
        return None
    low = h.lower()
    if "24/7" in low or "24 hour" in low or "all day" in low or "open 24" in low:
        return True

    m = re.search(
        r"(?P<o1>\d{1,2})(?::(?P<o2>\d{2}))?\s*(?P<oa>am|pm)\s*[-–]\s*"
        r"(?P<c1>\d{1,2})(?::(?P<c2>\d{2}))?\s*(?P<ca>am|pm)",
        h,
        re.IGNORECASE,
    )
    if not m:
        return None

    o1 = int(m.group("o1"))
    o2 = int(m.group("o2") or 0)
    oa = m.group("oa")
    c1 = int(m.group("c1"))
    c2 = int(m.group("c2") or 0)
    ca = m.group("ca")

    open_m = _clock_to_minutes(o1, o2, oa)
    close_m = _clock_to_minutes(c1, c2, ca)
    if close_m <= open_m:
        close_m += 24 * 60
    cur = now.hour * 60 + now.minute
    return open_m <= cur <= close_m


def try_tier1(query: str, intent_result: IntentResult, db: Session) -> str | None:
    """Return a Tier 1 response string, or ``None`` to fall through to Tier 3."""
    if intent_result.entity is None:
        return None
    sub = intent_result.sub_intent
    if sub not in _TIER1_SUB_INTENTS:
        return None

    provider = _get_provider(db, intent_result.entity)
    if provider is None:
        return None

    nq = intent_result.normalized_query or normalize(query)
    variant = 0

    if sub == "OPEN_NOW":
        # Slice F1: response always includes the relevant clock — current close time when
        # open, next-open boundary when closed — so the user knows when to come back.
        msg = _describe_open_state(provider, now_lake_havasu())
        if msg is None:
            return None
        return _append_voice(msg, provider)

    if sub in ("DATE_LOOKUP", "NEXT_OCCURRENCE"):
        ev = _next_event(db, provider)
        if ev is None:
            return None
        date_s = ev.date.isoformat()
        data: dict[str, Any] = {"program": ev.title, "date": date_s}
        out = render("DATE_LOOKUP", provider, data, variant=variant)
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "PHONE_LOOKUP":
        phone = _phone_for_query(db, provider, nq)
        if not phone:
            return None
        out = render("PHONE_LOOKUP", provider, {"phone": phone}, variant=variant)
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "LOCATION_LOOKUP":
        addr = (provider.address or "").strip()
        if not addr:
            return None
        out = render("LOCATION_LOOKUP", provider, {"address": addr}, variant=variant)
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "WEBSITE_LOOKUP":
        site = (provider.website or "").strip()
        if not site:
            return None
        out = render("WEBSITE_LOOKUP", provider, {"website": site}, variant=variant)
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "HOURS_LOOKUP":
        # Slice B: provider.hours first; fall back to google_hours.weekdayDescriptions for
        # Google-sourced rows that don't populate the legacy text column.
        hours = _provider_hours_text(provider)
        if not hours:
            return None
        out = render(
            "HOURS_LOOKUP",
            provider,
            {"hours": hours, "normalized_query": nq},
            variant=variant,
        )
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "TIME_LOOKUP":
        # Slice B: same hours fallback as HOURS_LOOKUP for Google providers; if no hours
        # (event-host providers without posted business hours) fall through to the program
        # schedule path below.
        hours = _provider_hours_text(provider)
        if hours:
            out = render(
                "HOURS_LOOKUP",
                provider,
                {"hours": hours, "normalized_query": nq},
                variant=variant,
            )
            if out is None:
                return None
            return _append_voice(out, provider)
        prog = _primary_program(db, provider, nq)
        if prog is None:
            return None
        # Slice 56 (Backlog #30 close): canonical schedule columns are typed
        # Time; strftime to HH:MM. ``st`` is required; ``et`` optional. The
        # None-guard on the start column survives from Slice 54 as cheap
        # resilience even though the column is now nullable=False.
        st_typed = prog.schedule_start_time
        et_typed = prog.schedule_end_time
        if st_typed is None:
            return None
        st = st_typed.strftime("%H:%M")
        et = et_typed.strftime("%H:%M") if et_typed is not None else ""
        window = f"{st}–{et}" if et else st
        out = render(
            "TIME_LOOKUP",
            provider,
            {"program": prog.title, "time": window},
            variant=variant,
        )
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "COST_LOOKUP":
        prog = _cost_program(db, provider)
        if prog is None:
            return None
        cost_val: str | None
        if prog.cost and str(prog.cost).strip():
            cost_val = str(prog.cost).strip()
        elif prog.show_pricing_cta:
            cost_val = CONTACT_FOR_PRICING
        else:
            return None
        phone = (prog.contact_phone or provider.phone or "").strip()
        data = {"program": prog.title, "cost": cost_val, "phone": phone}
        out = render("COST_LOOKUP", prog, data, variant=variant)
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "AGE_LOOKUP":
        prog = _age_program(db, provider)
        if prog is None:
            return None
        lo, hi = prog.age_min, prog.age_max
        if lo is None and hi is None:
            return None
        if lo is not None and hi is not None:
            ar = f"{lo}–{hi}"
        elif lo is not None:
            ar = f"{lo}+"
        else:
            ar = f"up to {hi}"
        out = render("AGE_LOOKUP", prog, {"program": prog.title, "age_range": ar}, variant=variant)
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "RATING_LOOKUP":
        # Slice C: Google rating + review count lives directly on the Provider row
        # (google_rating, google_review_count). Format rating to 1 decimal so "4.6 stars"
        # reads naturally and we don't expose float artifacts like 4.5999999.
        rating = provider.google_rating
        if rating is None:
            return None
        rc_int = provider.google_review_count or 0
        rating_str = f"{float(rating):.1f}"
        data: dict[str, Any] = {"rating": rating_str, "review_count": rc_int}
        out = render("RATING_LOOKUP", provider, data, variant=variant)
        if out is None:
            return None
        return _append_voice(out, provider)

    if sub == "REVIEW_COUNT_LOOKUP":
        # Slice C: review-count-only intent. Distinct from RATING_LOOKUP — sometimes the
        # user wants the volume signal alone ("how many reviews does X have").
        rc = provider.google_review_count
        if rc is None or rc == 0:
            return None
        out = render(
            "REVIEW_COUNT_LOOKUP",
            provider,
            {"review_count": int(rc)},
            variant=variant,
        )
        if out is None:
            return None
        return _append_voice(out, provider)

    return None
