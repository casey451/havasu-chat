"""T3.1/T3.2 read-only audit — name-pattern misfiles by source leaf.

Scans each audit-named "problem leaf" for providers whose NAME signals they are
misfiled, and writes a review CSV: current leaf, provider, matched pattern, and a
SUGGESTED target leaf (only when a confirmed existing leaf fits) or NEEDS_DECISION
(when the correct home is a new/ambiguous leaf — e.g. a Mortgage leaf that does
not exist yet, a Casey call).

**Read-only.** No catalog writes. This is the input to the gated reclassify script
(a follow-up) once targets are confirmed.

    .venv\\Scripts\\python.exe scripts\\misfile_audit_2026_07_06.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

_REPORT_CSV = "docs/audits/2026-07/misfile_audit_2026-07-06.csv"

# (source_leaf, pattern_regex, suggested_target_leaf_or_None). None target =>
# NEEDS_DECISION (correct home is a new or ambiguous leaf; do not auto-move).
_RULES: list[tuple[str, str, str | None]] = [
    # Med spas that are really schools / wellness / fitness.
    ("med-spas-and-aesthetics", r"\bacademy\b|\bschool\b|\binstitute\b", "training"),
    ("med-spas-and-aesthetics", r"\biv\b|hydration|\bdrip\b|infusion", "nutrition-and-wellness"),
    ("med-spas-and-aesthetics", r"pilates|\byoga\b", "yoga-and-pilates"),
    # Car wash leaf holding detailers.
    ("car-wash", r"\bdetail|ceramic coat", "auto-detailing"),
    # Banks holding mortgage brokers / loan officers -> needs a Mortgage leaf (new).
    ("banks-and-credit-unions", r"mortgage|\bloan\b|\bnmls\b|lending|loandepot", None),
    # Tattoo leaf holding permanent-makeup / microblading (cosmetic, not tattoo art).
    ("tattoo-and-piercing", r"permanent makeup|microblading|\bmicro ?blad", None),
    # Primary care holding specialists / non-PCP.
    ("primary-care", r"optometr|\boptical\b|\beye\b|vision center", None),
    ("primary-care", r"therapist|counsel|psycholog|behavioral", None),
    ("primary-care", r"\bgym\b|fitness|crossfit|pilates", None),
    # Pharmacies holding a physician assistant.
    ("pharmacies", r"\bpa-?c\b|physician assistant", None),
    # Dentists holding a dental LAB (not a practice).
    ("dentists-and-orthodontists", r"dental lab|\blab\b|laboratory", None),
    # General contractors holding single-trade HVAC.
    ("general-contractors", r"\bhvac\b|heating.{0,4}cooling|air condition|refrigerat", None),
    # Auto repair holding pool / storage / non-auto.
    ("auto-repair", r"\bpool\b|self.?storage|\bstorage\b|mini.?storage", None),
]


def main() -> int:
    with SessionLocal() as db:
        leaf_by_slug = {c.slug: c for c in db.scalars(select(Category).where(Category.level == 1)).all()}

        def active_in_leaf(leaf_id):
            return db.scalars(
                select(Provider).select_from(Provider)
                .join(Entity, Entity.id == Provider.entity_id)
                .join(EntityCategory, EntityCategory.entity_id == Entity.id)
                .where(EntityCategory.category_id == leaf_id, EntityCategory.is_primary.is_(True),
                       Provider.is_active.is_(True), Provider.draft.is_(False))
                .order_by(Provider.provider_name)
            ).all()

        rows_out: list[dict] = []
        seen: set[tuple[str, str]] = set()  # (provider_id, source_leaf) — first rule wins
        for source_leaf, pattern, target in _RULES:
            leaf = leaf_by_slug.get(source_leaf)
            if leaf is None:
                print(f"WARN source leaf {source_leaf!r} not found — skipped")
                continue
            target_exists = target is not None and target in leaf_by_slug
            suggested = target if target_exists else "NEEDS_DECISION"
            rx = re.compile(pattern, re.I)
            for p in active_in_leaf(leaf.id):
                if not rx.search(p.provider_name or ""):
                    continue
                key = (str(p.id), source_leaf)
                if key in seen:
                    continue
                seen.add(key)
                rows_out.append({
                    "current_leaf": source_leaf,
                    "provider_id": str(p.id),
                    "provider_name": p.provider_name,
                    "matched_pattern": pattern,
                    "suggested_target": suggested,
                    "phone": p.phone or "",
                    "website": p.website or "",
                })

    out = Path(_REPORT_CSV)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "current_leaf", "provider_id", "provider_name", "matched_pattern",
            "suggested_target", "phone", "website",
        ])
        w.writeheader()
        w.writerows(rows_out)

    by_leaf: Counter[str] = Counter(r["current_leaf"] for r in rows_out)
    needs = sum(1 for r in rows_out if r["suggested_target"] == "NEEDS_DECISION")
    print(f"misfile candidates: {len(rows_out)}  (auto-target={len(rows_out) - needs}  NEEDS_DECISION={needs})")
    for lf_slug, n in by_leaf.most_common():
        print(f"  {lf_slug:32} {n}")
    print(f"\nreport written: {out}")
    print("READ-ONLY audit — no writes. Confirm targets before any reclassify apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
