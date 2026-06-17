"""Phase 4 — Fitness & Classes completeness: add missing listings + recategorize.

Source of truth: ``relay/ASK_HAVA_PHASE4_FITNESS_AUDIT_2026-06-17.md`` plus the
2026-06-17 verification pass (Cowork session). Two gated operations in one script,
both honoring ``--dry-run`` (default) / ``--apply``:

  python scripts/phase4_fitness_load.py            # preview (default)
  python scripts/phase4_fitness_load.py --dry-run  # explicit preview
  python scripts/phase4_fitness_load.py --apply    # persist + undo snapshot

ADDS — genuinely-absent businesses fetched LIVE from the Google Places API by
name, so the card gets real place_id / lat-lng / rating / hours rather than a thin
hand-typed row. Requires ``GOOGLE_PLACES_API_KEY`` in the environment (dry-run
included — the preview shows exactly what would be written). The 2026-06-17
dry-run found 8 of the 9 audit "missing" businesses were already present but
misfiled, so they moved to RECAT below; only Four Dragons remains a true add.
A business is filed onto its leaf by setting ``Provider.category_id`` to the leaf's
``Category.id``; ``create_provider_and_entity`` then creates the PRIMARY
``EntityCategory`` link the leaf page actually filters on (see
``app/categories/leaf_pages.py``). Dedupe is by ``google_place_id`` and by name —
a business already present (or present on another leaf) is reported and SKIPPED,
never duplicated.

RECAT (move existing rows between leaves) — the leaf page lists an entity by its
PRIMARY ``EntityCategory`` link, so a move repoints that link from the source leaf
to the target leaf. ``Provider.subcategory`` is secondary metadata the leaf page
does NOT read, so it is intentionally left untouched. Each move asserts the
entity's current primary link is on the expected source leaf; an unexpected state
is reported and SKIPPED (no guessing — repo rule).

Three "non-gym" rows the audit flags (Kaizen Golf, Shah Racquetball, Universal
Sonics gymnastics/cheer) have NO destination leaf in the live taxonomy, so they
are listed with ``to_leaf=None`` — reported as ``flagged_no_target`` and LEFT in
place (removing them with no home would orphan the listing). Surfaced for Casey.

On ``--apply`` an undo snapshot (adds: inserted provider/entity ids; recat: prior
EntityCategory state) is written to ``relay/`` before the commit. Dry-run asserts
zero writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402
from app.contrib.google_places_scraper import GooglePlacesClient  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import create_provider_and_entity  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402
from scripts.places_load import LHC_ZIPS, row_to_provider_kwargs  # noqa: E402

# Leaf Category slugs (level=1) under the Fitness & Classes / Shopping departments.
LEAF_MARTIAL = "martial-arts"
LEAF_DANCE = "dance-studios"
LEAF_PT = "personal-training"
LEAF_YOGA = "yoga-and-pilates"
LEAF_NUTRITION = "nutrition-and-wellness"
LEAF_GYMS = "gyms-and-fitness-centers"
LEAF_SPORTING = "sporting-goods"
# Non-fitness leaves the 2026-06-17 dry-run found these businesses MISFILED on.
LEAF_KIDS = "kids-classes-and-camps"
LEAF_PARKS = "parks-and-playgrounds"
LEAF_PRIMARY_CARE = "primary-care"

# Fetch fn type: (search_query, expect_name_contains) -> enriched row | None.
FetchFn = Callable[[str, str], "dict[str, Any] | None"]


# --------------------------------------------------------------------------- #
# Specs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AddSpec:
    """One business to add, fetched live from Places by ``query``."""

    query: str  # Places text-search query
    expect: str  # lower-case substring the returned name must contain (match guard)
    leaf: str  # target leaf Category slug


@dataclass(frozen=True)
class RecatSpec:
    """Move an existing entity's primary EntityCategory between leaves."""

    name_contains: str  # case-insensitive match against Entity.name
    from_leaf: str  # leaf the primary link is expected to be on now
    to_leaf: str | None  # target leaf; None => no destination, flag + leave in place
    reason: str


# The 2026-06-17 dry-run revealed 8 of the 9 audit "missing" businesses were
# already in the directory, just MISFILED on non-fitness leaves — so they're
# re-files, not adds. Only Four Dragons is genuinely absent.
ADD_SPECS: list[AddSpec] = [
    AddSpec("Four Dragons Martial Arts Lake Havasu City AZ", "four dragons", LEAF_MARTIAL),
]

