"""Audit: bogus / non-business / junk provider listings (READ-ONLY).

Surfaces the auto-imported junk that public surfaces should not show — the
"Havasu" bakery shape: a Google-imported row that is a place name (not a
business), carries a mismatched photo, has zero real reviews, and was never
claimed. It scores every Provider against four operator-chosen signals and
emits a tiered flag list plus a dry-run removal plan. It makes ZERO writes.

Signals (operator spec, 2026-06-11):
  A. not-a-real-business  — name is a bare geographic/place token, OR the row's
     google_categories are ALL non-commercial POI types (landmark / park /
     natural_feature / tourist_attraction with no business type). Strongest
     when corroborated by zero reviews + no website + no phone.
  B. category-mismatch    — stored ``primary_category`` disagrees with the
     canonical ``derive_primary_category`` (same pure deriver the ingest +
     backfill paths use; no new classification heuristics introduced here).
  C. thin/empty-data      — missing >= 3 of {address, phone, website, hours,
     description, photo}.
  D. unclaimed+zero-reviews — Google-sourced row with no verified Claim AND
     google_review_count in (NULL, 0).

Protections (never auto-recommended for removal):
  * Provider.verified is True, OR the entity has a verified Claim.
  * Sponsored / paid tier rows (tier != "free" or sponsored_until in future).
  * Rows already hidden (is_active = False or draft = True) — reported under a
    separate "already-hidden" bucket, not the removal plan.

Review/photo signals (C-photo, D) apply only to Google-sourced rows
(``google_place_id IS NOT NULL``); event/program/seed providers legitimately
carry no Google reviews and are not penalised for it.

Recommended action mirrors this repo's "bury, don't delete" philosophy
(liveness ranking, LIVENESS_RANKING_HANDOFF_2026-06-03): high-confidence rows
are proposed for soft-deactivation (is_active = False), NOT hard deletion.
This is the dry-run half of the dry-run -> show-counts -> approve -> apply
protocol; an --apply companion is intentionally NOT part of this file.

Usage (runs against whatever DATABASE_URL is set; for prod the operator runs it
in the prod env, read-only):
    .venv\\Scripts\\python.exe scripts\\audit_bogus_listings.py
    .venv\\Scripts\\python.exe scripts\\audit_bogus_listings.py --csv flagged.csv
    .venv\\Scripts\\python.exe scripts\\audit_bogus_listings.py --min-conf high
    railway run python scripts/audit_bogus_listings.py --csv flagged_prod.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

# Provider/event names can contain emoji; force UTF-8 so the probe never dies on
# a stray character under a cp1252 console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.subcategories import derive_primary_category  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Claim, Provider  # noqa: E402

# --- signal vocabularies -----------------------------------------------------

# Bare geographic / place tokens that are never a business name on their own.
PLACE_NAMES = {
    "havasu", "lake havasu", "lake havasu city", "lake havasu city, az",
    "arizona", "az", "london bridge", "colorado river", "lake", "river",
    "beach", "site six", "windsor beach", "rotary park", "the channel",
}

# Google place types that describe a POI / geography rather than a business.
POI_TYPES = {
    "point_of_interest", "establishment", "natural_feature", "locality",
    "political", "tourist_attraction", "premise", "geocode", "route",
    "street_address", "neighborhood", "park", "sublocality",
    "administrative_area_level_1", "administrative_area_level_2",
    "colloquial_area", "landmark",
}

# A bare place-name fires only when the WHOLE name is essentially a geographic
# feature — anchored end-to-end. A descriptive title that merely STARTS with a
# geo word ("Lake Havasu Retreat w/ Pool & Spa") is NOT a place name; that was
# the 2026-06-11 false-positive that buried vacation rentals under "place name".
_PLACE_FULL_RE = re.compile(
    r"^\s*(lake havasu( city)?|london bridge|colorado river|site six|"
    r"windsor beach|rotary park|the channel|havasu)\s*$",
    re.IGNORECASE,
)

# Short-term / vacation rental titles. Whether STRs belong in the directory at
# all is an OPERATOR POLICY CALL, so these are bucketed separately ("str-rental")
# and routed to manual-review — never auto-deactivated on the rental signal
# alone. Keyword cues are matched only when corroborated by a lodging category.
_STR_RE = re.compile(
    r"\b(retreat|getaway|oasis|sleeps\s*\d|hot tub|heated pool|"
    r"pool\s*[,&/]+\s*spa|w/\s*pool|with pool|vacation rental|"
    r"casita|guest ?house|home w/|house w/|condo|villa|bnb|"
    r"private (?:pool|spa|dock)|firepit|fire pit)\b",
    re.IGNORECASE,
)
_LODGING_HINTS = {"lodging", "vacation_rental"}


def _norm(s: str | None) -> str:
    return (s or "").strip()


def _google_cats(p: Provider) -> list[str]:
    raw = p.google_categories
    if isinstance(raw, str):
        return [c for c in raw.split("|") if c]
    if isinstance(raw, (list, tuple)):
        return [str(c) for c in raw if c]
    return []


def _has_photo(p: Provider) -> bool:
    urls = p.google_photo_urls or []
    refs = p.google_photo_refs or []
    return bool([u for u in urls if u]) or bool(refs)


def _has_hours(p: Provider) -> bool:
    return bool(_norm(p.hours)) or bool(p.hours_structured) or bool(p.google_hours)


def _is_sponsored(p: Provider, now: datetime) -> bool:
    if _norm(p.tier) not in ("", "free"):
        return True
    su = p.sponsored_until
    if su is not None:
        if su.tzinfo is None:
            su = su.replace(tzinfo=UTC)
        if su > now:
            return True
    return False


# --- scoring -----------------------------------------------------------------

def score_provider(
    p: Provider, *, claimed_entity_ids: set[str], now: datetime
) -> tuple[int, list[str], dict]:
    """Return (score, reasons, signal_flags). Higher score = more bogus."""
    reasons: list[str] = []
    score = 0
    is_google = p.google_place_id is not None
    name = _norm(p.provider_name)
    nlow = name.lower()
    review_count = p.google_review_count if is_google else None
    zero_reviews = is_google and (review_count in (None, 0))

    # A. not-a-real-business -----------------------------------------------
    place_name = nlow in PLACE_NAMES or bool(_PLACE_FULL_RE.match(name))
    gcats = _google_cats(p)
    poi_only = bool(gcats) and all(c in POI_TYPES for c in gcats)
    if place_name:
        score += 3
        reasons.append("not-a-business: bare geographic/place name")
    if poi_only:
        # Weak signal: "point_of_interest|establishment" is the default Google
        # gives many legit small businesses it hasn't typed. +1 only, so it
        # needs real corroboration to reach the high (deactivate) tier.
        score += 1
        reasons.append(f"weak: POI-only google types ({'|'.join(gcats)})")
    # corroborators sharpen A but never flag on their own
    if (place_name or poi_only) and zero_reviews:
        score += 1
        reasons.append("corroborator: zero google reviews")
    if (place_name or poi_only) and not _norm(p.website) and not _norm(p.phone):
        score += 1
        reasons.append("corroborator: no website and no phone")

    # A'. short-term / vacation rental (OPERATOR POLICY — bucket, don't purge)
    legacy = _norm(getattr(p, "category", "")).lower()
    lodging_ctx = (
        legacy in _LODGING_HINTS
        or _norm(p.google_primary_category).lower() in _LODGING_HINTS
        or "lodging" in (_norm(p.primary_category).lower())
    )
    str_rental = bool(_STR_RE.search(name)) and (lodging_ctx or zero_reviews)
    if str_rental:
        score += 1
        reasons.append("str-rental: short-term/vacation rental title (policy review)")

    # B. category-mismatch --------------------------------------------------
    derived = derive_primary_category(
        category=p.category,
        subcategory=p.subcategory,
        google_primary_category=p.google_primary_category,
        google_categories=p.google_categories,
        attributes=p.attributes,
    )
    stored = _norm(p.primary_category) or None
    if derived and stored and derived != stored:
        score += 1
        reasons.append(f"category-mismatch: stored={stored} -> derived={derived}")

    # C. thin/empty-data ----------------------------------------------------
    missing = []
    if not _norm(p.address):
        missing.append("address")
    if not _norm(p.phone):
        missing.append("phone")
    if not _norm(p.website):
        missing.append("website")
    if not _has_hours(p):
        missing.append("hours")
    if not _norm(p.description) and not _norm(p.featured_description):
        missing.append("description")
    if is_google and not _has_photo(p):
        missing.append("photo")
    if len(missing) >= 3:
        score += 1
        reasons.append(f"thin-data: missing {', '.join(missing)}")

    # D. unclaimed + zero reviews ------------------------------------------
    unclaimed = p.entity_id not in claimed_entity_ids and not p.verified
    if is_google and unclaimed and zero_reviews:
        score += 1
        reasons.append("unclaimed + zero google reviews")

    flags = {
        "is_google": is_google,
        "review_count": review_count,
        "place_name": place_name,
        "poi_only": poi_only,
        "missing": "|".join(missing),
        "category_derived": derived or "",
        "category_stored": stored or "",
        "verified": bool(p.verified),
        "claimed": p.entity_id in claimed_entity_ids,
        "already_hidden": (not p.is_active) or bool(p.draft),
        "sponsored": _is_sponsored(p, now),
        "str_rental": str_rental,
        "zero_reviews": zero_reviews,
        "unclaimed": unclaimed,
    }
    return score, reasons, flags


def _confidence(score: int) -> str:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _recommended_action(conf: str, flags: dict) -> str:
    if flags["verified"] or flags["claimed"] or flags["sponsored"]:
        return "protected-skip"
    if flags["already_hidden"]:
        return "already-hidden"
    # Short-term rentals (operator policy 2026-06-11): an auto-imported rental
    # UNIT — descriptive rental title, unclaimed, zero reviews — is treated as
    # directory noise and soft-deactivated (reversible). A rental-flagged row
    # that someone claimed or that carries real reviews is a lodging *business*
    # and goes to a human instead.
    if flags["str_rental"]:
        if flags["unclaimed"] and flags["zero_reviews"]:
            return "deactivate (is_active=False)"
        return "manual-review (short-term-rental)"
    # Auto-deactivate is reserved for rows with a genuine place-name signal
    # (the lake, the bridge, a bare geo token). A high score driven only by a
    # weak POI type + thinness can still be a real-but-sparse business
    # ("London Bridge Beach boat rental"), so route those to a human.
    if conf == "high" and flags["place_name"]:
        return "deactivate (is_active=False)"
    if conf in ("high", "medium"):
        return "manual-review"
    return "watch"


# --- run ---------------------------------------------------------------------

def audit(min_conf: str, csv_path: str | None, limit_samples: int) -> int:
    db = SessionLocal()
    now = datetime.now(UTC)
    try:
        claimed = {
            row[0]
            for row in db.query(Claim.entity_id).filter(Claim.status == "verified").all()
        }
        providers = db.query(Provider).all()
        total = len(providers)

        results = []
        for p in providers:
            score, reasons, flags = score_provider(
                p, claimed_entity_ids=claimed, now=now
            )
            if score <= 0:
                continue
            conf = _confidence(score)
            results.append(
                {
                    "id": p.id,
                    "slug": p.slug or "",
                    "name": _norm(p.provider_name),
                    "score": score,
                    "confidence": conf,
                    "recommended_action": _recommended_action(conf, flags),
                    "reasons": "; ".join(reasons),
                    "google_place_id": p.google_place_id or "",
                    "review_count": "" if flags["review_count"] is None else flags["review_count"],
                    "category_stored": flags["category_stored"],
                    "category_derived": flags["category_derived"],
                    "missing": flags["missing"],
                    "verified": flags["verified"],
                    "claimed": flags["claimed"],
                    "sponsored": flags["sponsored"],
                    "already_hidden": flags["already_hidden"],
                    "str_rental": flags["str_rental"],
                    "source": p.source,
                }
            )

        rank = {"high": 0, "medium": 1, "low": 2}
        results.sort(key=lambda r: (rank[r["confidence"]], -r["score"], r["name"].lower()))

        keep = [r for r in results if rank[r["confidence"]] <= rank[min_conf]]

        # ---- dry-run report ------------------------------------------------
        print("=" * 72)
        print("BOGUS-LISTING AUDIT  (READ-ONLY DRY RUN — no rows written)")
        print("=" * 72)
        print(f"providers scanned:        {total}")
        print(f"verified claims (protected entities): {len(claimed)}")
        print(f"flagged (score > 0):      {len(results)}")
        print()

        by_conf = Counter(r["confidence"] for r in results)
        print("by confidence:")
        for c in ("high", "medium", "low"):
            print(f"  {c:7s}: {by_conf.get(c, 0)}")
        print()

        by_action = Counter(r["recommended_action"] for r in results)
        print("REMOVAL PLAN (recommended action — nothing applied):")
        for action, n in by_action.most_common():
            print(f"  {n:5d}  {action}")
        print()

        actionable = [
            r for r in results
            if r["recommended_action"].startswith("deactivate")
        ]
        print(f"=> {len(actionable)} rows proposed for soft-deactivation "
              f"(is_active=False). Review the CSV, then approve before any apply.")
        print()

        # sample the strongest reasons
        print(f"--- top {limit_samples} flagged (by score) ---")
        for r in results[:limit_samples]:
            print(f"  [{r['confidence']:6s} s{r['score']}] {r['name'][:38]:38s} "
                  f"| {r['recommended_action']:24s} | {r['reasons'][:70]}")

        if csv_path:
            fields = list(results[0].keys()) if results else []
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for r in keep:
                    w.writerow(r)
            print()
            print(f"wrote {len(keep)} rows (>= {min_conf}) to {csv_path}")

        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only bogus-listing audit (dry run).")
    ap.add_argument("--csv", default=None, help="write flagged rows to this CSV")
    ap.add_argument(
        "--min-conf",
        choices=("high", "medium", "low"),
        default="low",
        help="lowest confidence tier to include in the CSV (default: low = all)",
    )
    ap.add_argument("--limit-samples", type=int, default=20)
    args = ap.parse_args(argv)
    return audit(args.min_conf, args.csv, args.limit_samples)


if __name__ == "__main__":
    raise SystemExit(main())
