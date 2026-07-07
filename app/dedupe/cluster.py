"""Dedupe clustering engine (S1).

A pure function that clusters :class:`ProviderRecord` rows into "same real
business" groups. Reused by the catalog-cleanup script (``scripts.dedupe_catalog``,
T2.1) and — later — the dedupe-on-ingest guard (T2.2).

Signals, in priority order (a match on ANY unions two records into one cluster):
  1. ``google_place_id`` equal (hard match — definitive).
  2. Normalized name + normalized street address equal.
  3. Normalized name + normalized phone equal.
  4. Slug-family: trailing ``-N`` name variant (``x`` vs ``x-2``), or a token-subset
     name match at the SAME address (``denny-s`` vs ``denny-s-restaurant``).

Per cluster the engine emits the **primary** (the row to keep) plus the **members**
and a best-guess **relationship type**:
  * ``duplicate``     — same business, one storefront → retire the clones.
  * ``multi_location``— same name at DIFFERENT addresses → keep both, share a group.
  * ``parent_child``  — a parent org + a longer name that adds a person/department.

The engine only PROPOSES; it never writes. ``relationship_type`` is a heuristic for
a human to confirm (T2.1 writes a report Casey approves). Normalization reuses the
ingest reconciler's ``slugify`` + ``contact_norm.norm_phone`` and ``core.address.
street_line`` so clustering and ingest-time matching agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.contrib.ingest_reconciler import slugify
from app.core.address import street_line
from app.utils.contact_norm import norm_phone

# Tokens that mark the extra words of a longer name as a person/department/amenity
# rather than a different business — used to call a token-superset a parent/child
# (an anchor store + its departments, a resort + its amenities, a practice + its
# providers) instead of a duplicate to RETIRE. Retiring a "Safeway Pharmacy" or
# "JCPenney Optical" would drop a service people search for, so these are kept.
_PARENT_CHILD_HINTS: frozenset[str] = frozenset(
    {
        # people / credentials (practice + provider)
        "dr", "md", "do", "dds", "dmd", "pa", "np", "phd", "esq", "cpa", "realtor",
        # departments / sub-brands of an anchor store
        "department", "dept", "parts", "service", "sales", "office", "center",
        "pharmacy", "deli", "bakery", "liquor", "fuel", "salon", "optical",
        "cafe", "bar", "grill", "tea", "taproom", "spa", "clinic", "lab",
    }
)

# WS4 generic-subset signal. When two rows at the SAME address have names where
# one is a token-subset of the other and the EXTRA words are all generic cuisine
# /venue descriptors, they are the same business — the GLH-import twin shape
# ("Denny's" vs "Denny's Restaurant", "Filiberto's" vs "Filiberto's Mexican
# Food"). Unlike the token-subset signal below this needs NO phone, because a
# plaza never lists a bare name AND that name + a cuisine word as two tenants.
#
# CRITICAL: this set is DISJOINT from ``_PARENT_CHILD_HINTS`` on purpose. Words
# that double as department markers (cafe, bar, grill, taproom, deli, …) are
# deliberately EXCLUDED — "Safeway" vs "Safeway Deli" must stay parent/child, and
# "The Office" vs "The Office ... Grill" stays a review-tier case, not an auto
# merge. Person/credential extras (a broker + a named agent) are never generic,
# so the brokerage-plus-agent false merge stays blocked.
_GENERIC_DESCRIPTORS: frozenset[str] = frozenset(
    {
        "restaurant", "restaurants", "eatery", "diner", "cantina", "cuisine",
        "kitchen", "cocktail", "cocktails", "lounge", "pub", "brewery", "brewing",
        "craft", "arcade", "more", "house", "steakhouse",
        # cuisines / food types
        "mexican", "italian", "chinese", "thai", "japanese", "american", "food",
        "foods", "steak", "pizza", "pizzeria", "pasta", "seafood", "sushi", "bbq",
        "burgers", "coffee", "grille",  # note: "grille" != the "grill" dept hint
    }
)
# Noise tokens dropped before the generic-subset comparison: articles, the "and"
# conjunction (so "Grill & Pub" == "Grill and Pub" after slugify drops the "&"),
# and the lone "s" that slugify leaves from a possessive ("Denny's" -> denny-s).
_SUBSET_STOPWORDS: frozenset[str] = frozenset({"the", "and", "of", "a", "an", "at", "s"})

_SUITE_RE = re.compile(
    r"\b(?:ste|suite|unit|apt|apartment|bldg|building|fl|floor|rm|room)\b\s*#?\s*[\w-]+"
    r"|#\s*[\w-]+",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TRAILING_INT_RE = re.compile(r"-\d+$")


@dataclass(frozen=True)
class ProviderRecord:
    """The minimal Provider projection the clusterer needs."""

    id: str
    name: str
    address: str | None = None
    phone: str | None = None
    google_place_id: str | None = None
    review_count: int = 0
    verified: bool = False
    slug: str | None = None


@dataclass
class Cluster:
    """One "same real business" group proposed by the engine."""

    primary: ProviderRecord
    members: list[ProviderRecord]  # every row in the cluster, primary included
    relationship_type: str  # "duplicate" | "multi_location" | "parent_child"
    reason: str

    @property
    def clones(self) -> list[ProviderRecord]:
        """The non-primary members (the rows a ``duplicate`` cluster retires)."""
        return [m for m in self.members if m.id != self.primary.id]


def name_key(name: str | None) -> str:
    """Canonical name key (reuses the ingest reconciler's slugify)."""
    return slugify(name or "")


def _name_base(key: str) -> str:
    """Drop a trailing ``-N`` disambiguator: ``joes-bar-2`` -> ``joes-bar``."""
    return _TRAILING_INT_RE.sub("", key)


def _name_tokens(key: str) -> frozenset[str]:
    return frozenset(t for t in key.split("-") if t)


def _generic_subset_match(ka: str, kb: str) -> bool:
    """True when two name keys (at the same address) are the same business modulo
    generic descriptor words — the WS4 GLH-twin rule.

    After dropping stopwords, one token core must equal or be a subset of the
    other, and every extra token must be a generic cuisine/venue descriptor. A
    person name, department word, or any non-generic token makes it False, so the
    strict phone-gated token-subset path (below) still handles those.
    """
    ta = _name_tokens(ka) - _SUBSET_STOPWORDS
    tb = _name_tokens(kb) - _SUBSET_STOPWORDS
    if not ta or not tb:
        return False
    if ta == tb:
        return True  # identical cores once articles/"and"/possessive-s are gone
    if ta <= tb:
        extras = tb - ta
    elif tb <= ta:
        extras = ta - tb
    else:
        return False
    return bool(extras) and extras <= _GENERIC_DESCRIPTORS


def address_key(address: str | None) -> str | None:
    """Street-level address key: street line only, suite/unit stripped, folded."""
    if not address:
        return None
    street = street_line(address) or address
    street = _SUITE_RE.sub(" ", street.lower())
    folded = _NON_ALNUM_RE.sub(" ", street).strip()
    return folded or None


def phone_key(phone: str | None) -> str | None:
    """Canonical phone key (reuses contact_norm.norm_phone)."""
    return norm_phone(phone)


class _UnionFind:
    def __init__(self, ids: list[str]) -> None:
        self._parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:  # path compression
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def _bucket_union(uf: _UnionFind, buckets: dict) -> None:
    for members in buckets.values():
        first = members[0]
        for other in members[1:]:
            uf.union(first, other)


def cluster_providers(records: list[ProviderRecord]) -> list[Cluster]:
    """Cluster records into same-business groups; return one :class:`Cluster` per
    group of size >= 2 (singletons are not returned — nothing to reconcile)."""
    if not records:
        return []
    by_id = {r.id: r for r in records}
    uf = _UnionFind(list(by_id))

    # Signal 1: google_place_id equal.
    gpid_buckets: dict[str, list[str]] = {}
    # Signal 2: name + address equal.
    name_addr_buckets: dict[tuple[str, str], list[str]] = {}
    # Signal 3: name + phone equal.
    name_phone_buckets: dict[tuple[str, str], list[str]] = {}
    for r in records:
        nk = name_key(r.name)
        if r.google_place_id:
            gpid_buckets.setdefault(r.google_place_id, []).append(r.id)
        ak = address_key(r.address)
        if nk and ak:
            name_addr_buckets.setdefault((nk, ak), []).append(r.id)
        pk = phone_key(r.phone)
        if nk and pk:
            name_phone_buckets.setdefault((nk, pk), []).append(r.id)
    _bucket_union(uf, gpid_buckets)
    _bucket_union(uf, name_addr_buckets)
    _bucket_union(uf, name_phone_buckets)

    # Signal 4: slug-family within a shared address (trailing -N or token-subset).
    # PRECISION GUARD: at a shared plaza address, many DISTINCT businesses share a
    # common token (a brokerage + its agents, an anchor store + an unrelated salon
    # inside it). Phone is the disambiguator:
    #   * trailing "-N" variant (x vs x-2) is a strong re-scrape dup signal — union
    #     when phones are compatible (equal, or at least one missing).
    #   * a token-subset name (denny-s vs denny-s-restaurant) is weaker — union ONLY
    #     when BOTH rows carry the SAME phone, so different-phone agents/vendors at
    #     one address are never falsely merged.
    by_addr: dict[str, list[ProviderRecord]] = {}
    for r in records:
        ak = address_key(r.address)
        if ak:
            by_addr.setdefault(ak, []).append(r)
    for group in by_addr.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                ka, kb = name_key(a.name), name_key(b.name)
                if not ka or not kb:
                    continue
                pa, pb = phone_key(a.phone), phone_key(b.phone)
                if _name_base(ka) == _name_base(kb):
                    if pa is None or pb is None or pa == pb:  # phones compatible
                        uf.union(a.id, b.id)
                    continue
                # WS4: same business modulo generic descriptor words (GLH twin) —
                # unions with no phone because the extras can't be a distinct
                # tenant (a person, a department); precision-guarded by the
                # generic-only extras rule.
                if _generic_subset_match(ka, kb):
                    uf.union(a.id, b.id)
                    continue
                ta, tb = _name_tokens(ka), _name_tokens(kb)
                if ta and tb and (ta <= tb or tb <= ta):
                    if pa is not None and pa == pb:  # strict: same phone required
                        uf.union(a.id, b.id)

    # Assemble components.
    comps: dict[str, list[ProviderRecord]] = {}
    for r in records:
        comps.setdefault(uf.find(r.id), []).append(r)

    clusters: list[Cluster] = []
    for members in comps.values():
        if len(members) < 2:
            continue
        primary = _pick_primary(members)
        rel, reason = _classify(members, primary)
        clusters.append(
            Cluster(primary=primary, members=members, relationship_type=rel, reason=reason)
        )
    # Stable order: largest clusters first, then by primary name.
    clusters.sort(key=lambda c: (-len(c.members), name_key(c.primary.name)))
    return clusters


def _pick_primary(members: list[ProviderRecord]) -> ProviderRecord:
    """The row to keep: prefer a google_place_id, then verified, then most reviews,
    then a stable id tiebreak."""
    return sorted(
        members,
        key=lambda r: (
            r.google_place_id is None,  # False (has id) sorts first
            not r.verified,
            -int(r.review_count or 0),
            str(r.id),
        ),
    )[0]


def _classify(members: list[ProviderRecord], primary: ProviderRecord) -> tuple[str, str]:
    """Best-guess relationship type for a cluster (a human confirms it).

    * Distinct non-null addresses among same-named members -> ``multi_location``.
    * A token-superset name whose extra words are a person/department -> ``parent_child``.
    * Otherwise -> ``duplicate``.
    """
    addrs = {address_key(m.address) for m in members if address_key(m.address)}
    keys = {name_key(m.name) for m in members}
    if len(addrs) > 1 and len(keys) == 1:
        return ("multi_location", "same name at multiple distinct addresses")

    # "X at Y" / "X @ Y" names an amenity located inside the parent venue (a pub
    # at a bowling alley, a dog park at a beach). Keep it as a child rather than
    # retire it — biasing an ambiguous cluster toward KEEP is the safe direction.
    for m in members:
        if m.id == primary.id:
            continue
        low = f" {m.name.lower()} "
        if " at " in low or " @ " in low:
            return ("parent_child", "a member is an amenity located 'at' the parent venue")

    prim_tokens = _name_tokens(name_key(primary.name))
    for m in members:
        if m.id == primary.id:
            continue
        mt = _name_tokens(name_key(m.name))
        extra = mt - prim_tokens
        if prim_tokens and prim_tokens <= mt and extra & _PARENT_CHILD_HINTS:
            return ("parent_child", "a member name extends the parent with a person/department")

    if len(addrs) > 1:
        return ("multi_location", "members span multiple addresses")
    return ("duplicate", "same business (name/address/phone/slug-family match)")
