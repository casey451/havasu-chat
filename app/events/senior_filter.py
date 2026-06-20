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
# explicit senior words, a curated set of unambiguous senior-program signals
# (low-impact / mobility classes + the classic senior-center games) is included
# so senior items arriving WITHOUT a tag still surface. Deliberately excludes
# Lake-Havasu-ambiguous terms: "bridge" (the London Bridge), "billiards",
# "gentle", "line dance" — too broad to imply seniors on their own.
_SENIOR_TITLE_RE = re.compile(
    r"\b("
    r"senior|seniors|55\s*\+|meals\s+on\s+wheels|older\s+adults?|"
    r"tai\s+chi|qigong|silver\s+sneakers|low[\s-]impact|arthritis|"
    r"water\s+wellness|bunco|pinochle"
    r")\b",
    re.IGNORECASE,
)


def is_senior_event(title: str | None, tags: list[str] | None = None) -> bool:
    """True when the occurrence positively reads as a seniors thing."""
    for tag in tags or []:
        if isinstance(tag, str) and tag.strip().lower() in _SENIOR_TAGS:
            return True
    t = (title or "").strip()
    if t and _SENIOR_TITLE_RE.search(t):
        return True
    return False
