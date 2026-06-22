"""First-class event-TYPE classification (P2): live_music / comedy / car_show.

Generalizes the movie-tag model (``app.events.movie_tags`` — a string in
``Event.tags``) to the performance/show types the calendar should signal *before*
the click. A bare band name ("Sacred Stone") or comedy show ("Top Goons") carries
no type word a user can scan, so we derive a type from the same conservative
signals P1's classifiers use (curated names + venue + word-boundary keywords, with
the civic / automotive / family guards), and surface it as a small label.

Single source of truth, used at BOTH:
- ingest (``app.contrib.event_ingest._tags`` stamps the durable tag), and
- render (``event_type_label`` + the music subsection split) so existing rows
  that predate the tag still signal their type — no backfill required for display.

False positives are worse than misses here, so every path is guarded.
"""

from __future__ import annotations

import re

LIVE_MUSIC = "live_music"
COMEDY = "comedy"
CAR_SHOW = "car_show"

# Plain, COPY_VOICE-clean display labels (no em-dash, no system-speak).
EVENT_TYPE_LABELS: dict[str, str] = {
    LIVE_MUSIC: "Live Music",
    COMEDY: "Comedy",
    CAR_SHOW: "Car Show",
}
# Preference order when an event somehow carries more than one type.
_LABEL_ORDER: tuple[str, ...] = (LIVE_MUSIC, COMEDY, CAR_SHOW)

# Curated local acts whose NAME carries no type word (the confirmed-live targets).
# Substring-matched on the normalized title, so "Sacred Stone Live" still hits.
CURATED_LIVE_MUSIC: frozenset[str] = frozenset(
    {"sacred stone", "sparks after midnight", "the brew band", "retro riot"}
)
CURATED_COMEDY: frozenset[str] = frozenset({"top goons"})