# Categorization fixes (Casey-approved 2026-06-17). from_leaf must match the row's
# current PRIMARY link or the move is skipped as unexpected_state. The first block
# re-files the 8 businesses the dry-run found misfiled (sources observed live);
# the second block is the original audit cleanup.
RECAT_SPECS: list[RecatSpec] = [
    # Misfiled martial-arts dojos -> martial-arts (correct, specific home).
    RecatSpec("arevalo", LEAF_KIDS, LEAF_MARTIAL, "martial arts academy misfiled in kids"),
    RecatSpec("shao-lin", LEAF_KIDS, LEAF_MARTIAL, "martial arts (kempo) misfiled in kids"),
    RecatSpec("elite martial", LEAF_KIDS, LEAF_MARTIAL, "martial arts misfiled in kids"),
    RecatSpec("black belt", LEAF_KIDS, LEAF_MARTIAL, "taekwondo academy misfiled in kids"),
    RecatSpec("tap room", LEAF_PARKS, LEAF_MARTIAL, "jiu jitsu misfiled in parks"),
    # Misfiled dance studios -> dance-studios.
    RecatSpec("arizona coast", LEAF_KIDS, LEAF_DANCE, "dance studio misfiled in kids"),
    RecatSpec("foot lite", LEAF_KIDS, LEAF_DANCE, "dance studio misfiled in kids"),
    # Misfiled personal trainer -> personal-training.
    RecatSpec("heart and sole", LEAF_PRIMARY_CARE, LEAF_PT, "personal trainer misfiled in primary-care"),
    # Original audit cleanup.
    RecatSpec("nutrition one", LEAF_PT, LEAF_NUTRITION, "supplement store, not a trainer"),
    RecatSpec("align and define", LEAF_GYMS, LEAF_YOGA, "pilates studio"),
    RecatSpec("pilates of lake havasu", LEAF_GYMS, LEAF_YOGA, "pilates studio"),
    RecatSpec("crazy ed", LEAF_GYMS, LEAF_YOGA, "cardio & pilates studio"),
    # Precise term: only "Havasu Bike and Fitness" (the "and" variant), NOT the
    # suspected-duplicate "Lake Havasu Bike & Fitness" — flagged separately.
    RecatSpec("havasu bike and fitness", LEAF_GYMS, LEAF_SPORTING, "bicycle shop, retail"),
    RecatSpec("studio 2959", LEAF_GYMS, LEAF_PT, "1-on-1 personal-training studio"),
    # No destination leaf in the live taxonomy — flagged, left in place.
    RecatSpec("kaizen", LEAF_GYMS, None, "golf & fitness — no golf leaf"),
    RecatSpec("shah racquet", LEAF_GYMS, None, "racquetball — no racquet leaf"),
    RecatSpec("universal sonic", LEAF_GYMS, None, "gymnastics/cheer — no leaf"),
]


# --------------------------------------------------------------------------- #
# Live Places fetch
# --------------------------------------------------------------------------- #
def _api_key() -> str:
    ensure_dotenv_loaded()
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not key:
        raise SystemExit(
            "GOOGLE_PLACES_API_KEY is not set. This script (dry-run included) fetches "
            "live Google Places data to build real cards. Run it where the key is "
            "configured."
        )
    return key


def make_places_fetch() -> FetchFn:
    """Real fetcher: Places Text Search -> pick best name match -> Place Details."""
    client = GooglePlacesClient()
    key = _api_key()

    def fetch(query: str, expect: str) -> dict[str, Any] | None:
        payload = client.request_text_search(key, query, None)
        places = payload.get("places") or []
        if not places:
            return None
        chosen = next(
            (
                pl
                for pl in places
                if expect in ((pl.get("displayName") or {}).get("text") or "").lower()
            ),
            places[0],
        )
        pid = chosen.get("id")
        if not pid:
            return None
        detail = client.request_place_details(key, pid)
        meta = {
            "_first_seen_domain": "fitness_sports",
            "_first_seen_category": query,
            "_seen_categories": [query],
        }
        return client.build_enriched_row(pid, detail, meta)

    return fetch


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _category_id_by_slug(db: Session) -> dict[str, int]:
    return {c.slug: c.id for c in db.scalars(select(Category)).all()}


def _zip5(value: Any) -> str:
    return str(value or "").replace("-", "")[:5]


def _find_provider_by_name(db: Session, term: str) -> list[Provider]:
    """Active providers whose entity name contains ``term`` (case-insensitive)."""
    like = f"%{term.lower()}%"
    return list(
        db.scalars(
            select(Provider)
            .join(Entity, Provider.entity_id == Entity.id)
            .where(Provider.is_active.is_(True))
            .where(Entity.is_active.is_(True))
            .where(Entity.name.ilike(like))
        ).all()
    )


