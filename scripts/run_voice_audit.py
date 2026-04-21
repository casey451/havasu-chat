"""Phase 6.1.2 — voice audit runner (Tier 1 matrix + Tier 3 via ``route`` + reference §8 goldens).

Standalone script under ``scripts/`` (not imported by the app). Enumerates samples,
optionally calls Anthropic Haiku once per sample for ``prompts/voice_audit.txt``.

**Seed / data gap (6.1.3 report):** If ``DATE_LOOKUP`` or ``NEXT_OCCURRENCE`` rows log
``branch_present_not_auditable`` because no future live event exists for any seeded
``Event.provider_id``, treat that as a **seed/data gap** worth a follow-up line in the
voice audit delivery report — handoff §1b calls ``NEXT_OCCURRENENCE`` a Tier 1 branch
that fires in production; missing local audit coverage is not proof of a code bug.

**Scope fence:** Do not edit ``tier1_templates.py``, ``tier3_handler.py``,
``unified_router.py``, or ``prompts/`` from this runner.

Usage:
  .venv\\Scripts\\python.exe scripts/run_voice_audit.py              # default: --dry-run
  .venv\\Scripts\\python.exe scripts/run_voice_audit.py --dry-run
  .venv\\Scripts\\python.exe scripts/run_voice_audit.py --execute --confirm [--yes]

Environment:
  ``ANTHROPIC_API_KEY`` — required for ``--execute``.
  ``DATABASE_URL`` — optional; defaults per ``app.db.database``.

This sub-phase stops at building the runner and ``--dry-run`` proof; a full paid audit
run is 6.1.3 unless explicitly approved.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.chat.intent_classifier import IntentResult  # noqa: E402
from app.chat.normalizer import normalize  # noqa: E402
from app.chat.tier1_handler import (  # noqa: E402
    _open_now_from_hours,
    _utcnow,
    try_tier1,
)
from app.chat.unified_router import route  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event, Program, Provider  # noqa: E402

# Claude Haiku 4.5 list pricing (USD per 1M tokens) — rounded; verify against Anthropic pricing.
_HAIKU_1M_INPUT_USD = 1.0
_HAIKU_1M_OUTPUT_USD = 5.0

_AUDIT_MODEL = "claude-haiku-4-5-20251001"
_AUDIT_MAX_TOKENS = 300
_AUDIT_TEMPERATURE = 0.25

# Order-of-magnitude token estimates for dry-run costing (when usage is unknown).
_EST_AUDIT_IN = 900
_EST_AUDIT_OUT = 280
_EST_TIER3_IN = 7500
_EST_TIER3_OUT = 220

_HARD_CEILING_USD = 2.0

_TIER3_QUERIES: list[tuple[str, list[str]]] = [
    ("What's happening this weekend?", ["happy_path"]),
    ("What time does the BMX track open Saturday?", ["happy_path"]),
    ("When is the farmers market on Thursday?", ["happy_path"]),
    ("Is Altitude open late on Friday?", ["happy_path"]),
    ("Kids gymnastics programs near me", ["happy_path"]),
    ("Tell me about Bridge City Combat", ["happy_path"]),
    ("Events at Sara Park", ["happy_path"]),
    ("BMX race times", ["happy_path"]),
    ("Swimming lessons for beginners", ["happy_path"]),
    ("Dance classes for a 7-year-old", ["happy_path"]),
    ("My son wants to ride mountain bikes. Any classes available?", ["gap"]),
    ("Is there a curling club in Havasu?", ["gap"]),
    ("When is the hot air balloon festival?", ["gap"]),
    ("Who teaches violin to adults?", ["gap"]),
    ("Underground techno tonight?", ["gap"]),
    ("Sonics or Flips for fun for a shy 5-year-old?", ["multi_entity", "disambiguation"]),
    (
        "Bridge City Combat vs Footlite School of Dance for Saturday morning kids classes?",
        ["multi_entity", "disambiguation"],
    ),
    ("Which martial arts gym has Saturday morning kids classes?", ["multi_entity", "disambiguation"]),
    ("Best place for toddler tumbling", ["multi_entity", "explicit_rec_query"]),
    ("Compare Footlite and Ballet Havasu for preschool dance", ["multi_entity", "disambiguation"]),
    ("What's the best sushi in town?", ["out_of_scope"]),
    ("Are home prices going down in Havasu?", ["out_of_scope"]),
    ("Weather this weekend?", ["out_of_scope"]),
    ("What should I do Saturday?", ["explicit_rec_query"]),
    ("Pick one thing to do with kids this weekend", ["explicit_rec_query"]),
]

_REFERENCE_SAMPLES: list[dict[str, Any]] = [
    {
        "sample_id": "ref-8.5-low",
        "tier": "reference",
        "intent_or_mode": "§8.5 low-stakes contested-state",
        "user_query": "(contested hours — no live user query)",
        "assistant_text": (
            "Opens at 7 — someone recently reported it moved from 6. Let me know if that's wrong."
        ),
        "tags": ["contested_state"],
    },
    {
        "sample_id": "ref-8.5-high",
        "tier": "reference",
        "intent_or_mode": "§8.5 high-stakes contested-state",
        "user_query": "(contested phone — no live user query)",
        "assistant_text": (
            "My info says the phone is (928) 555-0100. Someone recently reported a different number — "
            "I'll get it confirmed before updating."
        ),
        "tags": ["contested_state"],
    },
    {
        "sample_id": "ref-8.8-intake",
        "tier": "reference",
        "intent_or_mode": "§8.8 intake",
        "user_query": "there's a car show at the channel saturday",
        "assistant_text": "nice — got a time, and who's running it?",
        "tags": ["intake"],
    },
    {
        "sample_id": "ref-8.8-commit",
        "tier": "reference",
        "intent_or_mode": "§8.8 commit",
        "user_query": "Casey I just submitted a car show event",
        "assistant_text": (
            "got it, added to the pile. Casey reviews new events before they go live — "
            "usually within a day or two."
        ),
        "tags": ["intake"],
    },
    {
        "sample_id": "ref-8.9-correction-low",
        "tier": "reference",
        "intent_or_mode": "§8.9 correction low-stakes",
        "user_query": "(user corrected a small catalog fact)",
        "assistant_text": "got it, noted — I'll flag it and watch for more confirmations.",
        "tags": ["correction"],
    },
    {
        "sample_id": "ref-8.9-high",
        "tier": "reference",
        "intent_or_mode": "§8.9 correction high-stakes",
        "user_query": "Altitude's phone isn't (928) 555-0100 anymore — it's a different number now",
        "assistant_text": (
            "got it — that one needs to go through review before I update it. Thanks for the heads up."
        ),
        "tags": ["correction"],
    },
]


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()[:40]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _token_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1_000_000.0) * _HAIKU_1M_INPUT_USD
        + (output_tokens / 1_000_000.0) * _HAIKU_1M_OUTPUT_USD
    )


def _count_future_events_null_provider(db: Session, today: date) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Event)
            .where(
                Event.status == "live",
                Event.date >= today,
                Event.provider_id.is_(None),
            )
        )
        or 0
    )


def _first_provider_where(db: Session, *conditions: Any) -> Provider | None:
    return db.scalars(select(Provider).where(*conditions).limit(1)).first()


def _programs_active(db: Session, provider_id: str) -> list[Program]:
    return list(
        db.scalars(
            select(Program).where(Program.provider_id == provider_id, Program.is_active.is_(True))
        ).all()
    )


def _append_not_auditable(
    out: list[dict[str, Any]],
    sample_id: str,
    sub_intent: str,
    detail: str,
) -> None:
    out.append(
        {
            "sample_id": sample_id,
            "sub_intent": sub_intent,
            "log": "branch_present_not_auditable — branch present, not auditable with current seed — "
            "possible dead code or data gap.",
            "detail": detail,
        }
    )


def _mk_ir(
    *,
    sub_intent: str,
    entity: str,
    raw_query: str,
) -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent=sub_intent,
        confidence=0.9,
        entity=entity,
        raw_query=raw_query,
        normalized_query=normalize(raw_query),
    )


def _slug_matrix(s: str) -> str:
    x = re.sub(r"[^a-z0-9]+", "-", (s or "").lower())[:48].strip("-")
    return x or "prov"


def discover_tier1_matrix(db: Session) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (auditable_payloads, not_auditable_rows) for the Tier 1 voice matrix.

    The proposal matrix lists **multiple seeded entities** for several sub-intents (e.g. two
    LOCATION targets, WEBSITE matrix attempts including a row that may be not-auditable
    when ``website`` is missing). The **~25–40** Tier 1 band is an upper bound over thin
    and rich seeds; a **fully linked local seed** often lands in the **~18–28** range for
    successful renders plus explicit ``branch_present_not_auditable`` rows for matrix
    cells the catalog cannot exercise.
    """
    auditable: list[dict[str, Any]] = []
    not_auditable: list[dict[str, Any]] = []
    today = _utcnow().date()

    # --- HOURS_LOOKUP (up to 3 providers with hours; prefer matrix names when present) ---
    all_hours = list(
        db.scalars(
            select(Provider).where(
                Provider.hours.is_not(None),
                func.length(func.trim(Provider.hours)) > 0,
            )
        ).all()
    )

    def _hours_sort_key(p: Provider) -> tuple[int, int, str]:
        name = (p.provider_name or "").lower()
        hints = ("footlite", "altitude", "iron wolf")
        for i, h in enumerate(hints):
            if h in name:
                return (0, i, p.provider_name)
        return (1, 99, p.provider_name)

    all_hours.sort(key=_hours_sort_key)
    hours_providers = all_hours[:3]
    if not hours_providers:
        _append_not_auditable(
            not_auditable,
            "t1-HOURS_LOOKUP",
            "HOURS_LOOKUP",
            "no provider with non-empty hours",
        )
    else:
        for i, p in enumerate(hours_providers, start=1):
            q = f"What are {p.provider_name} hours on Monday?"
            ir = _mk_ir(sub_intent="HOURS_LOOKUP", entity=p.provider_name, raw_query=q)
            text = try_tier1(q, ir, db)
            if not text:
                _append_not_auditable(
                    not_auditable,
                    f"t1-HOURS_LOOKUP-{i}",
                    "HOURS_LOOKUP",
                    f"try_tier1 returned None for provider={p.provider_name!r}",
                )
                continue
            auditable.append(
                {
                    "sample_id": f"t1-HOURS-{i:02d}",
                    "tier": "tier1",
                    "intent_or_mode": "HOURS_LOOKUP",
                    "user_query": q,
                    "assistant_text": text,
                    "tags": ["tier1_matrix"],
                    "matrix_note": f"provider={p.provider_name}",
                }
            )

    # --- TIME_LOOKUP (hours path): proposal matrix names **Altitude** for hours path ---
    hp = _first_provider_where(
        db,
        Provider.provider_name.like("%Altitude%Trampoline%"),
        Provider.hours.is_not(None),
        func.length(func.trim(Provider.hours)) > 0,
    )
    if hp is None:
        hp = _first_provider_where(
            db, Provider.hours.is_not(None), func.length(func.trim(Provider.hours)) > 0
        )
    if hp is None:
        _append_not_auditable(
            not_auditable,
            "t1-TIME-hours",
            "TIME_LOOKUP",
            "no provider with hours for TIME_LOOKUP hours render path",
        )
    else:
        q = f"What time does {hp.provider_name} open on Tuesday?"
        ir = _mk_ir(sub_intent="TIME_LOOKUP", entity=hp.provider_name, raw_query=q)
        text = try_tier1(q, ir, db)
        if not text:
            _append_not_auditable(
                not_auditable,
                "t1-TIME-hours",
                "TIME_LOOKUP",
                f"hours path failed for provider={hp.provider_name!r}",
            )
        else:
            auditable.append(
                {
                    "sample_id": "t1-TIME-hours",
                    "tier": "tier1",
                    "intent_or_mode": "TIME_LOOKUP",
                    "user_query": q,
                    "assistant_text": text,
                    "tags": ["tier1_matrix"],
                    "matrix_note": (
                        "render path: HOURS_LOOKUP via TIME_LOOKUP; "
                        f"matrix prefers Altitude, actual provider={hp.provider_name!r}"
                    ),
                }
            )

    # --- TIME_LOOKUP (program schedule path): provider with no hours, program with start time ---
    prog_path: tuple[Provider, Program, str] | None = None
    for p in db.scalars(select(Provider)).all():
        if (p.hours or "").strip():
            continue
        for pr in _programs_active(db, p.id):
            if (pr.schedule_start_time or "").strip():
                q = (
                    f"What time is {pr.title} at {p.provider_name} — schedule window"
                )
                prog_path = (p, pr, q)
                break
        if prog_path:
            break
    if prog_path is None:
        _append_not_auditable(
            not_auditable,
            "t1-TIME-program",
            "TIME_LOOKUP",
            "no provider without hours + active program with schedule_start_time",
        )
    else:
        p, _pr, q = prog_path
        ir = _mk_ir(sub_intent="TIME_LOOKUP", entity=p.provider_name, raw_query=q)
        text = try_tier1(q, ir, db)
        if not text:
            _append_not_auditable(
                not_auditable,
                "t1-TIME-program",
                "TIME_LOOKUP",
                f"program schedule path failed for provider={p.provider_name!r}",
            )
        else:
            auditable.append(
                {
                    "sample_id": "t1-TIME-program",
                    "tier": "tier1",
                    "intent_or_mode": "TIME_LOOKUP",
                    "user_query": q,
                    "assistant_text": text,
                    "tags": ["tier1_matrix"],
                    "matrix_note": (
                        "render path: TIME_LOOKUP program window (provider without hours + "
                        "schedule_start_time — may differ from proposal's Altitude example when "
                        "Altitude has hours and always hits the hours branch)"
                    ),
                }
            )

    # --- PHONE_LOOKUP (up to 3 providers with resolvable phone via try_tier1) ---
    phone_candidates = [
        "Footlite School of Dance",
        "Bridge City Combat",
        "Flips for Fun Gymnastics",
    ]
    phone_found = 0
    for name in phone_candidates:
        p = _first_provider_where(db, Provider.provider_name == name)
        if not p:
            continue
        q = f"What is the phone number for {name}?"
        ir = _mk_ir(sub_intent="PHONE_LOOKUP", entity=name, raw_query=q)
        text = try_tier1(q, ir, db)
        if not text:
            continue
        phone_found += 1
        auditable.append(
            {
                "sample_id": f"t1-PHONE-{phone_found:02d}",
                "tier": "tier1",
                "intent_or_mode": "PHONE_LOOKUP",
                "user_query": q,
                "assistant_text": text,
                "tags": ["tier1_matrix"],
                "matrix_note": f"provider={name}",
            }
        )
    if phone_found == 0:
        _append_not_auditable(
            not_auditable,
            "t1-PHONE",
            "PHONE_LOOKUP",
            "no phone resolvable for Footlite / Bridge City Combat / Flips for Fun",
        )

    # --- LOCATION_LOOKUP (matrix: Iron Wolf + Altitude — up to two auditable rows) ---
    loc_specs: list[tuple[str, str]] = [
        ("t1-LOCATION-iron-wolf", "Iron Wolf Golf & Country Club"),
        ("t1-LOCATION-altitude", "__ALTITUDE_LIKE__"),
    ]
    for sid, spec in loc_specs:
        if spec == "__ALTITUDE_LIKE__":
            loc = _first_provider_where(
                db,
                Provider.provider_name.like("%Altitude%Trampoline%"),
                Provider.address.is_not(None),
                func.length(func.trim(Provider.address)) > 0,
            )
        else:
            loc = _first_provider_where(
                db,
                Provider.provider_name == spec,
                Provider.address.is_not(None),
                func.length(func.trim(Provider.address)) > 0,
            )
        if not loc:
            _append_not_auditable(
                not_auditable,
                sid,
                "LOCATION_LOOKUP",
                f"matrix target {spec!r}: no provider row with non-empty address",
            )
            continue
        q = f"Where is {loc.provider_name} located?"
        ir = _mk_ir(sub_intent="LOCATION_LOOKUP", entity=loc.provider_name, raw_query=q)
        text = try_tier1(q, ir, db)
        if not text:
            _append_not_auditable(
                not_auditable,
                sid,
                "LOCATION_LOOKUP",
                f"try_tier1 None for provider={loc.provider_name!r}",
            )
        else:
            auditable.append(
                {
                    "sample_id": sid,
                    "tier": "tier1",
                    "intent_or_mode": "LOCATION_LOOKUP",
                    "user_query": q,
                    "assistant_text": text,
                    "tags": ["tier1_matrix"],
                    "matrix_note": f"matrix entity={loc.provider_name}",
                }
            )

    # --- WEBSITE_LOOKUP (matrix: Bridge City Combat + Altitude — log not-auditable per missing website) ---
    web_specs: list[tuple[str, str]] = [
        ("t1-WEBSITE-bridge-city-combat", "Bridge City Combat"),
        ("t1-WEBSITE-altitude", "__ALTITUDE_LIKE__"),
    ]
    any_website = False
    for sid, spec in web_specs:
        if spec == "__ALTITUDE_LIKE__":
            webp = _first_provider_where(
                db,
                Provider.provider_name.like("%Altitude%Trampoline%"),
                Provider.website.is_not(None),
                func.length(func.trim(Provider.website)) > 0,
            )
        else:
            webp = _first_provider_where(db, Provider.provider_name == spec)
        if not webp:
            _append_not_auditable(
                not_auditable,
                sid,
                "WEBSITE_LOOKUP",
                f"matrix target {spec!r}: provider row not found",
            )
            continue
        site = (webp.website or "").strip()
        if not site:
            _append_not_auditable(
                not_auditable,
                sid,
                "WEBSITE_LOOKUP",
                f"matrix target {webp.provider_name!r}: empty website (seed-dependent)",
            )
            continue
        any_website = True
        q = f"What is the website for {webp.provider_name}?"
        ir = _mk_ir(sub_intent="WEBSITE_LOOKUP", entity=webp.provider_name, raw_query=q)
        text = try_tier1(q, ir, db)
        if not text:
            _append_not_auditable(
                not_auditable,
                sid,
                "WEBSITE_LOOKUP",
                f"try_tier1 None for provider={webp.provider_name!r}",
            )
        else:
            auditable.append(
                {
                    "sample_id": sid,
                    "tier": "tier1",
                    "intent_or_mode": "WEBSITE_LOOKUP",
                    "user_query": q,
                    "assistant_text": text,
                    "tags": ["tier1_matrix"],
                    "matrix_note": f"matrix entity={webp.provider_name}",
                }
            )
    if not any_website:
        _append_not_auditable(
            not_auditable,
            "t1-WEBSITE",
            "WEBSITE_LOOKUP",
            "no matrix WEBSITE target rendered (all candidates missing website or lookup failed)",
        )

    # --- COST_LOOKUP (two distinct providers if possible) ---
    cost_specs: list[tuple[str, str]] = []
    alt = _first_provider_where(db, Provider.provider_name.like("%Altitude%Trampoline%"))
    if alt:
        cost_specs.append((alt.provider_name, "How much is Open Jump at Altitude?"))
    iw = _first_provider_where(db, Provider.provider_name == "Iron Wolf Golf & Country Club")
    if iw:
        cost_specs.append((iw.provider_name, "How much is the Junior Golf Clinic at Iron Wolf?"))
    cost_n = 0
    for prov_name, q in cost_specs:
        p = _first_provider_where(db, Provider.provider_name == prov_name)
        if not p:
            continue
        ir = _mk_ir(sub_intent="COST_LOOKUP", entity=prov_name, raw_query=q)
        text = try_tier1(q, ir, db)
        if not text:
            continue
        cost_n += 1
        auditable.append(
            {
                "sample_id": f"t1-COST-{cost_n:02d}",
                "tier": "tier1",
                "intent_or_mode": "COST_LOOKUP",
                "user_query": q,
                "assistant_text": text,
                "tags": ["tier1_matrix"],
            }
        )
    if cost_n == 0:
        _append_not_auditable(
            not_auditable,
            "t1-COST",
            "COST_LOOKUP",
            "no COST_LOOKUP render for Altitude / Iron Wolf matrix rows",
        )

    # --- AGE_LOOKUP (matrix: Flips + Universal/Sonics + one more distinct provider when present) ---
    def _first_age_query_for_provider(p: Provider) -> tuple[str, str] | None:
        for pr in _programs_active(db, p.id):
            if pr.age_min is None and pr.age_max is None:
                continue
            q = f"What ages is {pr.title} at {p.provider_name}?"
            return p.provider_name, q
        return None

    age_order_names: list[str] = []
    seen_age_names: set[str] = set()

    def _push_age_provider(p: Provider | None) -> None:
        if not p or p.provider_name in seen_age_names:
            return
        if not _first_age_query_for_provider(p):
            return
        age_order_names.append(p.provider_name)
        seen_age_names.add(p.provider_name)

    _push_age_provider(_first_provider_where(db, Provider.provider_name == "Flips for Fun Gymnastics"))
    _push_age_provider(
        db.scalars(
            select(Provider)
            .where(
                func.lower(Provider.provider_name).like("%sonics%"),
                func.lower(Provider.provider_name).like("%universal%"),
            )
            .limit(1)
        ).first()
    )
    for p in db.scalars(select(Provider).order_by(Provider.provider_name.asc())).all():
        if len(age_order_names) >= 3:
            break
        _push_age_provider(p)

    age_rows: list[tuple[str, str, str]] = []
    for pname in age_order_names:
        p = _first_provider_where(db, Provider.provider_name == pname)
        if not p:
            continue
        hit = _first_age_query_for_provider(p)
        if not hit:
            continue
        prov_name, q = hit
        slug = _slug_matrix(pname)
        age_rows.append((slug, prov_name, q))

    if len(age_rows) < 2:
        _append_not_auditable(
            not_auditable,
            "t1-AGE",
            "AGE_LOOKUP",
            "fewer than two providers with active programs carrying age_min/age_max in seed",
        )
    else:
        for slug, prov_name, q in age_rows[:3]:
            ir = _mk_ir(sub_intent="AGE_LOOKUP", entity=prov_name, raw_query=q)
            text = try_tier1(q, ir, db)
            sid = f"t1-AGE-{slug}"
            if not text:
                _append_not_auditable(
                    not_auditable,
                    sid,
                    "AGE_LOOKUP",
                    f"try_tier1 None for query={q!r}",
                )
                continue
            auditable.append(
                {
                    "sample_id": sid,
                    "tier": "tier1",
                    "intent_or_mode": "AGE_LOOKUP",
                    "user_query": q,
                    "assistant_text": text,
                    "tags": ["tier1_matrix"],
                    "matrix_note": f"provider={prov_name}",
                }
            )

    # --- DATE_LOOKUP + NEXT_OCCURRENCE (two classifier labels; repeat for up to two providers) ---
    date_providers: list[Provider] = []
    for p in db.scalars(select(Provider)).all():
        ev = db.scalars(
            select(Event)
            .where(
                Event.provider_id == p.id,
                Event.status == "live",
                Event.date >= today,
            )
            .order_by(Event.date.asc(), Event.start_time.asc())
            .limit(1)
        ).first()
        if ev:
            date_providers.append(p)
        if len(date_providers) >= 2:
            break
    if not date_providers:
        _append_not_auditable(
            not_auditable,
            "t1-DATE",
            "DATE_LOOKUP",
            "no future live Event rows linked to a provider_id — seed gap vs handoff §1b NEXT_OCCURRENCE",
        )
        _append_not_auditable(
            not_auditable,
            "t1-NEXT",
            "NEXT_OCCURRENCE",
            "same as DATE_LOOKUP — no auditable future provider-linked event",
        )
    else:
        for pi, dp in enumerate(date_providers[:2], start=1):
            slug = _slug_matrix(dp.provider_name)
            q_date = f"When is the next event for {dp.provider_name}?"
            for sub, abbr in (("DATE_LOOKUP", "DATE"), ("NEXT_OCCURRENCE", "NEXT")):
                sid = f"t1-{abbr}" if pi == 1 else f"t1-{abbr}-p{pi}"
                ir = _mk_ir(sub_intent=sub, entity=dp.provider_name, raw_query=q_date)
                text = try_tier1(q_date, ir, db)
                if not text:
                    _append_not_auditable(
                        not_auditable,
                        sid,
                        sub,
                        f"try_tier1 None for provider={dp.provider_name!r}",
                    )
                    continue
                auditable.append(
                    {
                        "sample_id": sid,
                        "tier": "tier1",
                        "intent_or_mode": sub,
                        "user_query": q_date,
                        "assistant_text": text,
                        "tags": ["tier1_matrix"],
                        "matrix_note": f"provider={dp.provider_name} slug={slug}",
                    }
                )

    # --- OPEN_NOW (up to four providers with parseable hours — Altitude preferred first) ---
    now = _utcnow().astimezone(UTC).replace(tzinfo=None)
    open_candidates: list[Provider] = []
    for p in db.scalars(select(Provider)).all():
        h = (p.hours or "").strip()
        if not h:
            continue
        if _open_now_from_hours(h, now) is None:
            continue
        open_candidates.append(p)

    def _open_sort_key(p: Provider) -> tuple[int, str]:
        n = (p.provider_name or "").lower()
        return (0 if "altitude" in n else 1, p.provider_name)

    open_candidates.sort(key=_open_sort_key)
    open_candidates = open_candidates[:4]
    if not open_candidates:
        _append_not_auditable(
            not_auditable,
            "t1-OPEN_NOW",
            "OPEN_NOW",
            "no provider hours matched OPEN_NOW regex / parser",
        )
    else:
        for p in open_candidates:
            slug = _slug_matrix(p.provider_name)
            sid = f"t1-OPEN_NOW-{slug}"
            q = f"Is {p.provider_name} open right now?"
            ir = _mk_ir(sub_intent="OPEN_NOW", entity=p.provider_name, raw_query=q)
            text = try_tier1(q, ir, db)
            if not text:
                _append_not_auditable(
                    not_auditable,
                    sid,
                    "OPEN_NOW",
                    f"try_tier1 None for provider={p.provider_name!r}",
                )
                continue
            auditable.append(
                {
                    "sample_id": sid,
                    "tier": "tier1",
                    "intent_or_mode": "OPEN_NOW",
                    "user_query": q,
                    "assistant_text": text,
                    "tags": ["tier1_matrix"],
                    "matrix_note": f"provider={p.provider_name}",
                }
            )

    return auditable, not_auditable


