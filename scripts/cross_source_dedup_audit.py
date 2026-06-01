"""All-sources live-row duplicate audit (READ-ONLY).

Generalizes the single-source golakehavasu_dedup_audit into a sweep over ALL
live catalog rows, finding likely-duplicate pairs that already exist across
sources (the gap at-ingest reconciliation cannot close -- see
CROSS_SOURCE_DEDUP_SESSION.md).

Providers: every LIVE provider (is_active AND NOT draft) is paired against every
other and scored by the strongest signal:

  * same google_place_id            -> reason "google_place_id", definite
  * same normalized website domain  -> reason "website",        definite
  * same last-10-digit phone        -> reason "phone",          definite
  * geo <=50m AND fuzzy name >= T    -> reason "geo+name",       review

The first three are identity signals (action "auto_merge_eligible"); the geo+name
tier is heuristic (action "needs_review"). This matches the resolution policy:
definite identity matches can later auto-merge, fuzzy/geo go to a human.

Events: every LIVE event is paired with same-date events whose venue matches and
whose fuzzy title clears the threshold (mirrors app/events/dedup semantics) ->
reason "event:date+venue+title", action "needs_review".

WRITES NOTHING. Emits a ranked CSV (keep-row, dup-row, reason, score, action)
plus a printed summary. The keep/dup split uses SOURCE_PRIORITY (lower wins),
tie-broken by google_place_id presence, verified, then older created_at -- this
is advisory only; nothing is merged here. The actual merge belongs to the
Item C merge primitive, which can consume this report.

O(n^2) is acceptable for the current ~2-3k catalog. Identity tiers are grouped
in O(n); the geo+name tier gates an O(n^2) scan behind a cheap haversine check
before scoring fuzzy names.

Usage:
    python scripts/cross_source_dedup_audit.py --out providers_dups.csv
    python scripts/cross_source_dedup_audit.py --events --out events_dups.csv
    python scripts/cross_source_dedup_audit.py --fuzzy-threshold 88 --limit 500
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rapidfuzz import fuzz  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.ingest_reconciler import (  # noqa: E402
    GEO_PROXIMITY_THRESHOLD_M,
    SOURCE_PRIORITY,
    haversine_m,
    slugify,
)
from app.utils.contact_norm import norm_domain as _norm_domain  # noqa: E402
from app.utils.contact_norm import norm_phone as _norm_phone  # noqa: E402

DEFAULT_FUZZY_THRESHOLD = 88.0

# An identity key (phone / website / google_place_id) shared by more than this
# many LIVE rows is almost never N copies of one business -- it is a shared
# switchboard number, an umbrella/booking domain, or a bad backfill (e.g. the
# visitor-center phone stamped on every partner). The first prod run proved this:
# 185 providers produced 1366 phone "pairs" -- one number on ~53 rows. Such a key
# must NOT mint auto_merge_eligible pairs (a resolve pass would fuse ~53 distinct
# businesses). Groups at or below the cap pair normally; oversized groups are
# pulled out and reported as shared-key data-quality flags instead. Tune via
# --max-group-size; raise it only if a venue legitimately has that many distinct
# sub-listings on one line.
DEFAULT_MAX_GROUP_SIZE = 4

# Only google_place_id is strong enough to auto-merge: it is a single global
# identity for one real-world place. website and phone are SOFT -- a hospitality
# group, plaza, or the CVB's own listings routinely share one domain or one
# phone across DISTINCT venues (real prod data: WET Pool Bar / Naked Turtle /
# Turtle Grille are three different bars at one resort, 0m apart, same domain).
# So website + phone are reported as needs_review for a human, never auto. (Geo
# proximity does NOT help here -- co-located sub-venues are exactly the false
# positives, so corroborating website-by-geo would rubber-stamp them.) phone is
# additionally protected upstream by the shared-key cap.
_AUTO_REASONS = {"google_place_id"}

# Strongest signal wins for a pair, regardless of fuzz score. geo+name can score
# 100 on identical names but must never override a definite identity key.
_REASON_TIER: dict[str, int] = {
    "google_place_id": 4,
    "website": 3,
    "phone": 2,
    "geo+name": 1,
}


def _min_source_priority(source: str | None) -> int:
    parts = [p.strip() for p in (source or "").split(",") if p.strip()]
    if not parts:
        return 99
    return min(SOURCE_PRIORITY.get(p, 99) for p in parts)


# --------------------------------------------------------------------------- #
# Pure scoring core (no DB) -- unit-tested directly.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProvRow:
    id: str
    name: str
    source: str | None
    website: str | None
    phone: str | None
    lat: float | None
    lng: float | None
    google_place_id: str | None
    verified: bool = False
    created_at: datetime | None = None


@dataclass(frozen=True)
class CandidatePair:
    score: float
    reason: str
    action: str
    keep_id: str
    keep_name: str
    keep_source: str | None
    dup_id: str
    dup_name: str
    dup_source: str | None
    distance_m: float | None


@dataclass(frozen=True)
class SharedKey:
    """An identity key shared by more rows than the cap -- a data-quality flag,
    not a duplicate set. Excluded from auto-merge pairing on purpose."""

    reason: str  # phone | website | google_place_id
    key: str
    count: int
    sample_names: tuple[str, ...]


def _order_keep_dup(a: ProvRow, b: ProvRow) -> tuple[ProvRow, ProvRow]:
    """Advisory survivor selection: lower SOURCE_PRIORITY wins, then has
    google_place_id, then verified, then older created_at, then id for stability.
    """

    def key(r: ProvRow) -> tuple:
        return (
            _min_source_priority(r.source),
            0 if r.google_place_id else 1,
            0 if r.verified else 1,
            r.created_at or datetime.max,
            r.id,
        )

    return (a, b) if key(a) <= key(b) else (b, a)


def _pair_for(a: ProvRow, b: ProvRow, *, reason: str, score: float) -> CandidatePair:
    keep, dup = _order_keep_dup(a, b)
    dist: float | None = None
    if None not in (keep.lat, keep.lng, dup.lat, dup.lng):
        dist = haversine_m(keep.lat, keep.lng, dup.lat, dup.lng)
    action = "auto_merge_eligible" if reason in _AUTO_REASONS else "needs_review"
    return CandidatePair(
        score=round(score, 1),
        reason=reason,
        action=action,
        keep_id=keep.id,
        keep_name=keep.name,
        keep_source=keep.source,
        dup_id=dup.id,
        dup_name=dup.name,
        dup_source=dup.source,
        distance_m=None if dist is None else round(dist, 1),
    )


def find_provider_pairs(
    rows: list[ProvRow],
    *,
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    max_group_size: int = DEFAULT_MAX_GROUP_SIZE,
) -> tuple[list[CandidatePair], list[SharedKey]]:
    """Return (ranked candidate-duplicate pairs, shared-key flags).

    Each unordered pair appears once, tagged with its strongest signal (identity
    tiers beat geo+name). Identity keys shared by more than ``max_group_size``
    rows are NOT paired -- they are returned as :class:`SharedKey` flags, because
    a key on that many live rows is a shared switchboard / umbrella domain / bad
    backfill rather than N copies of one business.
    """
    best: dict[frozenset[str], CandidatePair] = {}

    def consider(a: ProvRow, b: ProvRow, reason: str, score: float) -> None:
        if a.id == b.id:
            return
        key = frozenset((a.id, b.id))
        prev = best.get(key)
        tier = _REASON_TIER.get(reason, 0)
        if prev is None:
            best[key] = _pair_for(a, b, reason=reason, score=score)
            return
        prev_tier = _REASON_TIER.get(prev.reason, 0)
        if tier > prev_tier or (tier == prev_tier and score > prev.score):
            best[key] = _pair_for(a, b, reason=reason, score=score)

    # Identity tiers: group by key in O(n), pair within each group.
    by_gpid: dict[str, list[ProvRow]] = {}
    by_web: dict[str, list[ProvRow]] = {}
    by_phone: dict[str, list[ProvRow]] = {}
    for r in rows:
        if r.google_place_id:
            by_gpid.setdefault(r.google_place_id.strip(), []).append(r)
        w = _norm_domain(r.website)
        if w:
            by_web.setdefault(w, []).append(r)
        p = _norm_phone(r.phone)
        if p:
            by_phone.setdefault(p, []).append(r)

    shared: list[SharedKey] = []
    for group, reason, score in (
        (by_gpid, "google_place_id", 100.0),
        (by_web, "website", 99.0),
        (by_phone, "phone", 98.0),
    ):
        for key, members in group.items():
            if len(members) < 2:
                continue
            if len(members) > max_group_size:
                shared.append(
                    SharedKey(
                        reason=reason,
                        key=key,
                        count=len(members),
                        sample_names=tuple((m.name or "").strip() for m in members[:5]),
                    )
                )
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    consider(members[i], members[j], reason, score)

    # Geo + fuzzy name tier: cheap haversine gate, then fuzz on the survivors.
    geo_rows = [r for r in rows if r.lat is not None and r.lng is not None]
    slugs = {r.id: slugify(r.name or "") for r in geo_rows}
    for i in range(len(geo_rows)):
        a = geo_rows[i]
        for j in range(i + 1, len(geo_rows)):
            b = geo_rows[j]
            if haversine_m(a.lat, a.lng, b.lat, b.lng) > GEO_PROXIMITY_THRESHOLD_M:
                continue
            if not slugs[a.id] or not slugs[b.id]:
                continue
            ratio = float(
                fuzz.token_sort_ratio(
                    (a.name or "").strip().lower(), (b.name or "").strip().lower()
                )
            )
            if ratio >= fuzzy_threshold:
                consider(a, b, "geo+name", ratio)

    pairs = sorted(best.values(), key=lambda c: c.score, reverse=True)
    shared.sort(key=lambda s: s.count, reverse=True)
    return pairs, shared


# --------------------------------------------------------------------------- #
# DB loaders + report.
# --------------------------------------------------------------------------- #
def _load_provider_rows(limit: int | None) -> list[ProvRow]:
    from app.db.database import SessionLocal
    from app.db.models import Provider

    out: list[ProvRow] = []
    with SessionLocal() as session:
        stmt = select(Provider).where(Provider.is_active.is_(True), Provider.draft.is_(False))
        rows = session.scalars(stmt).all()
        if limit is not None:
            rows = rows[:limit]
        for p in rows:
            out.append(
                ProvRow(
                    id=p.id,
                    name=p.provider_name or "",
                    source=p.source,
                    website=p.website,
                    phone=p.phone,
                    lat=p.lat,
                    lng=p.lng,
                    google_place_id=p.google_place_id,
                    verified=bool(p.verified),
                    created_at=p.created_at,
                )
            )
    return out


def _write_provider_csv(pairs: list[CandidatePair], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "rank",
                "score",
                "reason",
                "action",
                "keep_id",
                "keep_name",
                "keep_source",
                "dup_id",
                "dup_name",
                "dup_source",
                "distance_m",
            ]
        )
        for rank, c in enumerate(pairs, start=1):
            w.writerow(
                [
                    rank,
                    c.score,
                    c.reason,
                    c.action,
                    c.keep_id,
                    c.keep_name,
                    c.keep_source or "",
                    c.dup_id,
                    c.dup_name,
                    c.dup_source or "",
                    "" if c.distance_m is None else c.distance_m,
                ]
            )


def _write_shared_keys_csv(shared: list[SharedKey], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["reason", "key", "count", "sample_names"])
        for s in shared:
            w.writerow([s.reason, s.key, s.count, " | ".join(s.sample_names)])


def _summarize(pairs: list[CandidatePair], shared: list[SharedKey]) -> None:
    by_reason: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for c in pairs:
        by_reason[c.reason] = by_reason.get(c.reason, 0) + 1
        by_action[c.action] = by_action.get(c.action, 0) + 1
    print("\n--- cross-source dedup audit summary ---")
    print(f"candidate_pairs: {len(pairs)}")
    for k in sorted(by_reason):
        print(f"  reason {k}: {by_reason[k]}")
    for k in sorted(by_action):
        print(f"  action {k}: {by_action[k]}")
    if shared:
        print(f"shared_keys (excluded as data-quality flags): {len(shared)}")
        for s in shared[:10]:
            sample = ", ".join(s.sample_names[:3])
            print(f"  {s.reason} shared by {s.count} rows [{s.key}]: {sample} ...")
    print("(read-only: no DB writes)")


# --------------------------------------------------------------------------- #
# Events sweep (read-only).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EventPairRow:
    rank: int
    score: float
    keep_id: str
    keep_title: str
    keep_source: str | None
    dup_id: str
    dup_title: str
    dup_source: str | None
    event_date: str
    venue: str


def find_event_pairs(limit: int | None, fuzzy_threshold: float) -> list[EventPairRow]:
    from app.db.database import SessionLocal
    from app.db.models import Event
    from app.events.scrapers.base import normalize_event_title

    out: list[EventPairRow] = []
    with SessionLocal() as session:
        stmt = select(Event).where(Event.status == "live")
        rows = list(session.scalars(stmt).all())
        if limit is not None:
            rows = rows[:limit]
        by_date: dict[Any, list[Event]] = {}
        for e in rows:
            by_date.setdefault(e.date, []).append(e)
        seen: set[frozenset[str]] = set()
        for day, evs in by_date.items():
            for i in range(len(evs)):
                a = evs[i]
                for j in range(i + 1, len(evs)):
                    b = evs[j]
                    same_venue = (a.entity_id and a.entity_id == b.entity_id) or (
                        (a.location_normalized or "").strip() != ""
                        and (a.location_normalized or "").strip()
                        == (b.location_normalized or "").strip()
                    )
                    if not same_venue:
                        continue
                    ratio = float(
                        fuzz.token_sort_ratio(
                            normalize_event_title(a.normalized_title or a.title),
                            normalize_event_title(b.normalized_title or b.title),
                        )
                    )
                    if ratio < fuzzy_threshold:
                        continue
                    key = frozenset((a.id, b.id))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(
                        EventPairRow(
                            rank=0,
                            score=round(ratio, 1),
                            keep_id=a.id,
                            keep_title=a.title,
                            keep_source=a.source,
                            dup_id=b.id,
                            dup_title=b.title,
                            dup_source=b.source,
                            event_date=str(day),
                            venue=a.location_name or "",
                        )
                    )
    out.sort(key=lambda r: r.score, reverse=True)
    return [EventPairRow(**{**r.__dict__, "rank": i}) for i, r in enumerate(out, 1)]


def _write_event_csv(rows: list[EventPairRow], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "rank",
                "score",
                "action",
                "keep_id",
                "keep_title",
                "keep_source",
                "dup_id",
                "dup_title",
                "dup_source",
                "event_date",
                "venue",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.rank,
                    r.score,
                    "needs_review",
                    r.keep_id,
                    r.keep_title,
                    r.keep_source or "",
                    r.dup_id,
                    r.dup_title,
                    r.dup_source or "",
                    r.event_date,
                    r.venue,
                ]
            )


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only cross-source duplicate audit")
    p.add_argument("--events", action="store_true", help="Audit events instead of providers")
    p.add_argument("--out", default=None, help="CSV output path")
    p.add_argument("--limit", type=int, default=None, help="Cap rows scanned")
    p.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=DEFAULT_FUZZY_THRESHOLD,
        help="token_sort_ratio floor (0-100) for the fuzzy tier",
    )
    p.add_argument(
        "--max-group-size",
        type=int,
        default=DEFAULT_MAX_GROUP_SIZE,
        help="identity keys (phone/website/gpid) shared by more rows than this "
        "are reported as shared-key flags, not paired (providers only)",
    )
    args = p.parse_args()

    if args.events:
        rows = find_event_pairs(args.limit, args.fuzzy_threshold)
        out_path = Path(args.out or "events_dup_candidates.csv")
        _write_event_csv(rows, out_path)
        print(f"event candidate pairs: {len(rows)}")
        print(f"wrote {out_path}")
        print("(read-only: no DB writes)")
        return 0

    prov_rows = _load_provider_rows(args.limit)
    pairs, shared = find_provider_pairs(
        prov_rows,
        fuzzy_threshold=args.fuzzy_threshold,
        max_group_size=args.max_group_size,
    )
    out_path = Path(args.out or "provider_dup_candidates.csv")
    _write_provider_csv(pairs, out_path)
    print(f"providers scanned: {len(prov_rows)}")
    print(f"wrote {out_path}")
    if shared:
        shared_path = out_path.with_name(out_path.stem + "_shared_keys.csv")
        _write_shared_keys_csv(shared, shared_path)
        print(f"wrote {shared_path}")
    _summarize(pairs, shared)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
