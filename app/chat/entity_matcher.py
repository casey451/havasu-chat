"""Fuzzy match user queries to a canonical ``Program.provider_name``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.normalizer import normalize
from app.db.models import Program, Provider

# Keys MUST match ``provider_name`` strings produced by
# ``docs/HAVASU_CHAT_SEED_INSTRUCTIONS.md`` / ``scripts/seed_from_havasu_instructions.py``.
CANONICAL_EXTRAS: dict[str, list[str]] = {
    "Iron Wolf Golf & Country Club": [
        "iron wolf",
        "iron wolf golf",
    ],
    "Altitude Trampoline Park — Lake Havasu City": [
        "altitude",
        "altitude trampoline park",
        "trampoline park",
    ],
    "Havasu Lanes": [
        "bowling alley",
        "havasu lanes",
    ],
    "Bridge City Combat (also: Bridge City Combat & Barry Sullins Jiu-Jitsu)": [
        "bridge city",
        "bridge city combat",
    ],
    "Lake Havasu City BMX": [
        "bmx",
        "lake havasu bmx",
        "bmx track",
        "sara park bmx",
    ],
    "Lake Havasu Mountain Bike Club": [
        "mountain bike",
        "mountain bikes",
        "mountain biking",
        "mtb",
        "bike trail",
        "dirt trail",
        "trail riding",
    ],
    "Universal Gymnastics and All Star Cheer — Sonics": [
        "sonics",
        "universal gymnastics",
        "gymnastics place on kiowa",
    ],
    "Lake Havasu City Aquatic Center": [
        "aquatic center",
        "havasu aquatic center",
    ],
    "The Tap Room Jiu Jitsu": [
        "tap room",
        "tap room bjj",
        "tap room jiu jitsu",
    ],
    "Lake Havasu Little League": [
        "little league",
    ],
    "Havasu Lions FC": [
        "lions",
        "havasu lions",
    ],
    "Lake Havasu Black Belt Academy": [
        "black belt academy",
        "lhcbba",
    ],
    "Aqua Beginnings": [
        "aqua beginnings",
    ],
    "Ballet Havasu": [
        "ballet havasu",
    ],
    "Flips for Fun Gymnastics": [
        "flips for fun",
    ],
}


@dataclass(frozen=True)
class _EntityRow:
    """One provider with all phrases to score against (already lowercased / normalized)."""

    canonical: str
    needles: frozenset[str]


@dataclass(frozen=True)
class EntityMatch:
    """One catalog provider mentioned in free text (Phase 6.4.1)."""

    name: str
    type: str
    id: str


_rows: list[_EntityRow] | None = None


def _needles_for_canonical(canonical: str) -> frozenset[str]:
    out: set[str] = set()
    c = canonical.strip()
    if not c:
        return frozenset()
    out.add(normalize(c))
    out.add(c.lower())
    for extra in CANONICAL_EXTRAS.get(c, []):
        n = normalize(extra)
        if n:
            out.add(n)
    return frozenset(x for x in out if x)


def refresh_entity_matcher(db: Session) -> None:
    """Load distinct ``Program.provider_name`` values and rebuild the in-memory index."""
    global _rows
    names = db.scalars(select(Program.provider_name).distinct()).all()
    canon = sorted({(n or "").strip() for n in names if (n or "").strip()})
    _rows = [_EntityRow(c, _needles_for_canonical(c)) for c in canon]


def reset_entity_matcher() -> None:
    """Clear the cache (mainly for tests)."""
    global _rows
    _rows = None


def _best_score(norm_query: str, needles: frozenset[str]) -> float:
    best = 0.0
    for needle in needles:
        best = max(best, float(fuzz.token_set_ratio(norm_query, needle)))
    return best


def _provider_id_for_name(db: Session, provider_name: str) -> str:
    """Resolve ``Provider.id`` when present; else fall back to name (same as ``record_entity``)."""
    name = (provider_name or "").strip()
    if not name:
        return ""
    try:
        row = db.scalars(select(Provider).where(Provider.provider_name == name).limit(1)).first()
        if row is not None:
            return str(row.id)
    except Exception:
        pass
    return name


def extract_catalog_entities_from_text(text: str, db: Session) -> list[EntityMatch]:
    """Return all catalog **providers** mentioned in *text* with fuzzy score strictly above 75.

    Uses the same in-memory index as :func:`match_entity`. Each hit is deduplicated by canonical
    name (one entry per provider). ``type`` is always ``"provider"`` for Phase 6.4.1.
    """
    global _rows
    if _rows is None:
        refresh_entity_matcher(db)
    assert _rows is not None

    norm = normalize(text)
    if not norm:
        return []

    best_by_canon: dict[str, float] = {}
    for row in _rows:
        s = _best_score(norm, row.needles)
        if s > 75.0:
            prev = best_by_canon.get(row.canonical)
            if prev is None or s > prev:
                best_by_canon[row.canonical] = s

    out: list[EntityMatch] = []
    for name in sorted(best_by_canon.keys()):
        pid = _provider_id_for_name(db, name)
        out.append(EntityMatch(name=name, type="provider", id=pid))
    return out


def match_entity(query: str, db: Session) -> tuple[str, float] | None:
    """Return ``(provider_name, score)`` if the best fuzzy match is strictly above 75.

    ``provider_name`` is the denormalized provider key on ``Program`` rows (there is no
    separate Provider table). Call :func:`refresh_entity_matcher` after bulk program imports.
    """
    global _rows
    if _rows is None:
        refresh_entity_matcher(db)
    assert _rows is not None

    norm = normalize(query)
    if not norm:
        return None

    best_canon: str | None = None
    best_score = -1.0
    for row in _rows:
        s = _best_score(norm, row.needles)
        if s > best_score:
            best_score = s
            best_canon = row.canonical
        elif s == best_score and best_canon is not None and row.canonical < best_canon:
            best_canon = row.canonical

    if best_canon is None or best_score <= 75.0:
        return None
    return (best_canon, best_score)


def match_entity_with_rows(query: str, canonical_names: Sequence[str]) -> tuple[str, float] | None:
    """Match *query* against an explicit list of canonical provider names (no DB)."""
    norm = normalize(query)
    if not norm:
        return None
    best_canon: str | None = None
    best_score = -1.0
    for c in canonical_names:
        c = c.strip()
        if not c:
            continue
        needles = _needles_for_canonical(c)
        s = _best_score(norm, needles)
        if s > best_score:
            best_score = s
            best_canon = c
        elif s == best_score and best_canon is not None and c < best_canon:
            best_canon = c
    if best_canon is None or best_score <= 75.0:
        return None
    return (best_canon, best_score)