def build_tier3_payloads(db: Session) -> list[dict[str, Any]]:
    sid = f"voice-audit-tier3-{uuid.uuid4().hex[:12]}"
    out: list[dict[str, Any]] = []
    for i, (q, tags) in enumerate(_TIER3_QUERIES, start=1):
        resp = route(q, sid, db)
        out.append(
            {
                "sample_id": f"t3-{i:02d}",
                "tier": "tier3",
                "intent_or_mode": f"ask/{resp.sub_intent or 'none'}",
                "user_query": q,
                "assistant_text": resp.response,
                "tags": tags,
                "route_meta": {
                    "mode": resp.mode,
                    "sub_intent": resp.sub_intent,
                    "entity": resp.entity,
                    "tier_used": resp.tier_used,
                    "latency_ms": resp.latency_ms,
                    "llm_tokens_used": resp.llm_tokens_used,
                    "llm_input_tokens": resp.llm_input_tokens,
                    "llm_output_tokens": resp.llm_output_tokens,
                },
            }
        )
    return out


def _load_voice_audit_system() -> str:
    path = _ROOT / "prompts" / "voice_audit.txt"
    return path.read_text(encoding="utf-8").strip()


def _parse_audit_json(text: str) -> dict[str, Any] | None:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        return None
    return None


