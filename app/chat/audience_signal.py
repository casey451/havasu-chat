"""Audience-signal classifier — Lane S3 of the visitor-mode dispatch.

Composes a *cheap* per-request audience signal (visitor / local / ambiguous)
from features that are already available at the request boundary: client IP
country (read from CDN headers), request timestamp in Lake Havasu local time,
and a light keyword scan on the query string.

This is **orthogonal** to ``intent_classifier`` — it answers "who is asking?"
not "what are they asking?". The signal is persisted to
``chat_logs.audience_signal`` for Phase 2 analysis (whether to ship a
visitor-mode UI). No ranking adjustments are made off this signal in this
slice.

Design constraints:

* Pure function, no I/O — safe to call on every request.
* No GeoIP dependency added; geolocation reads CDN-provided headers only.
* Returns ``"ambiguous"`` whenever the signal is weak — never guesses.
* Composition is deterministic and inspectable (no ML).

See ``HAVA_CONCIERGE_HANDOFF.md`` §3 for placement in the routing pipeline,
and ``docs/maintainability/disclosure_renderer_spec.md`` §1 for the
placement-regime selection that future ranking adjustments will read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping

AudienceClass = Literal["visitor", "local", "ambiguous"]


# --- Constants ---------------------------------------------------------------

# ZIP buckets for Lake Havasu City. Mohave County 86404/86406 are core
# in-town; this list is intentionally tiny — anything else falls through to
# nearby/out-of-area via header inspection.
_IN_TOWN_ZIPS: frozenset[str] = frozenset({"86404", "86406"})

# AZ / NV / CA region codes considered "nearby" when surfaced via the
# CF-Region / X-Vercel-IP-Region headers. The CDN layer normalizes these to
# ISO-3166-2 subdivision codes.
_NEARBY_REGIONS: frozenset[str] = frozenset({"AZ", "NV", "CA"})

# Country code we treat as in-region (in_town/nearby/out_of_area). Anything
# else with a country header goes straight to out_of_area.
_US_COUNTRY = "US"

# Light keyword scan on the query. These lists are intentionally short —
# the signal must be cheap and false-positives bias toward "ambiguous", not
# wrong classifications.
_VISITOR_WORDS: frozenset[str] = frozenset(
    {
        "visiting",
        "visit",
        "tourist",
        "rent",
        "rental",
        "tour",
        "weekend trip",
        "boat rental",
        "where to stay",
        "things to do",
    }
)

_LOCAL_WORDS: frozenset[str] = frozenset(
    {
        "plumber",
        "hvac",
        "doctor",
        "dentist",
        "school",
        "grocery",
        "fix",
        "repair",
        "tonight",
        "tomorrow",
        "this weekend",
    }
)


@dataclass(frozen=True)
class AudienceSignal:
    """Composed per-request audience classification.

    All fields are deterministic functions of the request inputs. ``confidence``
    is in [0.0, 1.0] and reflects the score margin between visitor and local
    sub-scores; ambiguous outcomes carry a low fixed confidence (~0.3).
    """

    audience: AudienceClass
    geo_bucket: str  # "in_town" / "nearby" / "out_of_area" / "unknown"
    time_of_day: str  # "morning" / "midday" / "afternoon" / "evening" / "late_night"
    day_of_week: str  # "weekday" / "weekend"
    season: str  # "snowbird" / "spring_break" / "summer" / "shoulder"
    confidence: float


# --- Header-driven geo bucket (stub — no GeoIP dependency) -------------------


def bucket_geo_from_headers(headers: Mapping[str, str] | None) -> str:
    """Bucket a request's origin into one of in_town / nearby / out_of_area / unknown.

    This is a *stub*: we read whatever the CDN already set on the request
    (Cloudflare's ``CF-IPCountry``/``CF-Region``, Vercel's
    ``X-Vercel-IP-Country``/``X-Vercel-IP-Country-Region``, or a ``X-Zip``
    header if upstream populated it). A real GeoIP lookup is a separate
    ticket. When no relevant header is present, returns ``"unknown"`` and the
    classifier defaults toward "ambiguous".
    """
    if not headers:
        return "unknown"

    # Header lookup is case-insensitive in practice; normalize once.
    norm: dict[str, str] = {}
    for k, v in headers.items():
        if not isinstance(k, str) or v is None:
            continue
        norm[k.lower()] = str(v).strip()

    # 1) ZIP — most precise, when an upstream layer exposes it.
    zip_value = norm.get("x-zip") or norm.get("cf-postal-code")
    if zip_value:
        zip_clean = zip_value.split("-", 1)[0].strip()
        if zip_clean in _IN_TOWN_ZIPS:
            return "in_town"

    # 2) Region — nearby AZ/NV/CA, only when paired with country == US.
    country = norm.get("cf-ipcountry") or norm.get("x-vercel-ip-country") or norm.get("x-country")
    region = (
        norm.get("cf-region-code")
        or norm.get("cf-region")
        or norm.get("x-vercel-ip-country-region")
        or norm.get("x-region")
    )

    if country:
        country_uc = country.upper()
        if country_uc == _US_COUNTRY:
            if region:
                region_uc = region.upper()
                if region_uc in _NEARBY_REGIONS:
                    return "nearby"
                # In-region US but not AZ/NV/CA → out of area.
                return "out_of_area"
            # US but no region info — treat as out_of_area; we can't claim nearby.
            return "out_of_area"
        return "out_of_area"

    # 3) X-Forwarded-For exists but no country/region info — unknown.
    return "unknown"


# --- Time-of-day / day-of-week / season --------------------------------------


def time_of_day_bucket(dt: datetime) -> str:
    """Bucket a datetime's hour into morning/midday/afternoon/evening/late_night."""
    h = dt.hour
    if 5 <= h < 11:
        return "morning"
    if 11 <= h < 14:
        return "midday"
    if 14 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "late_night"  # 22..23 and 0..4


