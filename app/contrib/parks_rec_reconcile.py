"""WS6b Phase 1 — reconcile flyer-sourced Parks & Rec events against the WebTrac
registration catalog, the datetime/venue **authority**.

The monthly flyer (vision-parsed) is unreliable; WebTrac (register.lhcaz.gov,
already ingested) is authoritative. **WebTrac wins on conflict.** This module is
the pure, tested core:

  * ``match_flyer`` — pair a flyer event to a WebTrac event by title similarity +
    date proximity (the grid off-by-one) + a soft venue signal. Recurring
    same-title series are guarded (an ambiguous near-date match is rejected).
  * ``classify_flyer`` — decide the action for a flyer event:
      - ``supersede``          — a WebTrac twin exists and either agrees on time
                                 or clearly corrects a flyer AM/PM flip → retire
                                 the flyer, keep WebTrac live.
      - ``needs_confirmation`` — a WebTrac twin exists but they DISAGREE on time in
                                 a way that is not an obvious flip (both plausible,
                                 e.g. Glow in the Dark Family Painting: WebTrac
                                 5:00 PM vs flyer 5:30 PM). Never assumed either
                                 way — flagged for a human to confirm with P&R.
      - ``quarantine``         — no WebTrac twin AND the flyer trips the event lint
                                 (:mod:`app.events.lint`).
      - ``keep``               — no WebTrac twin and the flyer is clean residue.

The gated script ``scripts/parks_rec_webtrac_reconcile_2026_07_08.py`` wires this
to the prod DB (dry-run → CSV → Casey approves → apply); the nightly canary
``scripts/parks_rec_webtrac_canary.py`` re-checks every *future* P&R event.
America/Phoenix throughout (all times are naive local, as stored).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Callable, Protocol

from app.events.dedup_match import start_minutes

# ── tunables ──────────────────────────────────────────────────────────────────
#: Token-set Jaccard at/above which two titles are "the same activity".
TITLE_JACCARD_MIN = 0.6
#: How far a flyer date may sit from its WebTrac twin (the vision grid off-by-one).
#: Exact-date matches are always preferred; proximity is a guarded fallback.
MAX_DATE_DELTA_DAYS = 1
#: Start times within this many minutes are treated as agreeing (rounding slack).
SAME_TIME_MINUTES = 15

# The catch-all default venue, normalized the same way _venue_tokens normalizes
# (``&`` → space): it carries no venue signal, so it never contradicts.
_DEFAULT_VENUE = "lake havasu city parks recreation"


class EventLike(Protocol):
    """The duck-typed shape the reconciler needs (an ``Event`` row or a test
    double). All times are naive America/Phoenix, as stored."""

    id: Any
    title: str | None
    date: date | None
    start_time: time | None
    location_name: str | None


_WEBTRAC_URL_MARKER = "register.lhcaz.gov/webtrac"


def is_webtrac_event(event: Any) -> bool:
    """True when the event's URL is a WebTrac registration URL — the datetime
    authority, NEVER a flyer. A WebTrac event can carry a COMBINED source string
    that also names the flyer source (via the ingest reconciler's source merge), so
    callers MUST exclude these from the flyer set by URL, not by source, or a
    WebTrac row would be reconciled against itself (the 2026-07-07 self-match)."""
    return _WEBTRAC_URL_MARKER in (getattr(event, "event_url", None) or "")


# ── title similarity ──────────────────────────────────────────────────────────
_PAREN_RE = re.compile(r"\([^)]*\)")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _norm_title(title: str | None) -> str:
    return _NON_ALNUM_RE.sub(" ", _PAREN_RE.sub(" ", (title or "").lower())).strip()


def title_tokens(title: str | None) -> frozenset[str]:
    return frozenset(t for t in _norm_title(title).split() if t)


def titles_similar(a: str | None, b: str | None) -> bool:
    """True when two program titles name the same activity: exact, a prefix of the
    other ("Kids Pizza Party" ⊂ "Kids Pizza Party Cooking Class"), a token subset,
    or token-set Jaccard ≥ :data:`TITLE_JACCARD_MIN`."""
    na, nb = _norm_title(a), _norm_title(b)
    if not na or not nb:
        return False
    if na == nb or na.startswith(nb) or nb.startswith(na):
        return True
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= TITLE_JACCARD_MIN


# ── venue (soft signal only — flyer venues are often scrambled) ────────────────
# Generic venue words shared across many places ("Wheeler Park" vs "Rotary Park")
# carry no distinguishing signal — drop them so compatibility keys on proper nouns.
_VENUE_STOPWORDS: frozenset[str] = frozenset({
    "park", "center", "centre", "field", "fields", "court", "courts", "room",
    "rooms", "site", "hall", "complex", "pool", "gym", "the", "and", "of", "at",
    "lake", "havasu", "city", "parks", "recreation", "rec",
})


def _venue_tokens(venue: str | None) -> frozenset[str]:
    norm = _NON_ALNUM_RE.sub(" ", (venue or "").lower()).strip()
    if not norm or norm == _DEFAULT_VENUE:
        return frozenset()  # the catch-all default carries no venue signal
    return frozenset(t for t in norm.split() if len(t) > 2 and t not in _VENUE_STOPWORDS)


def venue_compatible(a: str | None, b: str | None) -> bool:
    """Soft: two venues are compatible unless BOTH are named and share no token.
    A missing/default venue never contradicts (the flyer often scrambles it)."""
    ta, tb = _venue_tokens(a), _venue_tokens(b)
    if not ta or not tb:
        return True
    return bool(ta & tb)


# ── time-conflict shape ───────────────────────────────────────────────────────
def time_delta_minutes(a: time | None, b: time | None) -> int | None:
    """Absolute start-time gap in minutes, or None if either side is missing."""
    if a is None or b is None:
        return None
    return abs(start_minutes(a) - start_minutes(b))


def looks_like_ampm_flip(flyer_t: time | None, web_t: time | None) -> bool:
    """True when the flyer time is the same clock face as WebTrac's but a different
    meridiem (5:30 vs 17:30) — a flyer AM/PM typo that WebTrac plainly corrects, so
    we can supersede without a human."""
    if flyer_t is None or web_t is None:
        return False
    return (
        flyer_t.hour != web_t.hour
        and flyer_t.hour % 12 == web_t.hour % 12
        and flyer_t.minute == web_t.minute
    )


# ── matching ──────────────────────────────────────────────────────────────────
def _date_delta(a: date | None, b: date | None) -> int | None:
    if a is None or b is None:
        return None
    return abs((a - b).days)


def match_flyer(
    flyer: EventLike,
    webtracs: list[EventLike],
    *,
    max_date_delta_days: int = MAX_DATE_DELTA_DAYS,
) -> EventLike | None:
    """Best WebTrac twin for ``flyer``, or None.

    Exact-date title matches win. Failing that, a proximity match is allowed ONLY
    when it is unambiguous — exactly one title-similar WebTrac event within the
    date window — so a recurring same-title series (many nearby dates) never
    mispairs. Ties on an exact date are broken by venue compatibility then the
    closest start time.

    A candidate with the SAME id as the flyer is skipped: a WebTrac event whose
    combined ``source`` also names the flyer source can land in both sets, and it
    must never supersede ITSELF (the 2026-07-07 self-match mis-retire).
    """
    flyer_id = getattr(flyer, "id", None)
    similar = [
        w
        for w in webtracs
        if getattr(w, "id", None) != flyer_id and titles_similar(flyer.title, w.title)
    ]
    if not similar:
        return None
    exact = [w for w in similar if w.date == flyer.date and flyer.date is not None]
    if exact:
        return _pick_best(flyer, exact)
    near = [
        w
        for w in similar
        if (d := _date_delta(w.date, flyer.date)) is not None and d <= max_date_delta_days
    ]
    # Ambiguous proximity (a recurring series) → require an exact date; refuse.
    return near[0] if len(near) == 1 else None


def _pick_best(flyer: EventLike, candidates: list[EventLike]) -> EventLike:
    def _key(w: EventLike) -> tuple[int, int]:
        venue_penalty = 0 if venue_compatible(flyer.location_name, w.location_name) else 1
        dt = time_delta_minutes(flyer.start_time, w.start_time)
        return (venue_penalty, dt if dt is not None else 24 * 60)

    return sorted(candidates, key=_key)[0]


# ── classification ────────────────────────────────────────────────────────────
SUPERSEDE = "supersede"
NEEDS_CONFIRMATION = "needs_confirmation"
QUARANTINE = "quarantine"
KEEP = "keep"


@dataclass(frozen=True)
class FlyerVerdict:
    flyer: EventLike
    action: str  # one of SUPERSEDE / NEEDS_CONFIRMATION / QUARANTINE / KEEP
    webtrac: EventLike | None = None
    time_delta_minutes: int | None = None
    venue_conflict: bool = False
    reasons: tuple[str, ...] = ()

    @property
    def detail(self) -> str:
        bits = list(self.reasons)
        if self.time_delta_minutes is not None:
            bits.append(f"Δtime={self.time_delta_minutes}m")
        if self.venue_conflict:
            bits.append("venue-conflict")
        return "|".join(bits)


def classify_flyer(
    flyer: EventLike,
    webtracs: list[EventLike],
    *,
    lint_fn: Callable[[Any], list[Any]],
    max_date_delta_days: int = MAX_DATE_DELTA_DAYS,
) -> FlyerVerdict:
    """Decide the action for one flyer event. ``lint_fn`` is
    :func:`app.events.lint.lint_event` (injected so the module stays pure/testable
    and picks up whatever lint version is deployed)."""
    match = match_flyer(flyer, webtracs, max_date_delta_days=max_date_delta_days)
    if match is not None:
        dt = time_delta_minutes(flyer.start_time, match.start_time)
        venue_conflict = not venue_compatible(flyer.location_name, match.location_name)
        if dt is None or dt <= SAME_TIME_MINUTES:
            return FlyerVerdict(flyer, SUPERSEDE, match, dt, venue_conflict, ("times-agree",))
        if looks_like_ampm_flip(flyer.start_time, match.start_time):
            return FlyerVerdict(
                flyer, SUPERSEDE, match, dt, venue_conflict, ("webtrac-corrects-ampm-flip",)
            )
        # Genuine disagreement, both plausible → never assume; a human confirms.
        return FlyerVerdict(
            flyer, NEEDS_CONFIRMATION, match, dt, venue_conflict, ("time-conflict",)
        )
    findings = lint_fn(flyer)
    if findings:
        rules = tuple(getattr(f, "rule", str(f)) for f in findings)
        return FlyerVerdict(flyer, QUARANTINE, None, None, False, rules)
    return FlyerVerdict(flyer, KEEP, None, None, False, ())


@dataclass
class ReconcileResult:
    supersede: list[FlyerVerdict] = field(default_factory=list)
    needs_confirmation: list[FlyerVerdict] = field(default_factory=list)
    quarantine: list[FlyerVerdict] = field(default_factory=list)
    keep: list[FlyerVerdict] = field(default_factory=list)

    def add(self, v: FlyerVerdict) -> None:
        getattr(self, v.action).append(v)

    @property
    def counts(self) -> dict[str, int]:
        return {
            SUPERSEDE: len(self.supersede),
            NEEDS_CONFIRMATION: len(self.needs_confirmation),
            QUARANTINE: len(self.quarantine),
            KEEP: len(self.keep),
        }


def reconcile(
    flyers: list[EventLike],
    webtracs: list[EventLike],
    *,
    lint_fn: Callable[[Any], list[Any]],
    max_date_delta_days: int = MAX_DATE_DELTA_DAYS,
) -> ReconcileResult:
    """Classify every flyer event against the WebTrac authority set."""
    result = ReconcileResult()
    for flyer in flyers:
        result.add(
            classify_flyer(
                flyer, webtracs, lint_fn=lint_fn, max_date_delta_days=max_date_delta_days
            )
        )
    return result