# Word-boundary keyword signals (each allows a plural/gerund tail).
_MUSIC_VENUE_RE = re.compile(
    r"\b(lounge|saloon|tavern|pub|taproom|brewery|brewing|cantina|nightclub|"
    r"speakeasy|ale\s?house|wine bar|music hall|amphitheat(?:er|re)|beer garden)\b",
    re.IGNORECASE,
)
_MUSIC_STRONG_RE = re.compile(
    r"\b(live music|live band|band|bands|concert|acoustic|setlist|set list|"
    r"tribute|singer[- ]songwriter|cover band|jam session)\b",
    re.IGNORECASE,
)
_MUSIC_WEAK_RE = re.compile(
    r"\b(dj|deejay|dance party|duo|trio|live at|on stage|performing live|plays live)\b",
    re.IGNORECASE,
)
# Explicit comedy — always counts. Critically does NOT match a bare "play":
# "Open Play" / "Pickleball Open Play" (a daily sports row) was being labeled
# Comedy off the word "Play". "musical"/"drama" are dropped (ambiguous: "musical
# bingo", a "drama class"). Named comedy acts are handled by CURATED_COMEDY.
_COMEDY_EXPLICIT_RE = re.compile(
    r"\b(comedy|comedian|comedians|stand[- ]?up|standup|improv|cabaret|"
    r"open mic comedy|comedy night)\b",
    re.IGNORECASE,
)
# Theater words are name-prone (a music act named "Elective Theatre", a band at a
# venue called "Playhouse"), so they imply comedy/theater ONLY when the event has
# no live-music signal. "playhouse"/"stage play" kept; bare "play" is not here.
_THEATER_RE = re.compile(r"\b(theat(?:er|re)|playhouse|stage play)\b", re.IGNORECASE)
_AUTOMOTIVE_RE = re.compile(
    r"\b(car show|cruise[- ]?in|motor madness|auto show|classic car|hot rod|"
    r"show\s*[&n]?\s*shine|poker run|motorcycle rally)\b",
    re.IGNORECASE,
)
_FAMILY_CONTEXT_RE = re.compile(
    r"\b(all ages|kid|kids|family|families|junior|toddler|youth|children|child)\b",
    re.IGNORECASE,
)
_CIVIC_GUARD_RE = re.compile(
    r"\b(city council|council|commission|board of|planning and zoning|"
    r"public hearing|city hall|town hall|government|civic)\b",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")


def _normalize(text: str | None) -> str:
    return _WS_RE.sub(" ", (text or "").strip().lower())


def classify_event_type(
    *,
    title: str | None,
    tags: list[str] | tuple[str, ...] | None = None,
    venue: str | None = "",
    description: str | None = "",
    organizer: str | None = "",
) -> set[str]:
    """Return the subset of {live_music, comedy, car_show} this event signals.

    Conservative + guarded: civic items are never music/comedy; an automotive
    event is a car show (never music) unless it has a STRONG live-music headliner;
    a weak signal (DJ/dance) at a kids/all-ages event is not live music.
    """
    types: set[str] = set()
    tagset = {str(t).lower() for t in (tags or [])}
    # A durable specific tag (ingest/backfill) is authoritative.
    for t in (LIVE_MUSIC, COMEDY, CAR_SHOW):
        if t in tagset:
            types.add(t)

    ntitle = _normalize(title)
    if any(name in ntitle for name in CURATED_COMEDY):
        types.add(COMEDY)
    if any(name in ntitle for name in CURATED_LIVE_MUSIC):
        types.add(LIVE_MUSIC)

    blob = " ".join(x for x in (title, description, venue, organizer) if x)
    strong_music = bool(_MUSIC_STRONG_RE.search(blob))
    automotive = bool(_AUTOMOTIVE_RE.search(blob))

    # Car show: an automotive event with no strong live-music headliner.
    if automotive and not strong_music:
        types.add(CAR_SHOW)

    # Civic items are never music/comedy even if their agenda trips a keyword.
    if _CIVIC_GUARD_RE.search(blob):
        types.discard(LIVE_MUSIC)
        types.discard(COMEDY)
        return types

    # Live-music signal (suppressed at a car show; a weak signal needs a non-kids
    # context). The coarse legacy ``music`` tag (stamped from the venue at ingest)
    # counts, so a Lighthouse-Lounge band that predates this module still types.
    music_signal = strong_music or "music" in tagset or bool(_MUSIC_VENUE_RE.search(blob))
    if not music_signal and _MUSIC_WEAK_RE.search(blob):
        family_ctx = _FAMILY_CONTEXT_RE.search(f"{title or ''} {description or ''}")
        music_signal = not family_ctx

    # Comedy: an explicit comedy word always counts; a theater word counts only
    # when there's no live-music signal, so a music act named "...Theatre" or a gig
    # at a "Playhouse" stays music, not comedy.
    if _COMEDY_EXPLICIT_RE.search(blob) or (_THEATER_RE.search(blob) and not music_signal):
        types.add(COMEDY)

    # Strong music (a real concert/band) wins even at a car show, matching the
    # ingest ``_live_music_tags`` rule; a weak/venue-only signal stays suppressed
    # by the automotive guard.
    if music_signal and (strong_music or not automotive):
        types.add(LIVE_MUSIC)

    # A comedy show at a music venue (e.g. "Top Goons" at a lounge) is comedy, not
    # live music — unless there's a real (strong) music signal too.
    if COMEDY in types and LIVE_MUSIC in types and not strong_music:
        if not any(name in ntitle for name in CURATED_LIVE_MUSIC):
            types.discard(LIVE_MUSIC)

    return types


def is_strong_live_music(
    title: str | None, venue: str | None = "", description: str | None = ""
) -> bool:
    """True only for ACTUAL live music — a band/concert/acoustic signal or a
    curated local act. A venue-only or DJ/karaoke signal is NOT strong (it lands
    in the music group's residual subsection, not "Live Music")."""
    blob = " ".join(x for x in (title, description, venue) if x)
    if _MUSIC_STRONG_RE.search(blob):
        return True
    return any(name in _normalize(title) for name in CURATED_LIVE_MUSIC)


def _has_live_music_performance_signal(
    title: str | None,
    tags: list[str] | tuple[str, ...] | None,
    venue: str | None,
    description: str | None,
) -> bool:
    """True when an event carries an actual music-PERFORMANCE signal (a keyword,
    a curated act, or the durable tag) — NOT merely a music venue. A bare
    brewery/saloon venue routes an event into the Music group, but is not enough
    to stamp a "Live Music" badge on it (else a Paint & Sip or Bingo night at a
    brewery reads as Live Music)."""
    if LIVE_MUSIC in {str(t).lower() for t in (tags or [])}:
        return True
    if any(name in _normalize(title) for name in CURATED_LIVE_MUSIC):
        return True
    blob = " ".join(x for x in (title, description, venue) if x)
    return bool(_MUSIC_STRONG_RE.search(blob) or _MUSIC_WEAK_RE.search(blob))


def event_type_label(
    title: str | None,
    tags: list[str] | tuple[str, ...] | None = None,
    venue: str | None = "",
    description: str | None = "",
) -> str | None:
    """The single plain label to show beside a title ("Live Music" / "Comedy" /
    "Car Show"), or None. Tag-first via :func:`classify_event_type`, so it works
    on existing rows without a backfill. Highest-preference type wins — but a
    LIVE_MUSIC badge needs a real performance signal, not just a music venue."""
    types = classify_event_type(
        title=title, tags=tags, venue=venue, description=description
    )
    for t in _LABEL_ORDER:
        if t not in types:
            continue
        if t == LIVE_MUSIC and not _has_live_music_performance_signal(
            title, tags, venue, description
        ):
            continue  # venue-only → routes to Music, but no badge
        return EVENT_TYPE_LABELS[t]
    return None