def _provider_exists(db: Session, place_id: str, name: str) -> Provider | None:
    """Existing provider by google_place_id (strong key) or exact-ish name."""
    hit = db.scalars(
        select(Provider).where(Provider.google_place_id == place_id).limit(1)
    ).first()
    if hit is not None:
        return hit
    matches = _find_provider_by_name(db, name)
    return matches[0] if matches else None


def _primary_entity_category(db: Session, entity_id: str) -> EntityCategory | None:
    return db.scalars(
        select(EntityCategory)
        .where(EntityCategory.entity_id == entity_id)
        .where(EntityCategory.is_primary.is_(True))
        .limit(1)
    ).first()


# --------------------------------------------------------------------------- #
# ADD
# --------------------------------------------------------------------------- #
def add_listings(
    db: Session,
    *,
    apply: bool,
    fetch: FetchFn,
    cat_by_slug: dict[str, int],
    undo: list[dict[str, Any]],
) -> Counter[str]:
    c: Counter[str] = Counter()
    now = datetime.now(UTC)

    for spec in ADD_SPECS:
        c["total"] += 1
        tgt_id = cat_by_slug.get(spec.leaf)
        if tgt_id is None:
            c["leaf_missing"] += 1
            print(f"--- LEAF MISSING: {spec.leaf!r} for {spec.query!r}")
            continue

        row = fetch(spec.query, spec.expect)
        if not row or not row.get("display_name") or not row.get("place_id"):
            c["fetch_miss"] += 1
            print(f"--- fetch_miss: {spec.query}")
            continue

        name = row["display_name"]
        if spec.expect not in name.lower():
            c["name_mismatch"] += 1
            print(f"--- name_mismatch: wanted ~{spec.expect!r}, Places returned {name!r}")
            continue

        if _zip5(row.get("zip")) not in LHC_ZIPS:
            c["non_lhc"] += 1
            print(f"--- non_lhc (skip): {name} zip={row.get('zip')!r}")
            continue

        existing = _provider_exists(db, row["place_id"], name)
        if existing is not None:
            primary = _primary_entity_category(db, existing.entity_id)
            where = "?"
            if primary is not None:
                where = next(
                    (s for s, cid in cat_by_slug.items() if cid == primary.category_id), "?"
                )
            c["already_present"] += 1
            print(
                f"--- already_present (skip add): {name} "
                f"-> existing provider {existing.id} on leaf {where!r}"
                + ("  [RECAT candidate]" if where not in {spec.leaf, "?"} else "")
            )
            continue

        c["would_add"] += 1
        print(
            f"--- ADD: {name}  -> leaf {spec.leaf}\n"
            f"      place_id={row['place_id']}  addr={row.get('formatted_address')!r}\n"
            f"      rating={row.get('rating')!r} ({row.get('review_count')!r} reviews)  "
            f"phone={row.get('phone')!r}"
        )
        if not apply:
            continue

        kwargs = row_to_provider_kwargs(row, ref_now=now)
        kwargs["category_id"] = tgt_id
        slug = derive_provider_slug(db, kwargs["provider_name"])
        provider = Provider(**kwargs, slug=slug, last_google_scraped_at=now)
        db.add(provider)
        create_provider_and_entity(db, provider)
        db.flush()
        c["added"] += 1
        undo.append(
            {
                "op": "add",
                "provider_id": provider.id,
                "entity_id": provider.entity_id,
                "google_place_id": row["place_id"],
                "name": name,
                "leaf": spec.leaf,
            }
        )

    return c


