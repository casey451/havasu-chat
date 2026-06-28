"""Batch-13 read-only probe: Professional/Civic misfiles + dupes.

READ-ONLY. SELECT-only, ZERO writes. Surfaces the audit's Professional & Money /
Community & Civic misfiles whose TARGET leaf already exists (title-and-escrow,
accountants-and-tax, notary), plus clear retracts (SEO-keyword junk, OOA) and
duplicate clusters.

Sections:
  1. TITLE AGENCIES mis-filed under Insurance -> title-and-escrow.
  2. ATTORNEYS leaf misfiles (D Tax -> accountants; paralegals counted/HELD).
  3. FINANCIAL-ADVISORS junk (HBC Motors, SEO-keyword stubs).
  4. NONPROFITS for-profit injects (Quick Stop, Teri Parcells).
  5. PHOTOGRAPHERS out-of-area (PhotoAiD).
  6. DUPE CLUSTERS (Guild / Chase / Primary Residential / UniSource).

HELD for Batch 14 (need a NEW leaf): mortgage brokers out of Banks (no mortgage
leaf), paralegals out of Attorneys (no legal-doc-prep leaf).

    .venv\\Scripts\\python.exe scripts/audit_directory_batch13_professional_2026_06_27.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

_PARALEGAL_RE = re.compile(
    r"(paralegal|legal document|document prep|legal wizard|legal zoom|"
    r"\bzion\b|tt'?s|infinity legal|majestic)", re.I)


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 84)
    print("BATCH-13 PROFESSIONAL / CIVIC MISFILE PROBE  (READ-ONLY — no rows written)")
    print("=" * 84)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        cat_by_slug = {c.slug: c for c in db.query(Category).filter(Category.level == 1).all()}
        provs_by_entity: dict[str, list[Provider]] = {}
        for p in db.query(Provider).all():
            provs_by_entity.setdefault(p.entity_id, []).append(p)

        def members(slug: str) -> list[Entity]:
            cat = cat_by_slug[slug]
            ids = {ec.entity_id for ec in db.query(EntityCategory).filter(
                EntityCategory.category_id == cat.id, EntityCategory.is_primary.is_(True)).all()}
            return [e for e in db.query(Entity).filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place"))).all() if e.id in ids]

        def rev(e: Entity) -> int:
            ps = provs_by_entity.get(e.id, [])
            return max((p.google_review_count or 0) for p in ps) if ps else 0

        def show(e: Entity) -> str:
            pr = sorted(provs_by_entity.get(e.id, []), key=lambda p: -(p.google_review_count or 0))
            addr = (pr[0].address[:26] if pr and pr[0].address else "")
            return f"rev={rev(e):>4d} src={e.source[:11]:11s} {e.name[:38]:38s} | {addr}"

        # 1. TITLE in Insurance
        print("-" * 84)
        print("1. TITLE AGENCIES under Insurance -> title-and-escrow")
        for e in sorted(members("insurance"), key=lambda e: -rev(e)):
            if "title" in (e.name or "").lower():
                print(f"   {show(e)}")
        print(f"   (title-and-escrow currently has {len(members('title-and-escrow'))} members)")

        # 2. Attorneys
        print("\n" + "-" * 84)
        print("2. ATTORNEYS misfiles")
        att = members("attorneys")
        for e in att:
            n = (e.name or "").lower()
            if "d tax" in n or n.startswith("d tax"):
                print(f"   D-TAX -> accountants-and-tax: {show(e)}")
            elif "sweet peas" in n:
                print(f"   NON-ATTY (retract?): {show(e)}")
        paras = [e for e in att if _PARALEGAL_RE.search(e.name or "")]
        print(f"   paralegal/doc-prep in attorneys (HELD, need leaf): {len(paras)}")
        for e in sorted(paras, key=lambda e: -rev(e))[:12]:
            print(f"      {show(e)}")

        # 3. Financial advisors junk
        print("\n" + "-" * 84)
        print("3. FINANCIAL-ADVISORS junk")
        for e in members("financial-advisors"):
            n = (e.name or "").lower()
            if "hbc motors" in n:
                print(f"   HBC MOTORS (-> car dealer): {show(e)}")
            if "hard money" in n or "commercial lending" in n:
                print(f"   SEO-STUB (retract): {show(e)}")

        # 4. Nonprofits
        print("\n" + "-" * 84)
        print("4. NONPROFITS for-profit injects")
        for e in members("nonprofits-and-charities"):
            n = (e.name or "").lower()
            if "quick stop" in n:
                print(f"   QUICK STOP (-> government-and-mvd): {show(e)}")
            if "teri parcells" in n or "parcells" in n:
                print(f"   TERI PARCELLS (-> notary): {show(e)}")

        # 5. Photographers OOA
        print("\n" + "-" * 84)
        print("5. PHOTOGRAPHERS out-of-area")
        for e in members("photographers"):
            if "photoaid" in (e.name or "").lower():
                print(f"   PHOTOAID (retract, Poland): {show(e)}")

        # 6. Dupe clusters
        print("\n" + "-" * 84)
        print("6. DUPE CLUSTERS")
        for label, slugs, key in (
            ("Guild Mortgage", ("banks-and-credit-unions", "financial-advisors"), "guild"),
            ("Chase Home Lending", ("banks-and-credit-unions", "financial-advisors"), "chase"),
            ("Primary Residential", ("banks-and-credit-unions", "financial-advisors"), "primary residential"),
        ):
            seen: list[Entity] = []
            for slug in slugs:
                for e in members(slug):
                    if key in (e.name or "").lower():
                        seen.append(e)
            print(f"\n  {label}  ({len(seen)})")
            for e in sorted(seen, key=lambda e: -rev(e)):
                print(f"     {show(e)}")
        print("\n" + "=" * 84)
        print("READ-ONLY. Your eyeball before apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
