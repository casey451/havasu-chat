"""Find near-duplicate entities for HUMAN REVIEW (read-only; never writes).

``dedup_entities.py`` is deliberately chain-safe: it only collapses rows proven
to be the same physical venue (same google_place_id, or same name+address). That
leaves a residue — duplicates whose rows have *different* place_ids or addresses
(Google held two listings for one place, or a bad import used a wrong address),
e.g. the straggler "The Spot" / "Havasu Lanes" rows. Those can't be auto-merged
without risking collapsing a real second location, so this tool surfaces them for
a person to decide.

It clusters ACTIVE non-event entities by **normalized name only** (ignoring
place_id/address), then reports every cluster with >1 entity, annotated so a
human can tell a duplicate from a chain:

* ``likely-chain``  — >= 3 distinct addresses (multiple real locations: keep all).
* ``review``        — 2 entities, or <= 2 distinct addresses (probable duplicate;
                      eyeball the addresses and decide).

It writes a CSV and prints a summary. It makes ZERO writes — feed the entity_ids
you confirm as duplicates to ``deactivate_entities.py``.

    .venv\\Scripts\\python.exe scripts\\find_near_dups.py --csv near_dups.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Entity, Location, Provider  # noqa: E402

EXCLUDED_ENTITY_TYPES = frozenset({"event"})


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def classify_cluster(rows: list[dict[str, Any]]) -> str:
    """Label a same-name cluster: 'likely-chain' vs 'review'."""
    addrs = {_norm(r.get("address")) for r in rows if _norm(r.get("address"))}
    if len(addrs) >= 3:
        return "likely-chain"
    return "review"


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(*, csv_path: Path | None = None, session=None) -> Counter:
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
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
            rows.append({
                "entity_id": ent.id, "name": ent.name, "slug": ent.slug,
                "address": (getattr(prov, "address", None) if prov else None)
                or (getattr(loc, "address", None) if loc else None) or "",
                "place_id": (getattr(prov, "google_place_id", None) if prov else None)
                or (getattr(loc, "google_place_id", None) if loc else None) or "",
            })

        by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            n = _norm(r["name"])
            if n:
                by_name[n].append(r)

        report: list[dict[str, Any]] = []
        for members in by_name.values():
            if len(members) < 2:
                continue
            label = classify_cluster(members)
            counts[label] += 1
            for r in members:
                report.append({"label": label, "cluster_size": len(members), **r})

        review = [r for r in report if r["label"] == "review"]
        print(f"name-collision clusters: review={counts.get('review', 0)}  likely-chain={counts.get('likely-chain', 0)}")
        print(f"entities in 'review' clusters (eyeball these): {len(review)}\n")
        shown: set[str] = set()
        for r in sorted(review, key=lambda r: _norm(r["name"]))[:60]:
            tag = _norm(r["name"])
            if tag not in shown:
                shown.add(tag)
                print(f"  {r['name'][:40]:40s} (×{r['cluster_size']})")
            print(f"      - {r['slug'][:34]:34s} addr='{(r['address'] or '')[:34]}' pid={r['place_id'][:12]}")

        if csv_path and report:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
                w.writeheader()
                w.writerows(report)
            print(f"\nwrote {len(report)} rows to {csv_path}  (READ-ONLY — no DB writes)")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Find near-duplicate entities for review (read-only).")
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args(argv)
    run(csv_path=args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
