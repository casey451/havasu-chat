"""WS9a cuisine backfill — READ-ONLY dry-run proposal report.

Scope: the Eat & Drink **restaurants** leaf (the page the ``?cuisine=`` facet
filters). Today a card's cuisine is DERIVED at render time from Google Places
types (``app.categories.subcategories.derive_cuisine`` over
``google_primary_category`` + ``google_categories``). Restaurants whose Google
types carry no cuisine token (or that have no Google types at all) show no
cuisine and are invisible to the facet — this report proposes a cuisine for
them, into the SAME fixed enum the facet already uses.

Tiers, cheapest first (mirrors the WS9a spec):
  1. **reliable** — the cuisine is in the business NAME or a Google type
     (high-precision keyword map below). Review snippets are NOT used to classify
     (a single review word mis-tagged 24 of 34 rows in the first dry-run); they
     ride along only as evidence. Free, reproducible, no API — but still routed
     for review, never blind-applied.
  2. **enum_gap** — a Google type names a cuisine the fixed enum has no home for
     (korean/cuban/fried-chicken). Proposed as a separate enum-ADDITION list; the
     row stays UNKNOWN rather than force-fit to a wrong cuisine.
  3. **needs_llm** — a real restaurant with a Google signal but no reliable hit:
     the ambiguous remainder a one-shot LLM pass (name + type + snippet context)
     resolves. This script does NOT call the LLM (spend gate) — it SIZES/SAMPLES.
  4. **needs_places** — no Google types at all: the LLM tries the name; whatever
     it can't resolve needs a Places ``types`` fetch (API cost) and stays unknown
     until then.

WRITES NOTHING. ``--apply`` is intentionally disabled. The approved apply is a
separate gated job that writes ``Provider.attributes['cuisine'] = <slug>`` as a
curated override (curated-wins precedence over the derived value) and routes
each proposal through the WS6 review queue (``pending_review``), never a hand
edit. Like the dedupe audit, this runs in CI because the repo .env points
DATABASE_URL at Railway's INTERNAL host (unreachable from a laptop).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.categories.subcategories import (  # noqa: E402
    cuisine_label,
    cuisine_slugs_in_order,
    derive_cuisine,
)
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

_REPORT_CSV = "docs/audits/2026-07/cuisine_backfill_dryrun_2026-07-08.csv"
_RESTAURANTS_LEAF_SLUG = "restaurants"

# Deterministic name/type/snippet needles into the FIXED cuisine enum
# (app.categories.subcategories._CUISINES). Superset of the render-time
# ``derive_cuisine`` needles (which only see Google types) — these also catch
# the cuisine when it lives in the business NAME ("Bad Miguel's Mexican",
# "Tokyo Grill", "Barley Brothers"). Order = enum order; first hit wins, so a
# more specific cuisine beats a generic one. Kept deliberately conservative:
# a weak/ambiguous token is left for the LLM tier rather than force-classified.
_NEEDLES: dict[str, tuple[str, ...]] = {
    "mexican": ("mexican", "taco", "taqueria", "burrito", "cantina", "mariachi",
                "birria", "azteca", "jalisco", "michoacan", "carniceria"),
    "pizza": ("pizza", "pizzeria"),
    "italian": ("italian", "trattoria", "ristorante", "pasta", "osteria"),
    "chinese": ("chinese", "china ", "wok", "panda", "mandarin", "szechuan", "canton"),
    "japanese": ("japanese", "sushi", "ramen", "hibachi", "teriyaki", "tokyo", "sakura", "izakaya"),
    "thai": ("thai",),
    "indian": ("indian", "curry", "tandoor", "masala"),
    "mediterranean": ("mediterranean", "greek", "gyro", "kabob", "kebab", "falafel", "hummus"),
    "bbq": ("barbecue", "barbeque", "bbq", "smokehouse", "smoke house", "smoked"),
    "seafood": ("seafood", "oyster", "crab", "shrimp", "lobster", "fish house", "fish co"),
    "steakhouse": ("steakhouse", "steak house", "chophouse", "chop house", "steak"),
    "burgers": ("burger", "hamburger"),
    "sandwiches": ("sandwich", "deli", "submarine", "hoagie", "sub shop"),
    "breakfast": ("breakfast", "brunch", "pancake", "waffle", "donut", "doughnut", "bagel"),
    "diner": ("diner",),
    # 'american' is intentionally NOT keyword-proposed here: grill/tavern/pub/
    # kitchen are too generic and would swallow specific cuisines. It falls to
    # the LLM tier, which can read the fuller context.
}


def _name_type_blob(name: str, primary: str | None, cats) -> str:
    """Classification signal: business NAME + Google types ONLY.

    Review snippets are deliberately EXCLUDED. The first dry-run included them and
    a single word in one review ("great tacos") mis-tagged 24 of 34 rows — Babaloo
    Lounge, a ``cuban_restaurant``, → Chinese; a steakhouse → Seafood. Snippets are
    LLM CONTEXT only (see :func:`_snippet_excerpt`), never a deterministic match
    (Casey, 2026-07-08).
    """
    parts = [name or "", primary or ""]
    if isinstance(cats, list):
        parts += [str(c) for c in cats]
    return " ".join(parts).lower()


def _propose_deterministic(name, primary, cats, snippets=None) -> str | None:
    """First name/Google-type keyword hit into the fixed enum, or None.

    High-precision by design: a generic token ('american', grill/pub/brewery) is
    never proposed — those fall to the LLM tier. ``snippets`` is accepted but
    IGNORED (kept in the signature so callers/tests document that snippets do not
    classify).
    """
    del snippets
    blob = _name_type_blob(name, primary, cats)
    for slug in cuisine_slugs_in_order():
        for needle in _NEEDLES.get(slug, ()):  # 'american' absent → skipped
            if needle in blob:
                return slug
    return None


def _snippet_excerpt(snippets) -> str:
    """First review-snippet text, trimmed — EVIDENCE / LLM context only."""
    if isinstance(snippets, list):
        for s in snippets:
            if isinstance(s, dict):
                text = str(s.get("text") or s.get("snippet") or "").strip()
                if text:
                    return text[:160]
    return ""


# Google type tokens that name a cuisine with NO home in the fixed enum. These
# become enum-ADDITION proposals (a separate list) — the row stays UNKNOWN, never
# force-fit to a wrong cuisine (Casey: an unknown beats a wrong chip). Deliberately
# specific: generic 'asian_restaurant' is left to the LLM, not proposed as an enum.
_ENUM_GAP_TYPES: dict[str, str] = {
    "korean_restaurant": "korean",
    "cuban_restaurant": "cuban",
    "chicken_restaurant": "fried_chicken",
    "vietnamese_restaurant": "vietnamese",
    "filipino_restaurant": "filipino",
    "hawaiian_restaurant": "hawaiian",
    "caribbean_restaurant": "caribbean",
}


def _enum_gap(primary, cats) -> str | None:
    """Proposed enum-addition label when a Google type names an unhomed cuisine."""
    blob = ((primary or "") + " " + " ".join(str(c) for c in (cats or []))).lower()
    for tok, label in _ENUM_GAP_TYPES.items():
        if tok in blob:
            return label
    return None


def _has_google_signal(primary, cats) -> bool:
    return bool(primary) or bool(cats)


def _restaurants_leaf_providers(db) -> list[Provider]:
    leaf = (
        db.query(Category)
        .filter(Category.slug == _RESTAURANTS_LEAF_SLUG, Category.level == 1)
        .one_or_none()
    )
    if leaf is None:
        return []
    return (
        db.query(Provider)
        .join(Entity, Provider.entity_id == Entity.id)
        .join(EntityCategory, EntityCategory.entity_id == Entity.id)
        .filter(
            EntityCategory.category_id == leaf.id,
            EntityCategory.is_primary.is_(True),
            Entity.is_active.is_(True),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
            Provider.is_local.isnot(False),
        )
        .all()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cuisine backfill dry-run proposal report.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="DISABLED — the gated apply (writes attributes['cuisine'] via the "
        "WS6 review queue) is a separate job after Casey reviews this report.",
    )
    args = parser.parse_args(argv)
    if args.apply:
        print(
            "--apply is intentionally disabled. This script only PROPOSES cuisines. "
            "Review the report with Casey, then the gated apply writes "
            "attributes['cuisine'] through the WS6 review queue (pending_review)."
        )
        return 2

    with SessionLocal() as db:
        rows = _restaurants_leaf_providers(db)

    total = len(rows)
    tier = Counter()  # already / reliable / enum_gap / needs_llm / needs_places
    proposed_dist = Counter()  # cuisine slug -> count (reliable proposals)
    gap_dist = Counter()  # enum-addition label -> count
    report: list[dict] = []

    for p in rows:
        name = p.provider_name or ""
        primary = p.google_primary_category
        cats = p.google_categories
        snippets = getattr(p, "google_review_snippets", None)
        current = derive_cuisine(primary, cats)
        if current is not None:
            tier["already"] += 1
            continue
        # Unknown → classify on NAME + Google types only (snippets are evidence,
        # never a match). No hit → enum-gap / LLM / Places tier; never force-fit.
        proposal = _propose_deterministic(name, primary, cats)
        gap = _enum_gap(primary, cats)
        gap_label = ""
        if proposal is not None:
            source, bucket = "name/type", "reliable"
            proposed_dist[proposal] += 1
        elif gap is not None:
            source, bucket, gap_label = "enum_gap", "enum_gap", gap
            gap_dist[gap] += 1
        elif _has_google_signal(primary, cats):
            source, bucket = "llm", "needs_llm"
        else:
            source, bucket = "llm_or_places", "needs_places"
        tier[bucket] += 1
        report.append(
            {
                "slug": p.slug or "",
                "name": name,
                "address": (p.address or "").split(",", 1)[0],
                "google_primary_category": primary or "",
                "google_categories": "|".join(str(c) for c in (cats or []))[:120],
                "snippet_excerpt": _snippet_excerpt(snippets),
                "current_cuisine": "",
                "proposed_cuisine": proposal or "",
                "proposed_label": cuisine_label(proposal) or "",
                "enum_gap": gap_label,
                "source": source,
                "tier": bucket,
            }
        )

    cols = (
        "slug", "name", "address", "google_primary_category", "google_categories",
        "snippet_excerpt", "current_cuisine", "proposed_cuisine", "proposed_label",
        "enum_gap", "source", "tier",
    )
    out_path = Path(_REPORT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(cols))
        for r in report:
            w.writerow([r[k] for k in cols])

    # ---- summary to the run log --------------------------------------------
    print("=== CUISINE BACKFILL DRY-RUN (restaurants leaf) ===")
    print(f"total restaurants scanned          : {total}")
    print(f"  already classified (facet ok)    : {tier['already']}")
    unknown = tier["reliable"] + tier["enum_gap"] + tier["needs_llm"] + tier["needs_places"]
    print(f"  UNKNOWN (backfill target)        : {unknown}")
    print(f"    - RELIABLE (name/Google-type)  : {tier['reliable']}  (safe; still needs your OK)")
    print(f"    - enum-gap (no home; stay unknown): {tier['enum_gap']}  (propose enum addition)")
    print(f"    - needs LLM (has Google signal): {tier['needs_llm']}  (one-shot LLM pass)")
    print(f"    - needs LLM/Places (no type)   : {tier['needs_places']}  (LLM by name; else Places fetch)")
    print("\nRELIABLE proposals by cuisine:")
    for slug in cuisine_slugs_in_order():
        if proposed_dist.get(slug):
            print(f"    {slug:<14} {proposed_dist[slug]}")
    if gap_dist:
        print("\nENUM-GAP additions proposed (separate list — rows stay unknown):")
        for label, n in gap_dist.most_common():
            print(f"    {label:<16} {n}")

    print("\n=== RELIABLE proposals (safe tier — for your glance) ===")
    for r in [x for x in report if x["tier"] == "reliable"]:
        ev = r["google_primary_category"] or r["google_categories"].split("|")[0] or "name-only"
        print(f"  {r['name'][:34]:<34} [{ev[:24]:<24}] → {r['proposed_label']}")

    print(f"\nreport written: {out_path}")
    print("DRY RUN — no catalog writes. Review with Casey before any gated apply (prod-data gate).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