def day_of_week_bucket(dt: datetime) -> str:
    """Bucket a datetime's weekday into weekday (Mon–Thu) / weekend (Fri–Sun).

    Lake Havasu's tourism weekend starts Friday — the bucket reflects local
    economic reality, not the calendar. ``datetime.weekday()`` is 0=Mon..6=Sun.
    """
    return "weekend" if dt.weekday() >= 4 else "weekday"


def season_bucket(dt: datetime) -> str:
    """Bucket a datetime's month/day into the rough Lake Havasu calendar.

    Overlap rule: spring_break (mid-Feb to mid-Apr) overrides snowbird and
    shoulder where the months would otherwise both apply, since tourism
    behavior dominates the signal in those weeks.
    """
    m = dt.month
    d = dt.day

    # spring_break wins where it overlaps (mid-Feb..mid-Apr).
    if (m == 2 and d >= 15) or m == 3 or (m == 4 and d <= 15):
        return "spring_break"
    if m in (11, 12, 1, 2, 3):
        return "snowbird"
    if m in (5, 6, 7, 8, 9):
        return "summer"
    # April (post mid-Apr) and October.
    return "shoulder"


# --- Composition rule --------------------------------------------------------


def _query_score(query_text: str) -> tuple[int, int]:
    """Return (visitor_bump, local_bump) from light keyword scan."""
    if not query_text:
        return 0, 0
    q = query_text.lower()
    v = 2 if any(w in q for w in _VISITOR_WORDS) else 0
    lc = 2 if any(w in q for w in _LOCAL_WORDS) else 0
    return v, lc


def classify_audience(
    *,
    client_ip: str | None,
    accept_language: str | None,
    request_time_local: datetime,
    query_text: str,
    headers: Mapping[str, str] | None = None,
) -> AudienceSignal:
    """Compose the audience signal from cheap-to-compute request features.

    Pure function; safe to call on every request. Returns ``"ambiguous"`` as
    the default when signal is weak or unavailable.

    Parameters mirror the request boundary so the router can pass raw values
    (no parsed CDN structures) and this module owns all interpretation. The
    ``request_time_local`` argument should be a Lake Havasu local datetime
    when the caller already has one (``app.core.timezone.now_lake_havasu()``);
    the bucket boundaries are anchored in *local* wall-clock semantics.

    ``client_ip`` and ``accept_language`` are accepted but currently unused
    by the geo/locale heuristics — they're in the signature so future work
    can fold in browser locale or true GeoIP without a router-side rewrite.
    """
    # 1) Geo bucket — header-driven stub.
    geo = bucket_geo_from_headers(headers)

    # 2) Time / day / season — Lake Havasu local clock semantics.
    tod = time_of_day_bucket(request_time_local)
    dow = day_of_week_bucket(request_time_local)
    season = season_bucket(request_time_local)

    # 3) Score visitor vs. local — deterministic, simple.
    score_visitor = 0
    score_local = 0

    if geo == "in_town":
        score_local += 2
    elif geo == "out_of_area":
        score_visitor += 2
    elif geo == "nearby":
        score_visitor += 1
    # geo == "unknown" → no geo bump.

    if season == "snowbird" and dow == "weekend":
        score_visitor += 1
    if season == "spring_break":
        score_visitor += 1
    if season == "summer" and dow == "weekend":
        score_visitor += 1

    v_bump, l_bump = _query_score(query_text)
    score_visitor += v_bump
    score_local += l_bump

    # 4) Decide.
    diff = score_local - score_visitor
    if diff >= 2:
        confidence = min(0.9, 0.3 + 0.15 * abs(diff))
        return AudienceSignal(
            audience="local",
            geo_bucket=geo,
            time_of_day=tod,
            day_of_week=dow,
            season=season,
            confidence=confidence,
        )
    if -diff >= 2:  # score_visitor - score_local >= 2
        confidence = min(0.9, 0.3 + 0.15 * abs(diff))
        return AudienceSignal(
            audience="visitor",
            geo_bucket=geo,
            time_of_day=tod,
            day_of_week=dow,
            season=season,
            confidence=confidence,
        )
    return AudienceSignal(
        audience="ambiguous",
        geo_bucket=geo,
        time_of_day=tod,
        day_of_week=dow,
        season=season,
        confidence=0.3,
    )
