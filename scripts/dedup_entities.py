"""Deduplicate same-venue entities (DRY-RUN by default; gated).

One physical venue sometimes exists as several ``entities`` rows (Havasu Lanes
×4, The Spot ×4) — each independently categorized, so a leaf shows the same place
several times. This collapses confirmed same-venue duplicates to ONE surviving
entity and soft-deactivates the rest (``is_active = False``, reversible).

**Chain-safe.** Entities are clustered by ``google_place_id`` (from the Provider
or the Location); entities with no place_id fall back to ``normalized(name) +
normalized(address)``. A national chain's locations have DIFFERENT place_ids /
addresses, so they land in different clusters and are never collapsed — only rows
that are the same physical place cluster together.

**Survivor = the richest, safest row** (higher score kept):
    verified Claim (10000) > Provider.verified (5000) > sponsored/paid (4000)
    > has active non-draft Provider (1000) > data completeness (×10)
    > google_review_count (tiebreak).

**Protections.** A non-survivor that is itself claimed / verified / sponsored is
NEVER deactivated — it's reported as a conflict for manual review instead. Only
clearly-redundant rows are deactivated, and reversibly.

DEFAULT IS DRY-RUN: prints the collapse plan + a CSV, writes nothing. ``--apply``
requires ``--confirm``, wraps writes in ONE transaction, and first saves a
rollback snapshot of the deactivated entity ids. Prints the sanitized DB target
every run (the repo .env can point DATABASE_URL at prod).

    .venv\\Scripts\\python.exe scripts\\dedup_entities.py --csv dedup_plan.csv          # DRY RUN
    .venv\\Scripts\\python.exe scripts\\dedup_entities.py --apply --confirm              # writes

PROD GATE (CLAUDE.md): dry-run, show Casey the plan + counts, get approval, THEN a
human runs --apply --confirm. The agent never runs --apply against prod.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Claim, Entity, Location, Provider  # noqa: E402


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Venue dedup is for directory venues only — NEVER events. A recurring event (a
# daily "Lap Swim", a weekly Farmers Market, a civic meeting) legitimately
# exists as many rows that share the same name+address across occurrences, so
# name+address clustering would wrongly collapse an entire schedule into one
# row and gut the events feed. Event de-duplication is a separate, date-aware
# problem handled elsewhere — this tool never touches event rows.
EXCLUDED_ENTITY_TYPES: frozenset[str] = frozenset({"event"})


def is_dedupable_entity_type(entity_type: str | None) -> bool:
    """True if a venue-dedup may consider this entity (everything but events)."""
    return (entity_type or "") not in EXCLUDED_ENTITY_TYPES


def cluster_key(place_id: str | None, name: str | None, address: str | None) -> str | None:
    """Same-venue grouping key, or ``None`` when the row can't be safely clustered.

    A ``google_place_id`` is authoritative (same place_id = same venue). Without
    one, fall back to ``name|address`` — but ONLY when both are present, so two
    rows that merely share a name (a chain) never collapse without a matching
    address too."""
    if place_id:
        return f"pid:{place_id.strip()}"
    n, a = _norm(name), _norm(address)
    if n and a:
        return f"na:{n}|{a}"
    return None


def score_entity(row: dict[str, Any]) -> int:
    """Survivor score — higher is kept. Pure."""
    s = 0
    if row.get("claimed"):
        s += 10000
    if row.get("verified"):
        s += 5000
    if row.get("sponsored"):
        s += 4000
    if row.get("has_provider"):
        s += 1000
    s += int(row.get("completeness") or 0) * 10
    s += int(row.get("review_count") or 0)
    return s


def _is_protected(row: dict[str, Any]) -> bool:
    return bool(row.get("claimed") or row.get("verified") or row.get("sponsored"))


def plan_cluster(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """``(survivor, deactivate, conflicts)`` for one same-venue cluster.

    Survivor is the top-scored row (deterministic tiebreak on entity_id).
    Non-survivors are deactivated unless protected, in which case they go to
    ``conflicts`` (manual review) and are left active."""
    if len(rows) < 2:
        return (rows[0] if rows else None), [], []
    ordered = sorted(rows, key=lambda r: (-score_entity(r), str(r.get("entity_id"))))
    survivor = ordered[0]
    deactivate: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for r in ordered[1:]:
        if _is_protected(r):
            conflicts.append(r)
        else:
            deactivate.append(r)
    return survivor, deactivate, conflicts


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _completeness(p: Provider | None) -> int:
    if p is None:
        return 0
    fields = [p.phone, p.website, p.address, p.hours, p.description]
    n = sum(1 for f in fields if (f or "").strip())
    if getattr(p, "google_photo_urls", None) or getattr(p, "google_photo_refs", None):
        n += 1
    return n


def _load_rows(session) -> list[dict[str, Any]]:
    claimed = {
        eid
        for (eid,) in session.query(Claim.entity_id).filter(Claim.status == "verified")
    }
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    q = (
        session.query(Entity, Provider, Location)
        .outerjoin(Provider, Provider.entity_id == Entity.id)
        .outerjoin(Location, Location.entity_id == Entity.id)
        .filter(
            Entity.is_active.is_(True),
            Entity.entity_type.notin_(EXCLUDED_ENTITY_TYPES),
        )
    )
    for ent, prov, loc in q.all():
        if not is_dedupable_entity_type(ent.entity_type):
            continue  # defensive: events never enter venue dedup
        place_id = (getattr(prov, "google_place_id", None) if prov else None) or (
            getattr(loc, "google_place_id", None) if loc else None
        )
        address = (getattr(prov, "address", None) if prov else None) or (
            getattr(loc, "address", None) if loc else None
        )
        sponsored = False
        if prov is not None:
            tier = (getattr(prov, "tier", "") or "").strip().lower()
            su = getattr(prov, "sponsored_until", None)
            if su is not None and su.tzinfo is None:
                su = su.replace(tzinfo=UTC)
            sponsored = tier not in ("", "free") or (su is not None and su > now)
        rows.append(
            {
                "entity_id": ent.id,
                "name": ent.name,
                "slug": ent.slug,
                "place_id": place_id,
                "address": address,
                "has_provider": prov is not None
                and bool(getattr(prov, "is_active", False))
                and not bool(getattr(prov, "draft", False)),
                "verified": bool(getattr(prov, "verified", False)) if prov else False,
                "claimed": ent.id in claimed,
                "sponsored": sponsored,
                "completeness": _completeness(prov),
                "review_count": getattr(prov, "google_review_count", None) if prov else None,
            }
        )
    return rows


def run(*, apply: bool = False, confirm: bool = False, csv_path: Path | None = None,
        snapshot_dir: Path | None = None, session=None) -> Counter:
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        rows = _load_rows(session)
        counts["active_entities"] = len(rows)

        clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            key = cluster_key(r["place_id"], r["name"], r["address"])
            if key is not None:
                clusters[key].append(r)

        deactivate_rows: list[dict[str, Any]] = []
        conflict_rows: list[dict[str, Any]] = []
        report: list[dict[str, Any]] = []
        for key, members in clusters.items():
            if len(members) < 2:
                continue
            survivor, deact, conflicts = plan_cluster(members)
            if not deact and not conflicts:
                continue
            counts["dup_clusters"] += 1
            for r in deact:
                deactivate_rows.append(r)
                report.append({"action": "deactivate", "cluster": key,
                               "keep": survivor["name"], "keep_slug": survivor["slug"],
                               "entity_id": r["entity_id"], "name": r["name"], "slug": r["slug"]})
            for r in conflicts:
                conflict_rows.append(r)
                report.append({"action": "conflict-review", "cluster": key,
                               "keep": survivor["name"], "keep_slug": survivor["slug"],
                               "entity_id": r["entity_id"], "name": r["name"], "slug": r["slug"]})

        counts["to_deactivate"] = len(deactivate_rows)
        counts["conflicts"] = len(conflict_rows)

        print("dedup plan:")
        print(f"  {counts.get('dup_clusters', 0):>5}  duplicate clusters (>1 same-venue entity)")
        print(f"  {len(deactivate_rows):>5}  entities to deactivate (reversible)")
        print(f"  {len(conflict_rows):>5}  protected conflicts (left active, manual review)")
        print(f"  {counts['active_entities']:>5}  active entities scanned\n")
        for r in report[:30]:
            print(f"  {r['action']:16s} keep '{r['keep'][:28]}' <- drop '{r['name'][:28]}'")

        if csv_path and report:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
                w.writeheader()
                w.writerows(report)
            print(f"\nwrote {len(report)} rows to {csv_path}")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return counts

        ids = [r["entity_id"] for r in deactivate_rows]
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap = snapshot_dir / f"dedup_snapshot_{stamp}.json"
        snap.write_text(json.dumps([{"entity_id": i, "is_active": True} for i in ids], indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap} ({len(ids)} ids)")
        changed = 0
        for ent in session.query(Entity).filter(Entity.id.in_(ids)):
            ent.is_active = False
            changed += 1
        session.commit()
        counts["deactivated"] = changed
        print(f"\nAPPLIED — {changed} duplicate entities deactivated in one transaction.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deduplicate same-venue entities (dry-run by default).")
    ap.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    ap.add_argument("--confirm", action="store_true", help="Required with --apply.")
    ap.add_argument("--csv", type=Path, default=None, help="Write the dedup plan to this CSV.")
    args = ap.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm, csv_path=args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
