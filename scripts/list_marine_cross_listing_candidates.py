"""List marine-named hybrid providers missing from the boat-repair leaf page.

READ-ONLY discovery for Issue 1 (2026-06-18). Casey's chosen fix for hybrid
"Auto & Marine" shops is the curated cross-listing map
(``app/categories/cross_listing.py``), NOT a secondary ``entity_categories``
link — leaf pages render only the PRIMARY link and ``cross_listing``
deliberately ignores non-primary rows (stale A.3 migration leftovers).

This script finds the candidates for that map: ACTIVE providers whose NAME
signals MARINE (marine / boat / watercraft / outboard / pontoon / jet-ski) but
whose PRIMARY ``entity_categories`` leaf is NOT ``boat-repair-and-service`` — so
they show on their auto/tire/RV leaf but are missing from the boat-repair leaf.
It prints each candidate's ``Entity.slug`` (the key ``cross_listing`` uses) plus
a ready-to-paste ``frozenset`` snippet.

This script NEVER writes to the DB — there is no ``--apply``. It only reads and
writes a local CSV. Casey runs it against prod, reviews the CSV (dropping any
that aren't genuine marine repair/service — e.g. pure dealers or rentals), and
hands the kept slugs back; step 2 adds them to ``CROSS_LISTED_ENTITY_SLUGS``.

    .venv\\Scripts\\python.exe scripts\\list_marine_cross_listing_candidates.py

Every run prints the sanitized DB target — the repo .env can point DATABASE_URL
at prod, which is exactly what you want for this read-only discovery.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

_TARGET_LEAF = "boat-repair-and-service"

# Marine name signal — word-boundary so an auto shop with "board"/"arctic" etc.
# doesn't collide; covers jet-ski spellings (space / hyphen / joined). Same
# pattern the chat de-rank uses (app/chat/intents/runtime.py:_MARINE_ITEM_RE).
_MARINE_RE = re.compile(
    r"\b(marine|boat|watercraft|outboard|pontoon|jet[\s-]?ski)\b", re.IGNORECASE
)

# Informational only: does the name also carry a repair/service signal? Helps
# Casey separate genuine marine *service* shops from dealers / rentals when he
# reviews the CSV. Not a filter — every marine-named hybrid is listed.
_REPAIR_SIGNAL_RE = re.compile(
    r"\b(repair|service|mechanic|fiberglass|rigging|performance|body\s+shop|"
    r"automotive|auto|rv|tire)\b",
    re.IGNORECASE,
)


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(*, out_path: Path | None = None, session=None) -> Counter:
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")

        id_to_slug = {
            cid: slug
            for slug, cid in session.query(Category.slug, Category.id).filter(
                Category.level == 1
            )
        }
        target_present = _TARGET_LEAF in id_to_slug.values()
        if not target_present:
            print(
                f"WARNING — target leaf '{_TARGET_LEAF}' not found among level-1 "
                "categories; candidates are still listed by current primary leaf."
            )

        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(
                EntityCategory.is_primary.is_(True)
            )
        }

        # Left-join Entity so a provider with no/again-mapped entity still lists
        # (its slug shows blank, flagging that it can't be cross-listed as-is).
        rows = (
            session.query(Provider, Entity.slug)
            .outerjoin(Entity, Entity.id == Provider.entity_id)
            .filter(Provider.is_active.is_(True))
            .all()
        )
        counts["active_providers"] = len(rows)

        candidates: list[dict] = []
        for p, entity_slug in rows:
            if not _MARINE_RE.search(p.provider_name or ""):
                continue
            counts["marine_named"] += 1
            cur_leaf_id = current_primary.get(p.entity_id)
            cur_slug = id_to_slug.get(cur_leaf_id) if cur_leaf_id else None
            if cur_slug == _TARGET_LEAF:
                counts["already_on_boat_repair"] += 1
                continue  # already the primary -> already on the leaf page
            counts["missing_from_boat_repair"] += 1
            if not entity_slug:
                counts["no_entity_slug"] += 1
            candidates.append(
                {
                    "entity_slug": entity_slug or "",
                    "provider_name": p.provider_name or "",
                    "provider_slug": p.slug or "",
                    "google_primary_category": p.google_primary_category or "",
                    "current_primary_leaf": cur_slug or "(none)",
                    "name_has_repair_signal": bool(
                        _REPAIR_SIGNAL_RE.search(p.provider_name or "")
                    ),
                }
            )

        candidates.sort(key=lambda r: (r["current_primary_leaf"], r["provider_name"]))

        out_path = out_path or (
            _ROOT
            / f"marine_cross_listing_candidates_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
        )
        _write_csv(out_path, candidates)

        print(f"Active providers          : {counts['active_providers']}")
        print(f"Marine-named              : {counts.get('marine_named', 0)}")
        print(f"Already on boat-repair    : {counts.get('already_on_boat_repair', 0)}")
        print(f"Missing from boat-repair  : {counts.get('missing_from_boat_repair', 0)}")
        print(f"  (of those, no Entity slug): {counts.get('no_entity_slug', 0)}")
        print(f"Candidate CSV             : {out_path}\n")

        print("Candidates (current primary leaf -> would also surface on boat-repair):")
        for r in candidates:
            repair = "repair-name" if r["name_has_repair_signal"] else "name-only "
            slug = r["entity_slug"] or "(NO ENTITY SLUG)"
            print(
                f"  - {r['provider_name'][:38]:38}  {repair}  "
                f"{r['google_primary_category'][:18]:18}  "
                f"{r['current_primary_leaf']:>26}   slug={slug}"
            )

        usable = [r["entity_slug"] for r in candidates if r["entity_slug"]]
        print("\nSuggested cross_listing snippet (REVIEW + trim to genuine marine):")
        print(f'    "{_TARGET_LEAF}": frozenset(')
        print("        {")
        for s in usable:
            print(f'            "{s}",')
        print("        }")
        print("    ),")
        print(
            "\nREAD-ONLY — nothing was written to the DB. Review the CSV, drop any "
            "non-marine (pure dealers/rentals), then hand back the kept slugs for "
            "the cross_listing PR."
        )
        return counts
    finally:
        if own_session:
            session.close()


def _write_csv(out_path: Path, rows: list[dict]) -> None:
    fields = [
        "entity_slug",
        "provider_name",
        "provider_slug",
        "google_primary_category",
        "current_primary_leaf",
        "name_has_repair_signal",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="Candidate-CSV path.")
    args = parser.parse_args(argv)
    run(out_path=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