def _run_voice_audits(samples: Iterable[dict[str, Any]], client: Any) -> list[dict[str, Any]]:
    system = _load_voice_audit_system()
    results: list[dict[str, Any]] = []
    for sample in samples:
        sid = sample["sample_id"]
        user_payload = {k: v for k, v in sample.items() if k != "route_meta"}
        body = json.dumps(user_payload, ensure_ascii=False)
        msg = client.messages.create(
            model=_AUDIT_MODEL,
            max_tokens=_AUDIT_MAX_TOKENS,
            temperature=_AUDIT_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": body}],
        )
        raw = ""
        for block in getattr(msg, "content", None) or []:
            if getattr(block, "type", None) == "text":
                raw += getattr(block, "text", "") or ""
        parsed = _parse_audit_json(raw)
        if parsed is None:
            msg2 = client.messages.create(
                model=_AUDIT_MODEL,
                max_tokens=_AUDIT_MAX_TOKENS,
                temperature=_AUDIT_TEMPERATURE,
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": body + "\n\nYour previous reply was not valid JSON. Reply with one JSON object only.",
                    }
                ],
            )
            raw2 = ""
            for block in getattr(msg2, "content", None) or []:
                if getattr(block, "type", None) == "text":
                    raw2 += getattr(block, "text", "") or ""
            parsed = _parse_audit_json(raw2)
            raw = raw + "\n--- retry ---\n" + raw2
        if parsed is None:
            results.append(
                {
                    "sample_id": sid,
                    "verdict": "ERROR",
                    "voice_rules_cited": [],
                    "summary": "Auditor JSON parse failed after one retry.",
                    "suggested_rewrite": None,
                    "notes": raw[:8000],
                    "input": user_payload,
                }
            )
        else:
            results.append({**parsed, "_raw_auditor_response": raw[:4000]})
    return results


