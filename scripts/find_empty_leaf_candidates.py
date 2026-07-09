"""Find hand-tagging candidates for the empty 2026-06-19 monetization leaves.

READ-ONLY diagnostic — writes nothing to the DB ever (no --apply). The strict
backfill (``backfill_new_monetization_leaves_2026_06.py``) only moves providers
on a high-confidence name signal; this companion casts a DELIBERATELY WIDE net
(loose, recall-oriented tokens across name + primary type + secondary Google
categories) so a human can eyeball who actually exists in the data and tag them
onto the right leaf. Expect false positives — that's the point; you prune.

For each candidate it prints the provider, the matched token, and its CURRENT
primary leaf, so you can decide whether a move is warranted. Optionally writes a
CSV with the entity_id for easy tagging.

    .venv\\Scripts\\python.exe scripts\\find_empty_leaf_candidates.py
    .venv\\Scripts\\python.exe scripts\\find_empty_leaf_candidates.py --csv candidates.csv

Targets the five leaves the name-matcher left empty by default; pass --all to
search every 2026-06-19 leaf.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

# Loose, recall-oriented search tokens per leaf — broader than the strict
# matcher's needles. Substring match against lowercased name + primary type +
# secondary categories. Tuned for RECALL (catch maybes); the human prunes.
SEARCH_TOKENS: dict[str, tuple[str, ...]] = {
    "window-tint-and-wraps": ("tint", "wrap", "vinyl", "ppf", "clear bra", "paint protection"),
    "marine-supply": (
        "marine", "boat part", "boat supply", "boat accessor", "propeller",
        "prop shop", "nautical", "chandler", "boat dealer",
    ),
    "junk-removal-and-hauling": (
        "junk", "haul", "dump", "debris", "cleanout", "clean out", "demo ",
    ),
    "shade-screens-and-patio-covers": (
        "shade", "sun screen", "sunscreen", "awning", "patio cover", "canopy",
        "ramada", "misting", "mister", "patio",
    ),
    "painters": ("paint", "coating", "stucco", "drywall", "finish"),
}

# Extra leaves searchable with --all (the live ones, to find MORE listings).
EXTRA_TOKENS: dict[str, tuple[str, ...]] = {
    "golf-carts": ("golf cart", "golf car", "cart "),
    "off-road-shops-and-accessories": ("off road", "offroad", "off-road", "4x4", "lift kit", "side by side", "utv", "overland"),
    "auto-glass": ("glass", "windshield", "auto glass"),
    "trailer-sales-and-repair": ("trailer",),
    "garage-doors": ("garage door", "overhead door"),
    "pressure-washing-and-exterior-cleaning": ("pressure wash", "power wash", "soft wash", "wash"),
    # 2026-06-19 combined Golf hub: find courses + driving range/Toptracer +
    # indoor simulators to tag onto golf-courses. ("golf" also catches golf-cart
    # dealers — ignore those rows; they belong on golf-carts.)
    "golf-courses": (
        "golf", "driving range", "toptracer", "top tracer", "golf simulator",
        "indoor golf", "virtual golf", "putting",
    ),
}


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _haystack(name, primary, categories) -> str:
    parts = [name or "", primary or ""]
    if categories:
        if isinstance(categories, str):
            parts.append(categories)
        else:
            try:
                parts.extend(str(t) for t in categories)
            except TypeError:
                parts.append(str(categories))
    return re.sub(r"\s+", " ", " ".join(parts).lower())


def run(*, csv_path: Path | None = None, search_all: bool = False, session=None) -> int:
    own = session is None
    session = session or SessionLocal()
    try:
        print(f"DB target: {_sanitized_target()} (READ-ONLY)\n")
        tokens = dict(SEARCH_TOKENS)
        if search_all:
            tokens.update(EXTRA_TOKENS)

        cat_by_id = {c.id: c for c in session.query(Category).all()}
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
        print(f"scanned {len(providers)} active providers\n")

        rows: list[dict] = []
        seen: set[tuple[str, str]] = set()  # (entity_id, leaf) dedupe
        for leaf, toks in tokens.items():
            for p in providers:
                eid = p.entity_id
                if eid is None:
                    continue
                hay = _haystack(p.provider_name, p.google_primary_category, p.google_categories)
                hit = next((t for t in toks if t in hay), None)
                if hit is None or (eid, leaf) in seen:
                    continue
                seen.add((eid, leaf))
                cur = cat_by_id.get(current_primary.get(eid))
                rows.append(
                    {
                        "suggested_leaf": leaf,
                        "matched_token": hit.strip(),
                        "provider_name": (p.provider_name or "").strip(),
                        "google_primary_category": p.google_primary_category or "",
                        "current_leaf_slug": cur.slug if cur else "",
                        "entity_id": eid,
                    }
                )

        for leaf in tokens:
            group = [r for r in rows if r["suggested_leaf"] == leaf]
            print(f"== {leaf} — {len(group)} candidate(s) ==")
            for r in sorted(group, key=lambda r: r["provider_name"].lower()):
                cur = r["current_leaf_slug"] or "(none)"
                print(
                    f"  {r['provider_name'][:42]:42s} | now: {cur[:28]:28s} "
                    f"| match '{r['matched_token']}'"
                )
            print()

        if csv_path and rows:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(f"wrote {len(rows)} candidate rows to {csv_path}")

        print(
            "\nREAD-ONLY — nothing written. To tag a provider onto a leaf, set its primary"
            "\nentity_categories link (the backfill script's apply path does this for"
            "\nname-confident matches; for these review-only candidates, tag via the admin"
            "\nor a one-off you approve)."
        )
        return 0
    finally:
        if own:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Find hand-tagging candidates for empty leaves (read-only).")
    ap.add_argument("--csv", type=Path, default=None, help="Write candidates to this CSV.")
    ap.add_argument("--all", action="store_true", help="Also search the already-live 2026-06-19 leaves.")
    args = ap.parse_args(argv)
    return run(csv_path=args.csv, search_all=args.all)


if __name__ == "__main__":
    raise SystemExit(main())
