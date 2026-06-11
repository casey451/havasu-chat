"""Category synonym + singularization helpers for Tier 2 retrieval (Phase 2B.2).

Extracted from ``tier2_db_query`` so ``app/search/*`` can consume
:func:`_category_needle_set` without importing the full query module (avoids
import cycles with ``app.search.sqlite_fallback``).
"""

from __future__ import annotations


def _singularize_category(cat: str) -> str:
    """Strip a regular trailing-s plural from the LAST token; leave others alone.

    Slice D fix: queries like "any good coffee shops" arrive as the plural form, but
    Google tags places as ``coffee_shop`` (singular). Without singularization the
    matcher misses everything. Conservative: skip short words and common irregular
    endings ('ss'/'us'/'is') so we don't break "address" or "campus".
    """
    parts = cat.strip().split()
    if not parts:
        return cat
    last = parts[-1]
    if len(last) < 4:
        return cat
    if last.endswith("ies"):
        parts[-1] = last[:-3] + "y"
        return " ".join(parts)
    if last.endswith(("ss", "us", "is")):
        return cat
    if last.endswith("s"):
        parts[-1] = last[:-1]
        return " ".join(parts)
    return cat


# Voice battery 2026-05-08 (§4.2 synonym map): equivalence groups for category
# names that the strict primary-category filter would otherwise miss. Each group
# is a small set of mutually interchangeable terms — when a user query category
# matches any term in a group, all other members are also tried as needles
# against ``Provider.category`` and the normalized ``google_primary_category``.
#
# Conservative — only well-evidenced equivalences. The brief flags that
# "coffee shop" misses providers tagged ``cafe`` (Google's primary type),
# "barbershop" misses ``barber``, and "corner store" misses ``convenience_store``.
# Pharmacy/drugstore and mechanic/auto-repair are added on the same logic
# (Google primary types are ``drugstore`` and ``car_repair`` respectively).
# Add new groups as recall gaps surface in chat_logs / voice battery FAILs.
_CATEGORY_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"coffee shop", "coffee shops", "coffee", "cafe", "cafes"}),
    frozenset({"barber", "barbers", "barbershop", "barbershops", "barber shop", "barber shops"}),
    frozenset(
        {"corner store", "corner stores", "convenience store", "convenience stores", "convenience"}
    ),
    frozenset({"pharmacy", "pharmacies", "drugstore", "drugstores", "drug store", "drug stores"}),
    frozenset({"mechanic", "mechanics", "auto repair", "car repair", "auto shop", "auto shops"}),
    # trades — demand-proven (hunt 2026-06-10); singular forms were dead at Tier-3
    frozenset({"plumber", "plumbers", "plumbing", "leak repair"}),
    frozenset({"electrician", "electricians", "electrical contractor", "electrical"}),
    frozenset({"hvac", "ac repair", "air conditioning", "heating and cooling", "swamp cooler"}),
    # health
    frozenset({"chiropractor", "chiropractors", "chiropractic"}),
    frozenset({"physical therapy", "physical therapist", "physiotherapist", "physio", "rehab"}),
    # retail/fun
    frozenset({"beauty salon", "hair salon", "salon", "barber", "barbershop"}),
    frozenset({"car dealer", "car dealership", "auto dealer", "dealership"}),
    frozenset({"bowling", "bowling alley", "lanes"}),
)


def _category_synonyms(cat: str) -> tuple[str, ...]:
    """Return all equivalent category terms for ``cat`` (including ``cat`` itself).

    Lookup is case-insensitive and exact-match (whole string). If ``cat`` is in a
    synonym group, returns the full group as a deterministic tuple. Otherwise
    returns ``(cat,)`` so callers can iterate uniformly.
    """
    c = (cat or "").strip().lower()
    if not c:
        return ()
    for group in _CATEGORY_SYNONYM_GROUPS:
        if c in group:
            return tuple(sorted(group))
    return (c,)


def _category_needle_set(cat: str) -> tuple[str, ...]:
    """Build the full needle set for a category: synonyms × singularized forms.

    Combines :func:`_category_synonyms` with :func:`_singularize_category` so
    "coffee shops" expands to {coffee shops, coffee shop, cafe, cafes, cafe, coffee},
    deduplicated. Empty strings are dropped.
    """
    c = (cat or "").strip().lower()
    if not c:
        return ()
    out: set[str] = set()
    seeds = {c, _singularize_category(c)}
    for seed in seeds:
        for syn in _category_synonyms(seed):
            out.add(syn)
            sing = _singularize_category(syn)
            if sing:
                out.add(sing)
    out.discard("")
    return tuple(sorted(out))