def _estimate_plan_cost_usd(
    n_tier1_auditable: int,
    n_tier3: int,
    n_reference: int,
    *,
    assume_all_tier3_hits_llm: bool,
) -> tuple[float, int, int]:
    n_audit = n_tier1_auditable + n_tier3 + n_reference
    audit_in = n_audit * _EST_AUDIT_IN
    audit_out = n_audit * _EST_AUDIT_OUT
    tier3_in = (n_tier3 * _EST_TIER3_IN) if assume_all_tier3_hits_llm else 0
    tier3_out = (n_tier3 * _EST_TIER3_OUT) if assume_all_tier3_hits_llm else 0
    usd = _token_cost_usd(audit_in + tier3_in, audit_out + tier3_out)
    return usd, audit_in + tier3_in, audit_out + tier3_out


def _configure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _print_dry_run(
    tier1_ok: list[dict[str, Any]],
    tier1_skip: list[dict[str, Any]],
    est_usd: float,
    tot_in: int,
    tot_out: int,
    future_null_prov: int,
) -> None:
    n_t3 = len(_TIER3_QUERIES)
    n_ref = len(_REFERENCE_SAMPLES)
    print("=== Voice audit runner — dry run ===")
    print(f"git_sha: {_git_sha() or '(unavailable)'}")
    print()
    print("--- Tier 1 matrix (auditable) — full enumeration ---")
    for s in tier1_ok:
        print(f"--- {s['sample_id']} ---")
        print(f"  intent_or_mode: {s['intent_or_mode']}")
        print(f"  user_query: {s['user_query']}")
        if s.get("matrix_note"):
            print(f"  matrix_note: {s['matrix_note']}")
        at = (s.get("assistant_text") or "").replace("\r\n", "\n")
        print(f"  assistant_text: {at}")
        print()
    print(f"Tier 1 auditable count: {len(tier1_ok)}")
    print()
    print("--- Tier 1 matrix (branch_present_not_auditable) ---")
    if not tier1_skip:
        print("  (none)")
    for row in tier1_skip:
        print(f"  {row['sample_id']} [{row['sub_intent']}]")
        print(f"    {row.get('log', '')}")
        print(f"    detail: {row.get('detail', '')}")
    print(f"Tier 1 not-auditable rows: {len(tier1_skip)}")
    print()
    print("--- Tier 3 generated (unified_router.route) — queries only in dry-run ---")
    print(
        "  Note: dry-run does not call route() (would invoke Tier 2/3 LLMs). "
        "assistant_text is omitted here; use --execute to materialize Tier 3 responses."
    )
    for i, (q, tags) in enumerate(_TIER3_QUERIES, start=1):
        tgs = ",".join(tags)
        print(f"--- t3-{i:02d} ---")
        print(f"  tags: [{tgs}]")
        print(f"  user_query: {q}")
        print()
    print(f"Tier 3 count: {n_t3}")
    print()
    print("--- Reference (frozen §8 goldens) — full enumeration ---")
    for r in _REFERENCE_SAMPLES:
        print(f"--- {r['sample_id']} ---")
        print(f"  intent_or_mode: {r['intent_or_mode']}")
        print(f"  user_query: {r['user_query']}")
        print(f"  assistant_text: {r['assistant_text']}")
        tags = r.get("tags") or []
        print(f"  tags: {tags}")
        print()
    print(f"Reference count: {n_ref}")
    print()
    n_audit = len(tier1_ok) + n_t3 + n_ref
    print("--- Cost estimate (Haiku 4.5 @ $1/M input, $5/M output; order-of-magnitude) ---")
    print(
        f"Assumes: {n_audit} voice-audit calls (~{_EST_AUDIT_IN}+{_EST_AUDIT_OUT} tok/call) "
        f"+ {n_t3} Tier 3 generations at worst-case (~{_EST_TIER3_IN}+{_EST_TIER3_OUT} tok each)."
    )
    print(f"Estimated total USD (upper bound): ${est_usd:.4f}")
    print(f"Estimated total tokens (in+out): {tot_in + tot_out}")
    print(f"Hard ceiling configured: ${_HARD_CEILING_USD:.2f} (runner aborts --execute if estimate exceeds)")
    if est_usd > _HARD_CEILING_USD:
        print("WARNING: estimate exceeds hard ceiling — --execute will refuse without sample changes.")
    print()
    if future_null_prov:
        print(
            f"Note: {future_null_prov} future live event(s) have provider_id=NULL "
            "(valid for one-offs; if DATE/NEXT are not auditable, cite seed linkage in 6.1.3 report)."
        )
    print("=== End dry run ===")


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser(description="Phase 6.1.2 voice audit runner")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="enumerate samples + cost estimate (default if neither --dry-run nor --execute)",
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="run Tier 3 route() + voice audits (requires --confirm and ANTHROPIC_API_KEY)",
    )
    ap.add_argument(
        "--confirm",
        action="store_true",
        help="acknowledge spend for --execute",
    )
    ap.add_argument(
        "--yes",
        action="store_true",
        help="with --execute --confirm, skip interactive y/N",
    )
    args = ap.parse_args()
    do_dry = args.dry_run or not args.execute
    if args.execute and not args.confirm:
        print("Refusing --execute without --confirm.", file=sys.stderr)
        return 2

    try:
        with SessionLocal() as db:
            tier1_ok, tier1_skip = discover_tier1_matrix(db)
            today = _utcnow().date()
            future_null = _count_future_events_null_provider(db, today)
    except Exception as e:
        print(f"Database error: {e}", file=sys.stderr)
        print(
            "Hint: run `python -m alembic upgrade head` so the SQLite schema matches ORM models.",
            file=sys.stderr,
        )
        return 1

    n_t3 = len(_TIER3_QUERIES)
    n_ref = len(_REFERENCE_SAMPLES)
    est_usd, tot_in, tot_out = _estimate_plan_cost_usd(len(tier1_ok), n_t3, n_ref, assume_all_tier3_hits_llm=True)

    if do_dry:
        _configure_stdout_utf8()
        _print_dry_run(tier1_ok, tier1_skip, est_usd, tot_in, tot_out, future_null)
        return 0

    # --- execute path ---
    if est_usd > _HARD_CEILING_USD:
        print(
            f"Aborting: estimated ${est_usd:.4f} exceeds hard ceiling ${_HARD_CEILING_USD:.2f}.",
            file=sys.stderr,
        )
        return 3

    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        print("ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 4

    if not args.yes:
        ans = input(f"Estimated upper-bound cost ~${est_usd:.4f}. Type y to proceed: ")
        if ans.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 5

    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed.", file=sys.stderr)
        return 6

    client = anthropic.Anthropic(api_key=api_key)

    with SessionLocal() as db:
        tier1_ok, tier1_skip = discover_tier1_matrix(db)
        tier3_payloads = build_tier3_payloads(db)

    audit_inputs = [*tier1_ok, *tier3_payloads, *_REFERENCE_SAMPLES]
    actual_tier3_cost_in = sum(
        (p.get("route_meta") or {}).get("llm_input_tokens") or 0 for p in tier3_payloads
    )
    actual_tier3_cost_out = sum(
        (p.get("route_meta") or {}).get("llm_output_tokens") or 0 for p in tier3_payloads
    )

    verdicts = _run_voice_audits(audit_inputs, client)

    out_path = _ROOT / "scripts" / f"voice_audit_results_{_today()}.json"
    doc = {
        "meta": {
            "date": _today(),
            "git_sha": _git_sha(),
            "audit_model": _AUDIT_MODEL,
            "tier3_queries": n_t3,
            "tier1_auditable": len(tier1_ok),
            "tier1_not_auditable": tier1_skip,
            "reference_samples": n_ref,
            "estimated_usd_upper_bound_pre_run": round(est_usd, 4),
            "tier3_generation_usage_tokens": {
                "input_sum": int(actual_tier3_cost_in),
                "output_sum": int(actual_tier3_cost_out),
            },
            "future_live_events_null_provider_count": future_null,
        },
        "summary": {
            "total_audited": len(verdicts),
            "PASS": sum(1 for v in verdicts if v.get("verdict") == "PASS"),
            "MINOR": sum(1 for v in verdicts if v.get("verdict") == "MINOR"),
            "FAIL": sum(1 for v in verdicts if v.get("verdict") == "FAIL"),
            "ERROR": sum(1 for v in verdicts if v.get("verdict") == "ERROR"),
        },
        "samples": audit_inputs,
        "verdicts": verdicts,
    }
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
