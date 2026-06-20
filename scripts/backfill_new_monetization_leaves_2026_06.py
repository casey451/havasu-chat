"""Create + populate the 2026-06-19 monetization leaves (DRY-RUN by default; gated).

Companion to ``docs/proposals/category-monetization-review-2026-06-19.md``. That
pass added 13 high-ad-value Havasu leaves to ``docs/proposals/taxonomy-seed.json``
and wired their chat synonyms, but a leaf earns nothing until it (a) exists as a
``categories`` row and (b) clears the >=3 active-provider gate
(``LEAF_PAGE_MIN_PROVIDERS``). Most of these businesses are already in the DB,
just filed under a broader leaf (a golf-cart dealer under ``powersports-and-atv``,
an auto-glass shop under ``auto-repair``). This script does BOTH steps, surgically:

1. **Ensure leaf rows** — insert each of the 13 leaves under its department if
   missing (idempotent by slug; a later full ``seed_taxonomy.py`` stays
   consistent because the same slugs/names live in the seed JSON).
2. **Stage primary reassignments** — for every active Provider, a CONSERVATIVE
   name/Google-type matcher (:func:`match_new_leaf`, pure + unit-testable)
   proposes a move onto one of the new leaves. Same write shape as
   ``backfill_leaf_categories.py``: clear the old primary ``entity_categories``
   link, set the new leaf primary.

Why a local matcher (not ``leaf_type_mapping``): these verticals have no
confident Google ``types[]`` token, so the resolver leaves them unmapped. The
rules here are name-signal-driven and therefore FUZZIER — which is exactly why
the default is a dry-run that emits a per-leaf count + a reviewable CSV. Eyeball
the CSV, prune false positives, THEN a human applies.

Protections (mirrors the existing backfill): never touches a verified-``Claim``
entity; never moves a provider already primary-linked to the target; reports an
ambiguous match (two different leaves) instead of guessing.

    .venv\\Scripts\\python.exe scripts\\backfill_new_monetization_leaves_2026_06.py                 # DRY RUN
    .venv\\Scripts\\python.exe scripts\\backfill_new_monetization_leaves_2026_06.py --csv plan.csv  # DRY RUN + CSV
    .venv\\Scripts\\python.exe scripts\\backfill_new_monetization_leaves_2026_06.py --apply --confirm

PROD GATE (CLAUDE.md): run dry, show Casey the counts + CSV, get approval, THEN a
human runs --apply --confirm against prod. The agent never runs --apply on prod.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Claim, Entity, EntityCategory, Provider  # noqa: E402

try:  # keep the gate threshold in one place; tolerate import-time drift
    from app.categories.leaf_pages import LEAF_PAGE_MIN_PROVIDERS
except Exception:  # pragma: no cover - defensive
    LEAF_PAGE_MIN_PROVIDERS = 3


# New leaf slug -> (department slug, display name). Matches taxonomy-seed.json.
NEW_LEAVES: dict[str, tuple[str, str]] = {
    "golf-carts": ("auto-rv-and-marine", "Golf Carts"),
    "off-road-shops-and-accessories": ("auto-rv-and-marine", "Off-Road Shops & Accessories"),
    "window-tint-and-wraps": ("auto-rv-and-marine", "Window Tint & Wraps"),
    "auto-glass": ("auto-rv-and-marine", "Auto Glass"),
    "trailer-sales-and-repair": ("auto-rv-and-marine", "Trailer Sales & Repair"),
    "marine-supply": ("on-the-water", "Marine Supply"),
    "garage-doors": ("home-and-property-services", "Garage Doors"),
    "painters": ("home-and-property-services", "Painters"),
    "pressure-washing-and-exterior-cleaning": (
        "home-and-property-services",
        "Pressure Washing & Exterior Cleaning",
    ),
    "junk-removal-and-hauling": ("home-and-property-services", "Junk Removal & Hauling"),
    "shade-screens-and-patio-covers": ("home-and-property-services", "Shade Screens & Patio Covers"),
    "property-management": ("professional-and-financial", "Property Management"),
    "hearing-and-audiology": ("health-and-medical", "Hearing & Audiology"),
}


# Conservative matcher rules, in priority order. ``include`` = any-of substrings
# that must appear in the haystack (lowercased name + primary type + google
# categories text); ``exclude`` = any-of substrings that veto the match (guards
# against the obvious false positives). First rule whose include hits and whose
# excludes miss is a candidate; if two DIFFERENT leaves match, the provider is
# reported ambiguous and skipped (never guessed).
_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("golf-carts", ("golf cart", "golf car ", "golf carts", "golf cars"), ()),
    (
        "window-tint-and-wraps",
        ("window tint", "auto tint", "tint", "tinting", "vehicle wrap", "car wrap",
         "vinyl wrap", "auto wrap", "wraps"),
        ("tanning", "spray tan", "eyebrow", "lash", "brow", "sip"),
    ),
    ("auto-glass", ("auto glass", "autoglass", "windshield", "auto-glass"), ()),
    (
        "garage-doors",
        ("garage door", "overhead door"),
        (),
    ),
    (
        "pressure-washing-and-exterior-cleaning",
        ("pressure wash", "power wash", "soft wash", "pressure-wash", "power-wash"),
        (),
    ),
    (
        "junk-removal-and-hauling",
        ("junk removal", "junk haul", "junk-removal", "hauling & junk", "junk pickup"),
        ("junkyard", "auto", "salvage"),
    ),
    (
        "shade-screens-and-patio-covers",
        ("sun screen", "shade screen", "patio cover", "awning", "sun shade", "shade structure"),
        (),
    ),
    (
        "property-management",
        ("property management", "property manager", "property mgmt", "rental management"),
        (),
    ),
    (
        "hearing-and-audiology",
        ("hearing aid", "hearing center", "audiology", "audiologist", "hearing clinic"),
        (),
    ),
    (
        "marine-supply",
        ("marine supply", "marine supplies", "marine parts", "boat supply", "boat parts", "boat accessor"),
        ("rental", "repair", "detail"),
    ),
    (
        "trailer-sales-and-repair",
        ("trailer sales", "trailer repair", "trailer service", "boat trailer", "utility trailer"),
        ("trailer park", "mobile home", "rv park"),
    ),
    (
        "off-road-shops-and-accessories",
        ("off road", "off-road", "offroad", "4x4", "lift kit", "off road accessor"),
        ("rental", "tour", "trail ", "park"),
    ),
    (
        "painters",
        ("painting", "painter", "painters"),
        ("auto", "collision", "body shop", "powder coat", "face paint", "art", "sip"),
    ),
)


# Leaves the optional ``--wide`` pass is allowed to fill from SECONDARY Google
# categories. Deliberately the empty, name-signal-poor leaves only — and
# deliberately NOT ``painters``: a general contractor / handyman almost always
# lists "Painter" as a secondary service, so a secondary match there reliably
# misfiles a GC's PRIMARY onto painters (the exact 2026-06-19 dry-run bug).
# Painters needs pure-painting names or manual tagging, not a secondary sweep.
WIDE_SECONDARY_SLUGS: frozenset[str] = frozenset(
    {
        "window-tint-and-wraps",
        "marine-supply",
        "junk-removal-and-hauling",
        "shade-screens-and-patio-covers",
    }
)


def _haystack(name: str | None, primary_type: str | None, google_categories) -> str:
    """Lowercased match text from name + primary Google type + category tokens."""
    parts: list[str] = [name or "", primary_type or ""]
    if google_categories:
        if isinstance(google_categories, str):
            parts.append(google_categories)
        else:
            try:
                parts.extend(str(t) for t in google_categories)
            except TypeError:
                parts.append(str(google_categories))
    text = " ".join(parts).lower()
    return re.sub(r"\s+", " ", text)


def _rule_hits(hay: str, allowed: frozenset[str] | None = None) -> list[str]:
    """Distinct leaf slugs whose include hits and excludes miss in ``hay``.
    ``allowed`` (when given) restricts which rules are considered."""
    hits: list[str] = []
    for slug, include, exclude in _RULES:
        if allowed is not None and slug not in allowed:
            continue
        if any(tok in hay for tok in include) and not any(tok in hay for tok in exclude):
            hits.append(slug)
    return list(dict.fromkeys(hits))


def match_new_leaf(
    name: str | None,
    primary_type: str | None = None,
    google_categories=None,
    *,
    wide_slugs: frozenset[str] = frozenset(),
) -> str | None:
    """Best new-leaf slug for a provider, or ``None``. Pure (no DB).

    Two-stage, strong-signal-first:

    1. **Name + primary type only** (the repo's PRIMARY-only doctrine). Exactly
       one match wins; an ambiguous hit (two different leaves) returns ``None``.
    2. **Wide fallback** — ONLY when stage 1 found nothing AND ``wide_slugs`` is
       non-empty: also scan the secondary ``google_categories`` text, but accept
       a match only if its slug is in ``wide_slugs`` (the empty, name-poor
       leaves). This is opt-in (``--wide``) because secondary tokens are noisier.
    """
    strong = _rule_hits(_haystack(name, primary_type, None))
    if len(strong) == 1:
        return strong[0]
    if len(strong) > 1:
        return None
    if wide_slugs and google_categories:
        wide = _rule_hits(_haystack(name, primary_type, google_categories), allowed=wide_slugs)
        if len(wide) == 1:
            return wide[0]
    return None


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(
    *,
    apply: bool = False,
    confirm: bool = False,
    csv_path: Path | None = None,
    snapshot_dir: Path | None = None,
    wide: bool = False,
    session=None,
) -> Counter:
    """Ensure the new leaves exist and stage/commit provider moves. Dry by default.

    ``wide=True`` enables the secondary-category fallback for the empty,
    name-poor leaves (:data:`WIDE_SECONDARY_SLUGS`) — review the CSV carefully.
    """
    wide_slugs = WIDE_SECONDARY_SLUGS if wide else frozenset()
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        if wide:
            print(
                "WIDE mode ON — secondary-category fallback enabled for "
                f"{sorted(WIDE_SECONDARY_SLUGS)}. Review the CSV closely.\n"
            )

        cats = session.query(Category).all()
        by_slug = {c.slug: c for c in cats}
        dept_id = {c.slug: c.id for c in cats if c.level == 0}

        # ---- step 1: which leaves exist / would be created ----
        leaf_id_by_slug: dict[str, int | None] = {}
        to_create: list[tuple[str, str, int]] = []  # (slug, name, parent_id)
        print("leaf rows:")
        for slug, (dept_slug, name) in NEW_LEAVES.items():
            existing = by_slug.get(slug)
            if existing is not None and existing.level == 1:
                leaf_id_by_slug[slug] = existing.id
                print(f"  exists   {slug:38s} (id={existing.id})")
                continue
            parent = dept_id.get(dept_slug)
            if parent is None:
                counts["dept_absent"] += 1
                leaf_id_by_slug[slug] = None
                print(f"  ABORT    {slug:38s} — department {dept_slug!r} not found")
                continue
            leaf_id_by_slug[slug] = None
            sort_order = sum(1 for c in cats if c.level == 1 and c.parent_id == parent)
            to_create.append((slug, name, parent))
            counts["leaf_would_create"] += 1
            print(f"  CREATE   {slug:38s} under {dept_slug} (sort_order={sort_order})")

        # ---- step 2: scan providers, stage moves ----
        claimed = {
            eid for (eid,) in session.query(Claim.entity_id).filter(Claim.status == "verified")
        }
        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(EntityCategory.is_primary.is_(True))
        }
        providers = (
            session.query(Provider)
            .join(Entity, Provider.entity_id == Entity.id)
            .filter(Entity.is_active.is_(True), Provider.is_active.is_(True))
            .all()
        )
        counts["providers_scanned"] = len(providers)

        staged: list[tuple[str, str, str]] = []  # (entity_id, leaf_slug, provider_name)
        report_rows: list[dict] = []
        per_leaf: Counter = Counter()
        for p in providers:
            eid = p.entity_id
            if eid is None:
                continue
            # PRIMARY-ONLY by deliberate choice: name + primary Google type, never
            # the noisy secondary ``google_categories`` array. Matching secondary
            # tokens is what moved "Havasu Handyman Services" (a general_contractor
            # that merely *lists* painting) onto painters — the same class of
            # misfile as the 2026-06-12 backfill incident. Name is the real signal
            # for these verticals; the generic primary type rarely carries it.
            slug = match_new_leaf(
                p.provider_name,
                p.google_primary_category,
                p.google_categories if wide else None,
                wide_slugs=wide_slugs,
            )
            if slug is None or slug not in NEW_LEAVES:
                continue
            if eid in claimed:
                counts["protected_claimed"] += 1
                continue
            target_id = leaf_id_by_slug.get(slug)
            if target_id is not None and current_primary.get(eid) == target_id:
                counts["unchanged"] += 1
                continue
            counts["would_move"] += 1
            per_leaf[slug] += 1
            staged.append((eid, slug, (p.provider_name or "").strip()))
            report_rows.append(
                {
                    "entity_id": eid,
                    "provider_name": (p.provider_name or "").strip(),
                    "google_primary_category": p.google_primary_category or "",
                    "current_primary_category_id": current_primary.get(eid) or "",
                    "new_leaf_slug": slug,
                }
            )

        # ---- report ----
        print("\nmove plan (per leaf — does it reach the gate?):")
        for slug in NEW_LEAVES:
            n = per_leaf.get(slug, 0)
            gate = "GATE OK" if n >= LEAF_PAGE_MIN_PROVIDERS else f"below {LEAF_PAGE_MIN_PROVIDERS}"
            print(f"  {n:>4}  {slug:38s} [{gate}]")
        print(
            f"\n  totals: would_move={counts.get('would_move', 0)} "
            f"unchanged={counts.get('unchanged', 0)} "
            f"protected_claimed={counts.get('protected_claimed', 0)} "
            f"scanned={counts['providers_scanned']}"
        )
        print("\nsample matches (review for false positives):")
        for r in report_rows[:30]:
            print(
                f"  {r['provider_name'][:38]:38s} | "
                f"{r['google_primary_category'][:18]:18s} -> {r['new_leaf_slug']}"
            )

        if csv_path and report_rows:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
                w.writeheader()
                w.writerows(report_rows)
            print(f"\nwrote {len(report_rows)} planned moves to {csv_path}")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(
                f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                f"{_sanitized_target()}."
            )
            return counts

        # ---- rollback snapshot (touched entity_categories + leaves we create) ----
        touched = list({eid for eid, _, _ in staged})
        snapshot = {
            "created_leaves": [{"slug": s, "name": n, "parent_id": pid} for s, n, pid in to_create],
            "entity_categories": [
                {
                    "id": ec.id,
                    "entity_id": ec.entity_id,
                    "category_id": ec.category_id,
                    "is_primary": ec.is_primary,
                }
                for ec in session.query(EntityCategory).filter(
                    EntityCategory.entity_id.in_(touched)
                )
            ]
            if touched
            else [],
        }
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"new_monetization_leaves_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path}")

        # ---- one transaction: create leaves, then swap primaries ----
        for slug, name, parent in to_create:
            sort_order = (
                session.query(Category)
                .filter(Category.level == 1, Category.parent_id == parent)
                .count()
            )
            leaf = Category(slug=slug, name=name, level=1, sort_order=sort_order)
            leaf.parent_id = parent
            session.add(leaf)
            session.flush()
            leaf_id_by_slug[slug] = leaf.id
            counts["leaves_created"] += 1

        for entity_id, slug, _name in staged:
            new_id = leaf_id_by_slug.get(slug)
            if new_id is None:
                counts["skipped_no_leaf"] += 1
                continue
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id,
                EntityCategory.is_primary.is_(True),
            ):
                ec.is_primary = False
            existing = (
                session.query(EntityCategory)
                .filter(
                    EntityCategory.entity_id == entity_id,
                    EntityCategory.category_id == new_id,
                )
                .one_or_none()
            )
            if existing is None:
                session.add(
                    EntityCategory(entity_id=entity_id, category_id=new_id, is_primary=True)
                )
            else:
                existing.is_primary = True
            counts["primaries_changed"] += 1

        session.commit()
        print(
            f"\nAPPLIED — created {counts.get('leaves_created', 0)} leaves, "
            f"{counts.get('primaries_changed', 0)} primary moves, one transaction."
        )
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create + populate the 2026-06 monetization leaves.")
    ap.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    ap.add_argument("--confirm", action="store_true", help="Required with --apply.")
    ap.add_argument("--csv", type=Path, default=None, help="Write the planned moves to this CSV.")
    ap.add_argument(
        "--wide",
        action="store_true",
        help="Also match the empty leaves from secondary Google categories (review CSV).",
    )
    args = ap.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm, csv_path=args.csv, wide=args.wide)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
