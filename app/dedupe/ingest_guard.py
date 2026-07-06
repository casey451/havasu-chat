"""Dedupe-on-ingest guard (T2.2).

The S1 clustering engine (:mod:`app.dedupe.cluster`) cleans EXISTING duplicates;
this stops NEW ones. Before a scraper inserts a fresh Provider, this checks the
same-business signals the reconciler's geo/name tiers miss: a shared name +
street address, or a shared name + phone. On a UNIQUE match it returns the
existing entity so the caller updates it instead of minting a second slug.

High precision by design: it fires only when EXACTLY ONE active provider matches
(zero or many -> ``None``, caller falls through to its normal decision), and only
on the strong name+address / name+phone signals — never name alone (the
reconciler already treats a bare name match as ``ambiguous``). Reuses the S1
normalizers so ingest-time matching and catalog clustering agree.
"""

from __future__ import annotations

from typing import Any

from app.dedupe.cluster import address_key, name_key, phone_key


def find_ingest_duplicate(
    db: Any, *, name: str | None, address: str | None, phone: str | None
) -> str | None:
    """Return the entity_id of the UNIQUE active provider that is the same
    business as ``(name, address, phone)`` by name+address or name+phone, else
    ``None``."""
    from app.db.models import Provider

    nk = name_key(name)
    if not nk:
        return None
    ak = address_key(address)
    pk = phone_key(phone)
    if ak is None and pk is None:
        return None  # nothing strong enough to match on

    # Column-only scan (mirrors the reconciler's contact tier): the normalizers
    # run in Python, but hydrating every active Provider per payload is the cost
    # to avoid.
    rows = db.query(
        Provider.entity_id, Provider.provider_name, Provider.address, Provider.phone
    ).filter(Provider.is_active.is_(True), Provider.entity_id.isnot(None))

    matches: set[str] = set()
    for entity_id, prov_name, prov_addr, prov_phone in rows:
        if name_key(prov_name) != nk:
            continue
        if (ak is not None and address_key(prov_addr) == ak) or (
            pk is not None and phone_key(prov_phone) == pk
        ):
            matches.add(entity_id)
    return next(iter(matches)) if len(matches) == 1 else None
