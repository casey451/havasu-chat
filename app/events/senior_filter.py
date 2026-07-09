"""Senior-mode event filter -- "is this a seniors thing?".

Powers the additive **Seniors** overlay on ``/events-ui`` (see
:func:`app.home.events_views.day_groups`), mirroring the Kids & Family overlay.
An occurrence is a seniors item when it carries a senior tag (the senior-center
loader stamps ``"senior"`` on every row) or its title positively reads as a
seniors program. Tag-first keeps it precise; the title fallback catches
senior-center items that arrive from other paths.
"""

from __future__ import annotations

# Tags written by the senior-center loader (and any future senior source).
_SENIOR_TAGS = frozenset(
    {"senior", "seniors", "older adults", "55+", "meals on wheels"}
)

# Venue/provider names that ARE a senior program, so every occurrence published
# under them is a Seniors item even when its title and tags carry no senior word
# (future senior-center / senior-program rows auto-route here). Substring matched,
# lower-cased. Kept precise: a "community center" alone is NOT here (it hosts all
# ages); only an explicit senior venue/program.
_SENIOR_VENUE_HINTS: tuple[str, ...] = (
    "senior center",
    "senior centre",
    "senior living",
    "senior community",
)


def is_senior_event(
    title: str | None, tags: list[str] | None = None, venue: str | None = None
) -> bool:
    """True when the occurrence is gated Senior-Center programming.

    Senior membership is decided by TAG or VENUE only (Phase 4 / Q5, Casey
    2026-06-26): (1) a senior TAG (the senior-center loader stamps ``senior`` on
    every row); (2) a senior PROVIDER/venue (the Senior Center and like programs —
    so a generically-named "Exercise Class" published there still routes to
    Seniors). **Never a title keyword** — the Seniors group is the gated
    Senior-Center surface, so a public Aquatic-Center class whose title merely
    contains "arthritis" / "tai chi" / "water wellness" is NOT senior-gated and
    stays in Sports & Fitness. Genuine senior programming carries the tag (or the
    senior venue), so it is still caught.
    """
    for tag in tags or []:
        if isinstance(tag, str) and tag.strip().lower() in _SENIOR_TAGS:
            return True
    vlow = (venue or "").lower()
    if vlow and any(h in vlow for h in _SENIOR_VENUE_HINTS):
        return True
    return False
