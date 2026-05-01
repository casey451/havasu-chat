"""Provider display name normalization for matching and deduplication."""
from __future__ import annotations

import re
import unicodedata


def _norm_provider_name(name: str) -> str:
    """Normalize a provider display name for comparison (dedupe + program backfill).

    Two layers:

    1. **Portable Unicode folding** — NFKC, collapse whitespace, lowercase, map en/em
       dash and minus variants to ASCII hyphen, map curly quotes and apostrophes to
       straight ASCII quotes, strip soft hyphen, replace NBSP with space. Safe for
       any locale; keeps matching stable when master vs. instructions differ only by
       typography.

    2. **Non-portable Lake Havasu section 9 suffix folds** — end-anchored tails used because
       some legacy program-import rows used a shorter provider_name
       than the canonical business header in Section 9 (e.g. trailing (ACPA), - Sonics,
       - Lake Havasu City). Remove these once seed-data
       naming is canonicalized during **Phase 8** seed-data verification (owner phone
       review); then delete the suffix regexes here so normalization stays generic.

    Phase 1.3 uses this for Provider upsert keys; Phase 1.4 backfill imports the same
    function so exact-match keys always agree with the seed.
    """
    s = unicodedata.normalize("NFKC", (name or "").strip())
    for ch in ("\u2013", "\u2014", "\u2012", "\u2015", "\u2212"):
        s = s.replace(ch, "-")
    for old, new in (
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201a", "'"),
        ("\u201b", "'"),
        ("\u2032", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u201e", '"'),
        ("\u2033", '"'),
    ):
        s = s.replace(old, new)
    s = s.replace("\u00a0", " ").replace("\u00ad", "")
    s = " ".join(s.lower().split())
    s = re.sub(r"\s*\(acpa\)\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+-\s+sonics\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+-\s+lake havasu city\s*$", "", s, flags=re.IGNORECASE)
    return " ".join(s.split())
