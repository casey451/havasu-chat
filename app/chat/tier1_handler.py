"""Tier 1 direct lookup glue (Phase 3.1 — handoff §3.3, §3.5, §8).

Resolves ``IntentResult`` + DB rows into a string via ``tier1_templates.render``,
or returns ``None`` to fall through to Tier 3.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.chat.normalizer import normalize
from app.chat.tier1_templates import CONTACT_FOR_PRICING, render
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
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    today = _utcnow().date()
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
        h = (provider.hours or "").strip()
        if not h:
            return None
        now = _utcnow().astimezone(UTC).replace(tzinfo=None)
        state = _open_now_from_hours(h, now)
        if state is None:
            return None
        if state:
            msg = "They're open right now — hours say they're in window for today."
        else:
            msg = "They're closed right now — outside today's posted window."
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
        hours = (provider.hours or "").strip()
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
        hours = (provider.hours or "").strip()
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
        st = (prog.schedule_start_time or "").strip()
        et = (prog.schedule_end_time or "").strip()
        if not st:
            return None
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

    return None
