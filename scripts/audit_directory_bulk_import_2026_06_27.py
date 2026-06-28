"""Directory-audit triage: bulk-import junk, mailbox-as-storefront, shadow dupes.

READ-ONLY. Surfaces the high-precision signatures called out in
``askhava-directory-audit.md`` so the operator can decide what to verify / retract.
SELECT-only — ZERO writes, no commit — the dry-run half of the
dry-run -> show-counts -> approve -> apply protocol. Safe against prod.

Sections (each is a count + a capped sample; nothing is applied):

  1. BULK-IMPORT SIGNATURE — rows whose address is the placeholder
     "Go Lake Havasu Visitor Center" and/or whose phone is the visitor center's
     own number 800-242-8278. These are unverified auto-imports (generic
     activities like "Bird Watching"/"Splash Pads" and out-of-area sites).
  2. MAILBOX-AS-STOREFRONT — rows whose address is 1642 McCulloch Blvd N (the
     A+ Mail / Havasu Mail & Package Centre), i.e. rented mailbox suites listed
     as if they were storefronts.
  3. SHADOW DUPLICATES — active providers sharing a normalized name, where the
     cluster looks like a real listing + a thin "New / Visit-only" mirror (one
     member has reviews, another has none). Chains with distinct addresses are
     down-weighted so genuine multi-location brands don't dominate.
  4. OUT-OF-AREA — providers explicitly flagged is_local=False (already hidden
     from leaf pages, but still live rows). Counted by stored primary_category.

Usage (operator runs in the prod env; default DATABASE_URL from repo .env):
    .venv\\Scripts\\python.exe scripts/audit_directory_bulk_import_2026_06_27.py
    .venv\\Scripts\\python.exe scripts/audit_directory_bulk_import_2026_06_27.py --sample 40
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Names carry emoji/accents; force UTF-8 so the probe never dies under cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Entity, Provider  # noqa: E402

# --- signatures --------------------------------------------------------------

# The bulk-import placeholder address and the visitor center's own phone.
_VISITOR_CENTER_ADDR_RE = re.compile(r"go\s+lake\s+havasu\s+visitor\s+center", re.IGNORECASE)
_VISITOR_CENTER_DIGITS = "8002428278"  # 800-242-8278
# 1642 McCulloch Blvd N == the A+ Mail / Havasu Mail & Package Centre.
_MAILBOX_ADDR_RE = re.compile(r"\b1642\s+mcculloch\b", re.IGNORECASE)


def _norm(s: str | None) -> str:
    return (s or "").strip()


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _norm_name(s: str | None) -> str:
    """Aggressive name key for duplicate clustering: lowercase, punctuation and
    trailing entity suffixes dropped, whitespace collapsed."""
    n = (s or "").lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\b(llc|inc|incorporated|co|corp|ltd|the)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _has_reviews(p: Provider) -> bool:
    return bool(p.google_review_count)


# --- run ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Directory bulk-import / dupe triage (read-only).")
    ap.add_argument("--sample", type=int, default=30, help="rows to print per section")
    args = ap.parse_args(argv)
    sample = max(args.sample, 1)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 76)
    print("DIRECTORY BULK-IMPORT / DUPE TRIAGE  (READ-ONLY — no rows written)")
    print("=" * 76)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        providers = db.query(Provider).all()
        active = [p for p in providers if p.is_active and not p.draft]
        print(f"providers total: {len(providers)}   active non-draft: {len(active)}\n")

        # 1. BULK-IMPORT SIGNATURE -------------------------------------------
        addr_hits = [p for p in active if _VISITOR_CENTER_ADDR_RE.search(_norm(p.address))]
        phone_hits = [p for p in active if _VISITOR_CENTER_DIGITS in _digits(p.phone)]
        sig = {p.id: p for p in addr_hits}
        sig.update({p.id: p for p in phone_hits})
        sig_rows = sorted(sig.values(), key=lambda p: _norm(p.provider_name).lower())
        print("-" * 76)
        print("1. BULK-IMPORT SIGNATURE (visitor-center placeholder addr / phone)")
        print(f"   address == 'Go Lake Havasu Visitor Center': {len(addr_hits)}")
        print(f"   phone   == 800-242-8278:                    {len(phone_hits)}")
        print(f"   union (distinct rows):                       {len(sig_rows)}")
        for p in sig_rows[:sample]:
            why = []
            if _VISITOR_CENTER_ADDR_RE.search(_norm(p.address)):
                why.append("addr")
            if _VISITOR_CENTER_DIGITS in _digits(p.phone):
                why.append("phone")
            print(f"     [{'+'.join(why):10s}] {_norm(p.provider_name)[:44]:44s} "
                  f"| cat={_norm(p.primary_category)[:24]:24s} | rev={p.google_review_count}")
        if len(sig_rows) > sample:
            print(f"     … +{len(sig_rows) - sample} more")
        print()

        # 2. MAILBOX-AS-STOREFRONT -------------------------------------------
        mbox = sorted(
            [p for p in active if _MAILBOX_ADDR_RE.search(_norm(p.address))],
            key=lambda p: _norm(p.provider_name).lower(),
        )
        print("-" * 76)
        print("2. MAILBOX-AS-STOREFRONT (1642 McCulloch Blvd N — A+ Mail suites)")
        print(f"   rows: {len(mbox)}")
        for p in mbox[:sample]:
            print(f"     {_norm(p.provider_name)[:44]:44s} | {_norm(p.address)[:40]:40s} "
                  f"| cat={_norm(p.primary_category)[:20]}")
        if len(mbox) > sample:
            print(f"     … +{len(mbox) - sample} more")
        print()

        # 3. SHADOW DUPLICATES (entity-level) --------------------------------
        # Dedup keys on the ENTITY, not the Provider, so a provider-less place
        # mirror ("Visit"-only Avalon Park / SARA Park) is caught alongside the
        # real listing. Each entity is annotated with its active provider (if any)
        # and that provider's review count, exposing the "real + thin mirror" shape.
        # Directory listings only — exclude calendar events/programs (which
        # legitimately repeat the same title, e.g. "Lap Swim" recurring sessions).
        entities = (
            db.query(Entity)
            .filter(
                Entity.is_active.is_(True),
                Entity.entity_type.in_(("commercial", "place")),
            )
            .all()
        )
        prov_by_entity: dict[str, Provider] = {}
        for p in active:
            # Prefer the better-reviewed provider when an entity has more than one.
            cur = prov_by_entity.get(p.entity_id)
            if cur is None or (p.google_review_count or 0) > (cur.google_review_count or 0):
                prov_by_entity[p.entity_id] = p

        eclusters: dict[str, list[Entity]] = defaultdict(list)
        for e in entities:
            key = _norm_name(e.name)
            if key:
                eclusters[key].append(e)

        def _erev(e: Entity) -> int:
            pr = prov_by_entity.get(e.id)
            return (pr.google_review_count or 0) if pr else 0

        # A cluster is a likely shadow-dupe when >=2 active entities share a name
        # AND it is not a genuine multi-location chain (every member provider-backed
        # WITH reviews). The tell: at least one member is a thin/provider-less mirror.
        suspects: list[tuple[str, list[Entity]]] = []
        for key, rows in eclusters.items():
            if len(rows) < 2:
                continue
            all_real_chain = all(
                (e.id in prov_by_entity and _erev(e) > 0) for e in rows
            )
            if not all_real_chain:
                suspects.append((key, rows))
        suspects.sort(key=lambda kr: (-len(kr[1]), kr[0]))
        dup_rows = sum(len(r) for _, r in suspects)
        print("-" * 76)
        print("3. SHADOW DUPLICATES (entity-level; real listing + thin 'New/Visit' mirror)")
        print(f"   active entities scanned: {len(entities)}")
        print(f"   suspect clusters: {len(suspects)}   entities involved: {dup_rows}")
        for key, rows in suspects[:sample]:
            print(f"     '{key[:42]}'  (x{len(rows)})")
            for e in sorted(rows, key=lambda e: -_erev(e)):
                backed = "prov" if e.id in prov_by_entity else "PLACE"
                print(f"        - [{backed:5s}] rev={_erev(e):>4d} "
                      f"type={e.entity_type[:10]:10s} src={e.source[:14]:14s} {e.name[:30]}")
        if len(suspects) > sample:
            print(f"     … +{len(suspects) - sample} more clusters")
        print()

        # 4. OUT-OF-AREA ------------------------------------------------------
        ooa = [p for p in active if p.is_local is False]
        by_cat = Counter(_norm(p.primary_category) or "(none)" for p in ooa)
        print("-" * 76)
        print("4. OUT-OF-AREA (is_local=False — already hidden from leaf pages)")
        print(f"   rows: {len(ooa)}")
        for cat, n in by_cat.most_common(sample):
            print(f"     {n:4d}  {cat}")
        print()

        print("=" * 76)
        print("Nothing was written. Review the counts/samples above; the retract or "
              "re-home pass is a separate, operator-approved --apply step.")
        print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
