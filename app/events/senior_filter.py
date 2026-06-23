"""Senior-mode event filter -- "is this a seniors thing?".

Powers the additive **Seniors** overlay on ``/events-ui`` (see
:func:`app.home.events_views.day_groups`), mirroring the Kids & Family overlay.
An occurrence is a seniors item when it carries a senior tag (the senior-center
loader stamps ``"senior"`` on every row) or its title positively reads as a
seniors program. Tag-first keeps it precise; the title fallback catches
senior-center items that arrive from other paths.
"""

from __future__ import annotations

import re

# Tags written by the senior-center loader (and any future senior source).
_SENIOR_TAGS = frozenset(
    {"senior", "seniors", "older adults", "55+", "meals on wheels"}
)

# Positive seniors signals in a title. Word-boundary matched; kept precise so a
# generic "Senior Night" at a bar doesn't get pulled in without a tag. Beyond the
# explicit senior words, a curated set of unambiguous senior-PROGRAM signals
# (low-impact / mobility / adaptive classes) is included so senior items arriving
# WITHOUT a tag still surface. Deliberately excludes Lake-Havasu-ambiguous terms:
# "bridge" (the London Bridge), "billiards", "gentle", "line dance" — too broad to
# imply seniors on their own. "bunco"/"pinochle" were ALSO dropped (2026-06-23):
# they read as senior at the Senior Center (where they carry the `senior` tag, so
# the tag path catches them) but are common general bar/community game nights
# ("Uncorked Bunco" at a bar, "Red, White & Blue Bunco Party") that must NOT be
# pulled into the Seniors group on the title word alone — decide senior membership
# by PROVIDER/venue + tags, not a bare game name.
_SENIOR_TITLE_RE = re.compile(
    r"\b("
    r"senior|seniors|55\s*\+|meals\s+on\s+wheels|older\s+adults?|"
    r"tai\s+chi|qigong|silver\s+sneakers|low[\s-]impact|arthritis|"
    r"water\s+wellness"
    r")\b",
    re.IGNORECASE,
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
    """True when the occurrence positively reads as a seniors thing.

    Senior membership is decided by, in order: (1) a senior TAG (the senior-center
    loader stamps ``senior`` on every row); (2) a senior PROVIDER/venue (the Senior
    Center and like programs — so a generically-named program published there still
    routes to Seniors); (3) an explicit senior-program TITLE word. The venue path
    is why a generic "Exercise Class" at the Senior Center is senior while the same
    title elsewhere is not — the brief's "decide by provider + tags, not just the
    literal word in the title".
    """
    for tag in tags or []:
        if isinstance(tag, str) and tag.strip().lower() in _SENIOR_TAGS:
            return True
    vlow = (venue or "").lower()
    if vlow and any(h in vlow for h in _SENIOR_VENUE_HINTS):
        return True
    t = (title or "").strip()
    if t and _SENIOR_TITLE_RE.search(t):
        return True
    return False
