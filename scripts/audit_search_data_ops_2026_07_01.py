"""READ-ONLY report for the 2026-07-01 consolidated Phase-3 data ops.

Produces the counts + row lists Casey approves before
``apply_search_data_ops_2026_07_01.py`` runs. Sections (master audit =
ASKHAVA_FULL_SITE_AUDIT_2026-07-01_MASTER; plan = PROMPT_CC_SEARCH_CONSOLIDATED
Amendment 1):

  A  specialist re-home candidates out of the 159-row primary-care leaf (3.2)
  B  06-30 remainder targets, current state (3.3)
  C  placeholder visitor-center addresses still on rows (3.3)
  D  out-of-area ACTIVE rows on LHC surfaces (3.7 / [ASK #8] input)
  E  same-phone provider duplicate clusters (3.4 / master 3.1)
  F  live-event (title, date, time, venue) duplicate clusters (3.5 / master 3.4)
  G  integrity counts: zero-leaf actives (orphans) + zero-contact ghosts (3.6/3.9)

Nothing is written. Usage:
    .venv\\Scripts\\python.exe scripts/audit_search_data_ops_2026_07_01.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.contrib.ingest_suppression import is_placeholder_address  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Event, Provider  # noqa: E402

# Specialty signals scanned over primary-care member names. Order matters: a
# name carrying BOTH a pediatric and another specialty signal ("Adult and
# Pediatric Urology") is the specialty, not pediatrics.
_SPECIALIST_RE = re.compile(
    r"heart|vascular|cardio|obgyn|obstetric|gynecol|women'?s|podiat|\bdpm\b|"
    r"foot\s*(?:&|and)\s*ankle|urolog|oncolog|orthoped|imaging|radiolog|"
    r"neurolog|\bent\b|ear,?\s*nose",
    re.IGNORECASE,
)
_PEDIATRIC_RE = re.compile(r"pediatric|paediatric", re.IGNORECASE)

_OUT_OF_AREA_RE = re.compile(
    r"\b(kingman|bullhead|parker|needles|laughlin|oatman|topock|golden shores|"
    r"fort mohave|mohave valley|yucca|peach springs|havasu landing)\b",
    re.IGNORECASE,
)

_PHONE_DIGITS = re.compile(r"\d")
_TITLE_WS = re.compile(r"\s+")


def _norm_phone(phone: str | None) -> str:
    digits = "".join(_PHONE_DIGITS.findall(phone or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def _norm_text(s: str | None) -> str:
    return _TITLE_WS.sub(" ", (s or "").strip().lower())


def main() -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print("CONSOLIDATED PHASE-3 DATA-OPS AUDIT — READ-ONLY")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        # ------------------------------------------------------------- A
        print("--- A. primary-care specialist re-home candidates (3.2) ---")
        pc = db.query(Category).filter(Category.slug == "primary-care").first()
        ped, spec = [], []
        if pc is None:
            print("  primary-care leaf not found")
        else:
            for ec in db.query(EntityCategory).filter(EntityCategory.category_id == pc.id).all():
                ent = db.get(Entity, ec.entity_id)
                if ent is None or not ent.is_active:
                    continue
                name = ent.name or ""
                if _SPECIALIST_RE.search(name):
                    spec.append((name, ec.is_primary))
                elif _PEDIATRIC_RE.search(name):
                    ped.append((name, ec.is_primary))
            for name, prim in sorted(spec):
                print(f"  -> medical-specialists-and-imaging  {'PRIMARY' if prim else 'link   '}  {name}")
            for name, prim in sorted(ped):
                print(f"  -> pediatrics                       {'PRIMARY' if prim else 'link   '}  {name}")
            print(f"  totals: specialists={len(spec)}  pediatrics={len(ped)}")

        # ------------------------------------------------------------- B
        print("\n--- B. 06-30 remainder targets, current state (3.3) ---")
        for frag in ("%Designated Operator Program%", "%Outdoor Enthusiasts%",
                     "The Spot%", "%HavaLife%", "%Custom T%", "%Hava Math%",
                     "%Stingrays%", "%Steelhead%", "%London Bridge Jet Boat%"):
            rows = db.query(Provider).filter(Provider.provider_name.ilike(frag)).all()
            if not rows:
                print(f"  {frag}: NO ROWS")
            for p in rows:
                slugs = []
                if p.entity_id:
                    slugs = [s for (s,) in
                             db.query(Category.slug)
                             .join(EntityCategory, EntityCategory.category_id == Category.id)
                             .filter(EntityCategory.entity_id == p.entity_id).all()]
                print(f"  {p.provider_name!r}  active={p.is_active}  leaves={slugs}")

        # ------------------------------------------------------------- C
        print("\n--- C. placeholder visitor-center addresses (3.3) ---")
        actives = db.query(Provider).filter(
            Provider.is_active.is_(True), Provider.draft.is_(False)).all()
        ph = [p for p in actives if is_placeholder_address(p.address)]
        print(f"  ACTIVE provider rows still carrying it: {len(ph)}")
        for p in sorted(ph, key=lambda p: p.provider_name or ""):
            print(f"    {p.provider_name}")

        # ------------------------------------------------------------- D
        print("\n--- D. out-of-area ACTIVE rows ([ASK #8] input, 3.7) ---")
        ooa = [p for p in actives if _OUT_OF_AREA_RE.search(p.address or "")]
        for p in sorted(ooa, key=lambda p: p.provider_name or ""):
            m = _OUT_OF_AREA_RE.search(p.address or "")
            print(f"    {(p.provider_name or '')[:44]:44s}  [{m.group(0).title()}]")
        print(f"  total: {len(ooa)} (address-signal only; name-only OOA rows appear in G)")

        # ------------------------------------------------------------- E
        print("\n--- E. same-phone duplicate clusters (3.4) ---")
        by_phone: dict[str, list[Provider]] = defaultdict(list)
        for p in actives:
            ph10 = _norm_phone(p.phone)
            if len(ph10) == 10:
                by_phone[ph10].append(p)
        n_clusters = 0
        for ph10, rows in sorted(by_phone.items()):
            if len(rows) < 2:
                continue
            n_clusters += 1
            print(f"    {ph10}: " + " | ".join(sorted(p.provider_name or "?" for p in rows)))
        print(f"  clusters: {n_clusters} (includes legit multi-listing chains — dedupe by name+address)")

        # ------------------------------------------------------------- F
        print("\n--- F. live-event duplicate clusters (3.5) ---")
        by_key: dict[tuple, list[Event]] = defaultdict(list)
        for ev in db.query(Event).filter(Event.status == "live").all():
            key = (_norm_text(ev.title), ev.date, ev.start_time, _norm_text(ev.location_name))
            by_key[key].append(ev)
        clusters = {k: v for k, v in by_key.items() if len(v) > 1}
        shown = 0
        for (title, day, t, venue), evs in sorted(clusters.items(), key=lambda kv: (kv[0][1] or "", kv[0][0]))[:60]:
            print(f"    x{len(evs)}  {day} {t or ''}  {title[:44]:44s}  @{venue[:24]}")
            shown += 1
        extra_rows = sum(len(v) - 1 for v in clusters.values())
        print(f"  clusters: {len(clusters)} (showing {shown}) — {extra_rows} redundant rows")

        # ------------------------------------------------------------- G
        print("\n--- G. integrity counts (3.6/3.9 planning) ---")
        linked_eids = {eid for (eid,) in db.query(EntityCategory.entity_id).distinct().all()}
        orphans = [p for p in actives if p.entity_id and p.entity_id not in linked_eids]
        ghosts = [p for p in actives if not (p.address or "").strip() and not (p.phone or "").strip()]
        print(f"  active providers with ZERO entity_categories links: {len(orphans)}")
        for p in sorted(orphans, key=lambda p: p.provider_name or "")[:40]:
            print(f"    {p.provider_name}")
        if len(orphans) > 40:
            print(f"    … +{len(orphans) - 40} more")
        print(f"  active providers with NO address AND NO phone: {len(ghosts)}")

    print("\nREAD-ONLY — nothing written. Companion apply script: "
          "apply_search_data_ops_2026_07_01.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
