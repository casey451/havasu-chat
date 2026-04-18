"""Program search + response formatting (Session Z-2).

Program search is additive — it runs when the query looks like a
how-to-start/ongoing-class question rather than a dated event lookup.
Shares synonym expansion with event search but keeps its own scoring
because program rows carry different fields (schedule_days, age range,
provider, cost) than event rows.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.conversation_copy import PROGRAMS_INTRO, PROGRAMS_NONE
from app.core.slots import expand_query_synonyms
from app.db.models import Program

_STOP_TOKENS = frozenset(
    {
        "the",
        "a",
        "an",
        "for",
        "and",
        "with",
        "any",
        "some",
        "where",
        "can",
        "how",
        "what",
        "when",
        "who",
        "that",
        "this",
        "there",
        "here",
        "near",
        "from",
        "my",
        "our",
        "your",
        "about",
        "into",
        "kid",
        "kids",
        "child",
        "children",
        "year",
        "years",
        "yr",
        "yrs",
        "old",
        "daughter",
        "son",
        "signup",
        "sign",
        "up",
    }
)

_DAY_ORDER = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _extract_age_from_query(message: str) -> int | None:
    """Parse an integer age from phrases like 'for my 8 year old' or 'for 6 year olds'."""
    lowered = message.lower()
    m = re.search(r"\b(\d{1,2})\s*(?:year|yr|yo)s?\s*old", lowered)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d{1,2})\s*yrs?\b", lowered)
    if m:
        return int(m.group(1))
    m = re.search(r"\bfor\s+(?:my\s+|a\s+)?(\d{1,2})\b", lowered)
    if m:
        return int(m.group(1))
    return None


def _query_tokens(message: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[a-z0-9]+", message.lower())
        if len(t) > 2 and t not in _STOP_TOKENS
    ]


def _program_text_blob(program: Program) -> str:
    parts = [
        (program.title or "").lower(),
        (program.description or "").lower(),
        (program.activity_category or "").lower(),
        " ".join(str(t).lower() for t in (program.tags or [])),
    ]
    return " ".join(parts)


def _score_program(program: Program, tokens: list[str], synonyms: list[str]) -> float:
    blob = _program_text_blob(program)
    if not blob.strip():
        return 0.0
    matched = 0
    for t in tokens:
        if t in blob:
            matched += 1
    synonym_bonus = 0
    for s in synonyms:
        if s.lower() in blob:
            synonym_bonus += 1
    if tokens:
        base = matched / len(tokens)
    else:
        base = 0.0
    return base + 0.1 * synonym_bonus


def search_programs(
    db: Session,
    message: str,
    slots: dict[str, Any] | None = None,
) -> list[Program]:
    """Return active programs relevant to ``message``, ordered by relevance."""
    tokens = _query_tokens(message)
    synonyms = expand_query_synonyms(message)

    programs: list[Program] = (
        db.query(Program).filter(Program.is_active.is_(True)).all()
    )

    age = _extract_age_from_query(message)
    if age is not None:
        programs = [
            p
            for p in programs
            if (p.age_min is None or p.age_min <= age)
            and (p.age_max is None or p.age_max >= age)
        ]

    if not tokens and not synonyms:
        return programs

    scored: list[tuple[Program, float]] = []
    for p in programs:
        s = _score_program(p, tokens, synonyms)
        if s > 0:
            scored.append((p, s))
    scored.sort(key=lambda pair: (-pair[1], (pair[0].title or "").lower()))
    return [p for p, _ in scored]


def _format_days(days: list[str]) -> str:
    if not days:
        return "schedule TBD"
    ordered = sorted(
        {d.lower() for d in days if isinstance(d, str)},
        key=lambda d: _DAY_ORDER.index(d) if d in _DAY_ORDER else 99,
    )
    labels = [d.capitalize() for d in ordered]
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} & {labels[1]}"
    return ", ".join(labels[:-1]) + f" & {labels[-1]}"


def _format_hhmm(hhmm: str) -> str:
    try:
        h, m = (hhmm or "").split(":")
        hour = int(h)
        minute = int(m)
    except ValueError:
        return hhmm or ""
    ampm = "AM" if hour < 12 else "PM"
    h12 = hour % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{minute:02d} {ampm}"


def _format_age_range(p: Program) -> str | None:
    if p.age_min is None and p.age_max is None:
        return None
    if p.age_min is not None and p.age_max is not None:
        return f"Ages {p.age_min}–{p.age_max}"
    if p.age_min is not None:
        return f"Ages {p.age_min}+"
    return f"Up to age {p.age_max}"


def _format_cost(p: Program) -> str | None:
    cost = (p.cost or "").strip()
    return cost or None


def _program_card(p: Program) -> str:
    days = _format_days(list(p.schedule_days or []))
    when = (
        f"Every {days} • {_format_hhmm(p.schedule_start_time)} – "
        f"{_format_hhmm(p.schedule_end_time)}"
    )
    lines = [
        f"🗓 {when}",
        p.title,
    ]
    meta_bits = [x for x in (_format_age_range(p), _format_cost(p)) if x]
    if meta_bits:
        lines.append(" • ".join(meta_bits))
    lines.append(f"📍 {p.location_name}")
    lines.append(f"🏫 {p.provider_name}")
    desc = (p.description or "").strip()
    if desc:
        lines.append("")
        lines.append(desc)
    contact_bits = [
        x
        for x in (p.contact_phone, p.contact_email, p.contact_url)
        if x and x.strip()
    ]
    if contact_bits:
        lines.append("")
        lines.append("📞 " + " • ".join(contact_bits))
    return "\n".join(lines)


def format_program_results(programs: list[Program]) -> str:
    if not programs:
        return PROGRAMS_NONE
    display = programs[:5]
    parts = [PROGRAMS_INTRO, ""]
    for p in display:
        parts.append(_program_card(p))
        parts.append("")
    body = "\n".join(parts).rstrip()
    remaining = len(programs) - len(display)
    if remaining > 0:
        body += f"\n\n…and {remaining} more — tell me an age or day to narrow."
    return body
