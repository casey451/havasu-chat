"""Pure classification core for the source reconciliation job (Part B of the
source-parity plan). No network, no DB — unit-tested in isolation.

Given an external listing/event and pre-built indexes of our providers/events,
classify it ``matched`` / ``miscategorized`` / ``missing`` / ``excluded``.
``scripts/reconcile_sources.py`` (CLI/report) and ``app/contrib/reconcile_live``
(live crawl + DB indexes + ledger persistence) both build on this.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

from app.contrib.source_category_map import (
    OUTSIDE_SERVICE_AREA_REASON,
    is_out_of_area,
    map_business_leaf,
    map_event_category,
    resolve_region,
)


def slugify_name(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def norm_web(url: str | None) -> str | None:
    if not url:
        return None
    s = str(url).strip().lower()
    for pre in ("https://", "http://"):
        if s.startswith(pre):
            s = s[len(pre):]
    if s.startswith("www."):
        s = s[4:]
    return s.rstrip("/") or None


@dataclass
class ReconcileRow:
    source: str
    source_url: str
    source_category: str | None
    name: str | None
    address: str | None
    region: str
    mapped: str | None  # leaf (business) or canonical category (event)
    match_status: str
    matched_id: str | None
    exclusion_reason: str | None


def classify_business(
    *,
    source: str,
    source_url: str,
    name: str | None,
    address: str | None,
    source_category: str | None,
    providers_by_name: dict[str, tuple[str, str | None]],
    providers_by_web: dict[str, tuple[str, str | None]],
    website: str | None = None,
    suppressed_names: frozenset[str] = frozenset(),
) -> ReconcileRow:
    """Classify one external business listing. ``providers_by_*`` map an identity
    key -> (provider_id, current_leaf_slug)."""
    region = resolve_region(address, name)
    mapped = map_business_leaf(source_category, name=name)

    if name and slugify_name(name) in suppressed_names:
        return ReconcileRow(source, source_url, source_category, name, address, region,
                            mapped, "excluded", None, "suppressed")
    if is_out_of_area(region):
        return ReconcileRow(source, source_url, source_category, name, address, region,
                            mapped, "excluded", None, OUTSIDE_SERVICE_AREA_REASON)

    hit = providers_by_name.get(slugify_name(name))
    if hit is None and website:
        hit = providers_by_web.get(norm_web(website) or "")
    if hit is None:
        return ReconcileRow(source, source_url, source_category, name, address, region,
                            mapped, "missing", None, None)

    provider_id, current_leaf = hit
    if mapped and current_leaf and mapped != current_leaf:
        return ReconcileRow(source, source_url, source_category, name, address, region,
                            mapped, "miscategorized", provider_id, None)
    return ReconcileRow(source, source_url, source_category, name, address, region,
                        mapped, "matched", provider_id, None)


def classify_event(
    *,
    source: str,
    source_url: str,
    title: str | None,
    event_date: date | None,
    venue: str | None,
    source_category: str | None,
    events_by_key: dict[tuple[str, str], str],
) -> ReconcileRow:
    """Classify one external event. ``events_by_key`` maps
    (normalized_title, iso-date) -> event_id."""
    region = resolve_region(venue)
    mapped = map_event_category(source_category)
    if is_out_of_area(region):
        return ReconcileRow(source, source_url, source_category, title, venue, region,
                            mapped, "excluded", None, OUTSIDE_SERVICE_AREA_REASON)
    key = (slugify_name(title), event_date.isoformat() if event_date else "")
    event_id = events_by_key.get(key)
    if event_id is None:
        return ReconcileRow(source, source_url, source_category, title, venue, region,
                            mapped, "missing", None, None)
    return ReconcileRow(source, source_url, source_category, title, venue, region,
                        mapped, "matched", event_id, None)


def summarize(rows: list[ReconcileRow]) -> Counter:
    c: Counter = Counter()
    for r in rows:
        c[r.match_status] += 1
        if r.match_status == "excluded" and not r.exclusion_reason:
            c["excluded_without_reason"] += 1
    return c


def invariant_green(counts: Counter) -> bool:
    """The completeness invariant: 0 missing, 0 miscategorized, every excluded
    row has a reason."""
    return (
        counts.get("missing", 0) == 0
        and counts.get("miscategorized", 0) == 0
        and counts.get("excluded_without_reason", 0) == 0
    )
