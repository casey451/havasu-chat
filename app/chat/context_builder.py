"""Tier 3 context block from local catalog (Phase 3.2 — handoff §3.3 / §5).

Builds a plain-text context string capped at ~2000 tokens using a word budget
(``MAX_CONTEXT_WORDS``). Excludes draft providers, inactive programs, and past
events. Entity-matched provider (if any) is listed first with full detail.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.intent_classifier import IntentResult
from app.db.models import Event, Program, Provider

MAX_PROVIDERS = 10
MAX_CONTEXT_WORDS = 1500
_HOURS_MAX_LEN = 200


def _truncate_hours(h: str | None) -> str:
    if not h:
        return ""
    s = h.strip()
    if len(s) <= _HOURS_MAX_LEN:
        return s
    return s[: _HOURS_MAX_LEN - 3] + "..."


def _word_count(text: str) -> int:
    return len(text.split())


def _trim_to_word_budget(text: str, max_words: int) -> str:
    if _word_count(text) <= max_words:
        return text
    words = text.split()
    return " ".join(words[:max_words])


def _fetch_provider_rows(db: Session, entity: str | None) -> list[Provider]:
    """Active, non-draft providers; entity match first; max ``MAX_PROVIDERS``."""
    active = list(
        db.scalars(
            select(Provider).where(Provider.draft.is_(False), Provider.is_active.is_(True))
        ).all()
    )
    if not active:
        return list(
            db.scalars(
                select(Provider)
                .where(Provider.draft.is_(False), Provider.verified.is_(True))
                .order_by(Provider.provider_name.asc())
                .limit(MAX_PROVIDERS)
            ).all()
        )
    if entity:
        matched = [p for p in active if p.provider_name == entity]
        rest = [p for p in active if p.provider_name != entity]
        ordered: list[Provider] = matched + rest
    else:
        ordered = sorted(active, key=lambda p: (not p.verified, p.provider_name or ""))
    return ordered[:MAX_PROVIDERS]


def _programs_for(db: Session, provider_id: str) -> Sequence[Program]:
    return db.scalars(
        select(Program).where(Program.provider_id == provider_id, Program.is_active.is_(True))
    ).all()


def _events_future_for(db: Session, provider_id: str, today: date) -> Sequence[Event]:
    return db.scalars(
        select(Event)
        .where(
            Event.provider_id == provider_id,
            Event.status == "live",
            Event.date >= today,
        )
        .order_by(Event.date.asc(), Event.start_time.asc())
        .limit(8)
    ).all()


def build_context_for_tier3(query: str, intent_result: IntentResult, db: Session) -> str:
    """Return a plain-text context block for the Tier 3 system prompt (never empty)."""
    today = date.today()
    providers = _fetch_provider_rows(db, intent_result.entity)
    if not providers:
        return (
            "Context: No verified provider rows are available in the local catalog yet. "
            "Answer conservatively and do not invent businesses or events."
        )

    parts: list[str] = []
    parts.append("Context — Lake Havasu catalog snapshot (programs and events may be partial):")
    for p in providers:
        lines: list[str] = []
        lines.append(f"Provider: {p.provider_name}")
        lines.append(f"  category: {p.category}")
        if p.address:
            lines.append(f"  address: {p.address}")
        if p.phone:
            lines.append(f"  phone: {p.phone}")
        if p.website:
            lines.append(f"  website: {p.website}")
        hrs = _truncate_hours(p.hours)
        if hrs:
            lines.append(f"  hours: {hrs}")
        if p.verified:
            lines.append("  verified: yes")
        for prog in _programs_for(db, p.id):
            if prog.age_min is not None or prog.age_max is not None:
                ages = f"{prog.age_min if prog.age_min is not None else '?'}-{prog.age_max if prog.age_max is not None else '?'}"
            else:
                ages = "n/a"
            seg = (
                f"  Program: {prog.title} | ages {ages} | "
                f"schedule {prog.schedule_start_time}-{prog.schedule_end_time}"
            )
            if prog.cost:
                seg += f" | cost: {prog.cost}"
            if prog.schedule_note:
                sn = prog.schedule_note.strip()
                if len(sn) > 120:
                    sn = sn[:117] + "..."
                seg += f" | note: {sn}"
            lines.append(seg)
        for ev in _events_future_for(db, p.id, today):
            lines.append(
                f"  Upcoming event: {ev.title} on {ev.date.isoformat()} "
                f"at {ev.start_time.strftime('%H:%M')} — {ev.location_name}"
            )
        parts.append("\n".join(lines))

    body = "\n\n".join(parts)
    body = _trim_to_word_budget(body, MAX_CONTEXT_WORDS)
    return body
