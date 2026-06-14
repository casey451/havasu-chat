"""Report divergence between the two category layers (READ-ONLY).

The app stores a provider's category in two independent places:

* ``providers.primary_category`` — one of the 13 canonical primaries; drives
  Home / Explore / Map / Chat.
* ``entity_categories`` (primary link) — a finer leaf under a 15-root tree;
  drives the directory category / leaf pages.

They are assigned by different code and can silently disagree (that is how
"Whiz Kid" showed under Tattoo on the leaf pages while its primary_category was
already shopping/computer). This script joins the two and reports rows whose
``entity_categories`` root domain maps to a *different* canonical primary than
``providers.primary_category``. It makes NO writes — it is a divergence report
to size the problem and feed a future reconciliation policy.

Usage:
    python scripts/reconcile_category_layers.py            # summary
    python scripts/reconcile_category_layers.py --csv out.csv
"""

from __future__ import annotations

# Read-only diagnostic: providers.primary_category vs entity_categories leaf domain.
import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

_ROOT = Path(__file__).resolve().parents[1]

# entity_categories ROOT slug -> the canonical 13-primary it corresponds to.
ROOT_TO_PRIMARY: dict[str, str] = {
    "eat-and-drink": "eat-drink",
    "on-the-water": "on-the-water",
    "outdoors-and-recreation": "outdoors-parks-trails",
    "things-to-do-and-attractions": "events",
    "health-and-medical": "health-wellness-care",
    "beauty-and-personal-care": "health-wellness-care",
    "fitness-and-wellness": "classes-sports-recreation",
    "home-and-property-services": "home-property-services",
    "auto-rv-and-marine": "auto-rv-fuel",
    "shopping-and-retail": "shopping-essentials",
    "professional-and-financial": "professional-services",
    "family-and-education": "classes-sports-recreation",
    "community-and-civic": "public-civic-resources",
    "lodging": "lodging-vacation-rentals",
    "pets": "pets",
}


def _dsn() -> dict:
    env = (_ROOT / ".env").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^DATABASE_URL=(.+)$", env, re.M)
    if not m:
        raise SystemExit("DATABASE_URL not found in .env")
    u = urlparse(m.group(1).strip().strip('"').replace("+psycopg2", ""))
    return dict(host=u.hostname, port=u.port, user=u.username,
                password=u.password, dbname=(u.path or "/").lstrip("/").strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    args = ap.parse_args()
    conn = psycopg2.connect(**_dsn())
    cur = conn.cursor()
    cur.execute(
        """
        select p.provider_name, p.primary_category,
               leaf.slug as ec_leaf, coalesce(root.slug, leaf.slug) as ec_root
        from entity_categories ec
        join providers p on p.entity_id = ec.entity_id and coalesce(p.is_active, true)
        join categories leaf on leaf.id = ec.category_id
        left join categories root on root.id = leaf.parent_id
        where ec.is_primary = true and p.primary_category is not null
        """
    )
    diverge = []
    for name, prim, leaf, root in cur.fetchall():
        mapped = ROOT_TO_PRIMARY.get(root)
        if mapped and mapped != prim:
            diverge.append((name, prim, leaf, root, mapped))
    conn.close()

    print(f"Divergent rows (primary_category != entity_categories domain): {len(diverge)}")
    print("\n  count   providers.primary_category  ->  entity_categories domain")
    for (a, b), n in Counter((d[1], d[4]) for d in diverge).most_common(20):
        print(f"  {n:5d}   {a}  ->  {b}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "providers_primary", "ec_leaf", "ec_root", "ec_domain_primary"])
            w.writerows(diverge)
        print(f"\nWrote {len(diverge)} rows to {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