# --------------------------------------------------------------------------- #
# RECAT
# --------------------------------------------------------------------------- #
def recat_listings(
    db: Session,
    *,
    apply: bool,
    cat_by_slug: dict[str, int],
    undo: list[dict[str, Any]],
) -> Counter[str]:
    c: Counter[str] = Counter()

    for spec in RECAT_SPECS:
        c["total"] += 1
        if spec.to_leaf is None:
            c["flagged_no_target"] += 1
            print(f"--- FLAG (no target leaf, left in place): {spec.name_contains} — {spec.reason}")
            continue

        src_id = cat_by_slug.get(spec.from_leaf)
        tgt_id = cat_by_slug.get(spec.to_leaf)
        if src_id is None or tgt_id is None:
            c["leaf_missing"] += 1
            print(f"--- LEAF MISSING for {spec.name_contains!r}: {spec.from_leaf} -> {spec.to_leaf}")
            continue

        matches = _find_provider_by_name(db, spec.name_contains)
        if not matches:
            c["no_match"] += 1
            print(f"--- no_match: {spec.name_contains!r}")
            continue
        if len(matches) > 1:
            c["ambiguous"] += 1
            names = ", ".join(sorted(p.provider_name for p in matches))
            print(f"--- ambiguous ({len(matches)} matches, skip): {spec.name_contains!r} -> {names}")
            continue

        provider = matches[0]
        primary = _primary_entity_category(db, provider.entity_id)
        if primary is None or primary.category_id != src_id:
            cur = "none" if primary is None else next(
                (s for s, cid in cat_by_slug.items() if cid == primary.category_id),
                str(primary.category_id),
            )
            c["unexpected_state"] += 1
            print(
                f"--- unexpected_state (skip): {provider.provider_name} primary leaf is "
                f"{cur!r}, expected {spec.from_leaf!r}"
            )
            continue

        c["would_move"] += 1
        print(
            f"--- MOVE: {provider.provider_name}  {spec.from_leaf} -> {spec.to_leaf}  "
            f"({spec.reason})"
        )
        if not apply:
            continue

        all_ecs = list(
            db.scalars(
                select(EntityCategory).where(EntityCategory.entity_id == provider.entity_id)
            ).all()
        )
        undo.append(
            {
                "op": "recat",
                "entity_id": provider.entity_id,
                "provider_id": provider.id,
                "name": provider.provider_name,
                "provider_category_id": provider.category_id,
                "entity_categories": [
                    {"id": ec.id, "category_id": ec.category_id, "is_primary": ec.is_primary}
                    for ec in all_ecs
                ],
            }
        )

        existing_tgt = next((ec for ec in all_ecs if ec.category_id == tgt_id), None)
        if existing_tgt is not None:
            # Target link already present: promote it, demote the source link.
            existing_tgt.is_primary = True
            primary.is_primary = False
        else:
            # Repoint the source primary link onto the target leaf.
            primary.category_id = tgt_id
        # Sustainability: the Google Places re-scrape (places_load.py) PRESERVES an
        # operator-set Provider.category_id and re-ensures the matching primary
        # EntityCategory from it. Setting it to the target leaf here is what keeps
        # the move sticky across future scrapes — without it, the next re-pull
        # would re-insert the OLD leaf link from the stale Provider.category_id.
        provider.category_id = tgt_id
        db.flush()
        c["moved"] += 1

    return c


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _write_undo(undo: list[dict[str, Any]], snapshot_dir: Path | None) -> Path:
    out_dir = snapshot_dir or (Path(__file__).resolve().parents[1] / "relay")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = out_dir / f"_phase4_fitness_undo_{datetime.now():%Y%m%dT%H%M%S}.json"
    snap.write_text(json.dumps(undo, indent=2), encoding="utf-8")
    return snap


def run(
    db: Session,
    *,
    apply: bool,
    fetch: FetchFn,
    snapshot_dir: Path | None = None,
) -> dict[str, Counter[str]]:
    """Recat first (no network), then adds. Returns the two counters."""
    cat_by_slug = _category_id_by_slug(db)
    undo: list[dict[str, Any]] = []

    print("\n=== RECAT (move existing rows between leaves) ===")
    recat = recat_listings(db, apply=apply, cat_by_slug=cat_by_slug, undo=undo)
    print("\n=== ADD (fetch live Places data, file onto leaf) ===")
    adds = add_listings(db, apply=apply, fetch=fetch, cat_by_slug=cat_by_slug, undo=undo)

    if apply and undo:
        snap = _write_undo(undo, snapshot_dir)
        db.commit()
        print(f"\ninfo: applied {len(undo)} ops; undo snapshot -> {snap}")
    elif apply:
        print("\ninfo: nothing to apply (no eligible rows).")

    print("\n--- RECAT summary ---")
    for k in ("total", "flagged_no_target", "no_match", "ambiguous", "unexpected_state",
              "leaf_missing", "would_move", "moved"):
        print(f"  {k:18} {recat[k]}")
    print("--- ADD summary ---")
    for k in ("total", "fetch_miss", "name_mismatch", "non_lhc", "already_present",
              "leaf_missing", "would_add", "added"):
        print(f"  {k:18} {adds[k]}")

    if not apply:
        assert recat["moved"] == 0 and adds["added"] == 0, "dry-run must not persist"
    return {"recat": recat, "add": adds}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", action="store_true", help="Preview without writing (default).")
    mode.add_argument("--apply", action="store_true", help="Persist updates + undo snapshot.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    fetch = make_places_fetch()
    with SessionLocal() as db:
        run(db, apply=bool(args.apply), fetch=fetch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
