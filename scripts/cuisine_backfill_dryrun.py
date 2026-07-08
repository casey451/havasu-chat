"""WS9a cuisine backfill — READ-ONLY dry-run proposal report.

Scope: the Eat & Drink **restaurants** leaf (the page the ``?cuisine=`` facet
filters). Today a card's cuisine is DERIVED at render time from Google Places
types (``app.categories.subcategories.derive_cuisine`` over
``google_primary_category`` + ``google_categories``). Restaurants whose Google
types carry no cuisine token (or that have no Google types at all) show no
cuisine and are invisible to the facet — this report proposes a cuisine for
them, into the SAME fixed enum the facet already uses.

Two proposal tiers, cheapest first (mirrors the WS9a spec):
  1. **deterministic** — name / Google primary type / review snippets carry a
     cuisine keyword (extended needle map below). Free, reproducible, no API.
  2. **needs_llm** — a real restaurant with signal (a Google type and/or review
     snippets) but no keyword hit: the ambiguous remainder a one-shot LLM pass
     over name+type+snippets would classify. This script does NOT call the LLM
     (spend gate) — it only SIZES and SAMPLES that bucket.
  3. **needs_places** — no Google types at all: needs a Places ``types`` fetch
     (API cost) before either tier can run.

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


def _text_blob(name: str, primary: str | None, cats, snippets) -> str:
    parts = [name or "", primary or ""]
    if isinstance(cats, list):
        parts += [str(c) for c in cats]
    if isinstance(snippets, list):
        for s in snippets[:5]:
            if isinstance(s, dict):
                parts.append(str(s.get("text") or s.get("snippet") or ""))
    return " ".join(parts).lower()


def _propose_deterministic(name, primary, cats, snippets) -> str | None:
    """First keyword hit into the fixed enum, or None (→ LLM/Places tier)."""
    blob = _text_blob(name, primary, cats, snippets)
    for slug in cuisine_slugs_in_order():
        for needle in _NEEDLES.get(slug, ()):  # 'american' absent → skipped
            if needle in blob:
                return slug
    return None


def _has_google_signal(primary, cats, snippets) -> bool:
    return bool(primary) or bool(cats) or bool(snippets)


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
    tier = Counter()  # already / deterministic / needs_llm / needs_places
    proposed_dist = Counter()  # cuisine slug -> count (deterministic proposals)
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
        # Unknown → try to propose.
        proposal = _propose_deterministic(name, primary, cats, snippets)
        if proposal is not None:
            source, bucket = "deterministic", "deterministic"
            proposed_dist[proposal] += 1
        elif _has_google_signal(primary, cats, snippets):
            source, bucket, proposal = "llm", "needs_llm", ""
        else:
            source, bucket, proposal = "places", "needs_places", ""
        tier[bucket] += 1
        report.append(
            {
                "slug": p.slug or "",
                "name": name,
                "address": (p.address or "").split(",", 1)[0],
                "google_primary_category": primary or "",
                "google_categories": "|".join(str(c) for c in (cats or []))[:120],
                "current_cuisine": "",
                "proposed_cuisine": proposal,
                "proposed_label": cuisine_label(proposal) or "",
                "source": source,
                "tier": bucket,
            }
        )

    out_path = Path(_REPORT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["slug", "name", "address", "google_primary_category", "google_categories",
             "current_cuisine", "proposed_cuisine", "proposed_label", "source", "tier"]
        )
        for r in report:
            w.writerow([r[k] for k in (
                "slug", "name", "address", "google_primary_category", "google_categories",
                "current_cuisine", "proposed_cuisine", "proposed_label", "source", "tier")])

    # ---- summary to the run log --------------------------------------------
    print("=== CUISINE BACKFILL DRY-RUN (restaurants leaf) ===")
    print(f"total restaurants scanned      : {total}")
    print(f"  already classified (facet ok): {tier['already']}")
    unknown = tier["deterministic"] + tier["needs_llm"] + tier["needs_places"]
    print(f"  UNKNOWN (backfill target)    : {unknown}")
    print(f"    - deterministic proposal   : {tier['deterministic']}  (free, this run)")
    print(f"    - needs LLM (has signal)   : {tier['needs_llm']}  (paid one-shot LLM pass)")
    print(f"    - needs Places types fetch : {tier['needs_places']}  (no Google types; API cost)")
    print("\ndeterministic proposals by cuisine:")
    for slug in cuisine_slugs_in_order():
        if proposed_dist.get(slug):
            print(f"    {slug:<14} {proposed_dist[slug]}")

    print("\n=== 15 SAMPLE PROPOSALS ===")
    det = [r for r in report if r["tier"] == "deterministic"]
    llm = [r for r in report if r["tier"] == "needs_llm"]
    samples = (det[:10] + llm[:5]) or report[:15]
    for r in samples[:15]:
        prop = r["proposed_label"] or f"<{r['tier']}>"
        print(f"  [{r['source']:<13}] {r['name'][:34]:<34} | google={r['google_primary_category'][:26]:<26} → {prop}")

    print(f"\nreport written: {out_path}")
    print("DRY RUN — no catalog writes. Review with Casey before any gated apply (prod-data gate).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
