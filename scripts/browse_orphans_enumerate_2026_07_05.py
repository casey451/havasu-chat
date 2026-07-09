"""Session 6a Phase 1 — recompute browse-orphans from LIVE state (READ-ONLY).

A **browse-orphan** = an ACTIVE, provider-backed entity that renders on **zero
shipping leaf** (invisible to browse / leaf-search) because of bad
categorization. This script recomputes them against the live DB using the same
leaf-page contract the site renders through
(``app/categories/leaf_pages.py::_leaf_provider_query`` + ``_gate_counts``,
``LEAF_PAGE_MIN_PROVIDERS = 1``) — it does NOT reuse the stale 2026-07-01 "131".

Read-only: SELECTs plus one review CSV. No DB writes, no ``--apply``. Phase 2
(the gated repoint / deactivate apply) waits on Casey's review of the CSV.

Per-cause buckets (why the entity renders nowhere):
  (a) no ``is_primary`` entity_categories row at all;
  (b) primary points at a level-0 department, a non-leaf, or a dangling/retired
      category id (a leaf must be level-1 under a level-0 parent);
  (c) primary points at a level-1 leaf that is itself below the publish gate
      (the whole leaf 404s, so its members vanish);
  (d) primary points at a shipping leaf, but the entity's only active/non-draft
      provider(s) are all ``is_local = False`` — the locality filter drops them
      from the provider rows AND the ``backed_eids`` guard keeps them out of the
      place-card fallback, so they render nowhere.

Note on ``draft``: under the current contract a draft/inactive provider does NOT
strand — the entity falls through to a **place card** (``_leaf_entity_rows``
minus ``backed_eids``), so it still renders on a shipping leaf. Only
``is_local = False`` on an *active, non-draft* provider genuinely masks. The
report prints a draft-only tally separately for transparency.

Review buckets (what to do about it — Phase 2):
  A. Stranded in-city business → repoint the primary to a correct leaf
     (proposed leaf attached; leaf choice is a judgment call → CSV review).
  B. Out-of-area → ``is_local = False`` OR an address/city token in
     {parker, kingman, needles, topock} (Session-5 removal signal).
  C. Dedup twin → normalized name near-matches a *different* active, rendering
     entity (the canonical page is still live).

Legitimate place-type entities (Site Six, parks, London Bridge / lighthouse
trail) are excluded structurally — the population is provider-backed only, so
Provider-less civic places never enter it; a defensive name guard drops any
place-named stragglers.

Usage:
    .venv\\Scripts\\python.exe scripts\\browse_orphans_enumerate_2026_07_05.py
    .venv\\Scripts\\python.exe scripts\\browse_orphans_enumerate_2026_07_05.py --csv <path>
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.leaf_pages import LEAF_PAGE_MIN_PROVIDERS, _gate_counts  # noqa: E402
from app.categories.subcategories import derive_primary_category  # noqa: E402
from app.contrib.leaf_type_mapping import map_google_types_to_leaf_slug  # noqa: E402
from app.contrib.name_leaf_rules import leaf_for_name  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Category,
    Entity,
    EntityCategory,
    Location,
    Provider,
)
from scripts.backfill_new_monetization_leaves_2026_06 import match_new_leaf  # noqa: E402

# Bucket-B out-of-area address/city tokens (plan §buckets — the Session-5 set).
_OOA_TOKENS = ("parker", "kingman", "needles", "topock")

# Defensive place-name guard: provider-backed rows that are really civic places
# should never be repointed/deactivated as businesses. The population is
# provider-backed so these are rare, but guard by name anyway.
_PLACE_NAME_RE = re.compile(
    r"\bsite six\b|\blondon bridge\b|\blighthouse\b|\bstate park\b"
    r"|\bcommunity park\b|\bsara park\b|\brotary park\b|\bbeach\b",
    re.I,
)

# Name normalization for dedup-twin detection.
_NAME_SUFFIX_RE = re.compile(
    r"\b(llc|l\.l\.c|inc|incorporated|co|corp|corporation|company|ltd|lp|"
    r"pllc|pc|the|and|&)\b"
)
_NAME_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")


def _norm_name(name: str | None) -> str:
    s = (name or "").lower()
    s = _NAME_PUNCT_RE.sub(" ", s)
    s = _NAME_SUFFIX_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def _primary_type(p: Provider) -> str:
    """The provider's authoritative Google PRIMARY type (never a secondary)."""
    gpc = (p.google_primary_category or "").strip()
    if gpc:
        return gpc
    cats = p.google_categories or []
    if isinstance(cats, list) and cats:
        return str(cats[0]).strip()
    return ""


def _propose_leaf(
    p: Provider, live_leaf_slugs: set[str]
) -> tuple[str, str]:
    """``(proposed_leaf_slug, proposer)`` for a stranded (bucket-A) provider.

    Decreasing reliability (plan §leaf-proposal): Google PRIMARY type →
    single-hit name rules (martial-arts/dance + the 2026-06 monetization-leaf
    name matcher). Only a slug that is a live level-1 leaf is emitted; anything
    else is blanked so the CSV never proposes a non-existent target. Blank when
    no confident proposal — Casey fills those.
    """
    ptype = _primary_type(p)
    slug, _non_directory = map_google_types_to_leaf_slug([ptype] if ptype else [])
    if slug and slug in live_leaf_slugs:
        return slug, "google_primary_type"
    # Conservative name signal (martial-arts / dance — kinds Google can't type).
    name_slug = leaf_for_name(p.provider_name)
    if name_slug and name_slug in live_leaf_slugs:
        return name_slug, "name_rule"
    # 2026-06 monetization-leaf name matcher (auto-glass, junk-removal, garage-
    # doors, painters, property-management, hearing, …). Single-hit / None.
    mono_slug = match_new_leaf(p.provider_name, ptype or None, p.google_categories)
    if mono_slug and mono_slug in live_leaf_slugs:
        return mono_slug, "name_rule_mono"
    return "", ""


def _dept_hint(p: Provider) -> str:
    """Coarse legacy dept-level primary category (one of the 13), or ''.

    NOT a leaf — recorded only as a manual-fill hint for the review CSV, never
    proposed as ``proposed_leaf``.
    """
    return (
        derive_primary_category(
            category=p.category,
            subcategory=p.subcategory,
            name=p.provider_name,
            google_primary_category=p.google_primary_category,
            google_categories=p.google_categories,
            attributes=p.attributes,
        )
        or ""
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--csv",
        type=Path,
        default=_ROOT / "docs" / "audits" / "2026-07" / "browse_orphans_review_2026-07-05.csv",
        help="Path for the review CSV (default: docs/audits/2026-07/...).",
    )
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print("BROWSE-ORPHANS ENUMERATOR (read-only) — Session 6a Phase 1")
    print("=" * 78)
    print(f"DB target: …@{redacted}")
    print(f"gate: LEAF_PAGE_MIN_PROVIDERS = {LEAF_PAGE_MIN_PROVIDERS}\n")

    with SessionLocal() as db:
        # --- taxonomy: categories + which leaves ship -----------------------
        cats = {c.id: c for c in db.query(Category).all()}
        shipping_leaf_ids = set(_gate_counts(db).keys())  # level-1 leaves at/above gate
        live_leaf_slugs = {
            c.slug for c in cats.values() if c.level == 1
        }
        print(
            f"categories: {len(cats)}  live leaves (level-1): {len(live_leaf_slugs)}  "
            f"shipping leaves (>= gate): {len(shipping_leaf_ids)}\n"
        )

        # --- population: providers on ACTIVE entities, grouped by entity ----
        prov_rows = (
            db.query(Provider, Entity)
            .join(Entity, Provider.entity_id == Entity.id)
            .filter(Entity.is_active.is_(True))
            .all()
        )
        providers_by_entity: dict[str, list[Provider]] = defaultdict(list)
        entity_by_id: dict[str, Entity] = {}
        for prov, ent in prov_rows:
            providers_by_entity[ent.id].append(prov)
            entity_by_id[ent.id] = ent

        # --- primary links for every active entity (any type) --------------
        # (used both for cause detection and to compute the rendering set)
        primary_links: dict[str, list[int]] = defaultdict(list)
        active_entity_ids = {
            eid for (eid,) in db.query(Entity.id).filter(Entity.is_active.is_(True))
        }
        for eid, cid in (
            db.query(EntityCategory.entity_id, EntityCategory.category_id)
            .filter(EntityCategory.is_primary.is_(True))
            .all()
        ):
            if eid in active_entity_ids:
                primary_links[eid].append(cid)

        # --- location city/address for OOA tokens --------------------------
        loc_by_entity: dict[str, Location] = {
            loc.entity_id: loc
            for loc in db.query(Location).filter(
                Location.entity_id.in_(list(active_entity_ids))
            )
        }

        # ---- helper: does an entity render on ANY shipping leaf? ----------
        def _active_nondraft(eid: str) -> list[Provider]:
            return [
                p
                for p in providers_by_entity.get(eid, [])
                if p.is_active and not p.draft
            ]

        def _masked_on_shipping(eid: str) -> bool:
            """True when the entity has active/non-draft providers but ALL are
            ``is_local = False`` — so it renders nowhere even on a shipping leaf
            (cause d). No active/non-draft provider → place card → not masked."""
            andp = _active_nondraft(eid)
            if not andp:
                return False
            return all(p.is_local is False for p in andp)

        def _renders(eid: str) -> bool:
            """Whether the entity actually renders on some shipping leaf."""
            for cid in primary_links.get(eid, ()):
                c = cats.get(cid)
                if c is None or c.level != 1:
                    continue
                if cid not in shipping_leaf_ids:
                    continue
                if not _masked_on_shipping(eid):
                    return True
            return False

        # Rendering set across ALL active entities (for twin canonicity) ----
        # Pull names for every active entity (incl. Provider-less place rows) so
        # a business twinning a civic place is still caught.
        rendering_norm_names: dict[str, list[str]] = defaultdict(list)
        ent_name_by_id: dict[str, str] = {
            eid: (name or "")
            for eid, name in db.query(Entity.id, Entity.name).filter(
                Entity.id.in_(list(active_entity_ids))
            )
        }
        for eid in active_entity_ids:
            if _renders(eid):
                nn = _norm_name(ent_name_by_id.get(eid))
                if nn:
                    rendering_norm_names[nn].append(eid)

        def _twin_of(eid: str, name: str) -> str:
            """Name of a DIFFERENT active, rendering entity this row twins, or ''.
            Exact normalized-name hit first, then a tight fuzzy pass (>= 0.90)."""
            nn = _norm_name(name)
            if not nn:
                return ""
            for other in rendering_norm_names.get(nn, ()):
                if other != eid:
                    return ent_name_by_id.get(other, "")
            for cand_nn, ids in rendering_norm_names.items():
                if cand_nn == nn:
                    continue
                if abs(len(cand_nn) - len(nn)) > 6:
                    continue
                if SequenceMatcher(None, nn, cand_nn).ratio() >= 0.90:
                    for other in ids:
                        if other != eid:
                            return ent_name_by_id.get(other, "")
            return ""

        # ---- classify the provider-backed population ----------------------
        cause_counts: Counter = Counter()
        bucket_counts: Counter = Counter()
        draft_only_masked = 0
        place_guard_skipped = 0
        rows: list[dict] = []

        for eid, provs in providers_by_entity.items():
            ent = entity_by_id[eid]

            if _renders(eid):
                continue  # visible somewhere — not an orphan

            # Defensive: never treat a civic place row as a stranded business.
            if _PLACE_NAME_RE.search(ent.name or ""):
                place_guard_skipped += 1
                continue

            prims = primary_links.get(eid, [])

            # --- cause (priority d > c > b > a among this entity's primaries) ---
            cause = None
            current_leaf_slug = ""
            if not prims:
                cause = "a"
            else:
                saw_dept = saw_below_gate = saw_masked = False
                for cid in prims:
                    c = cats.get(cid)
                    if current_leaf_slug == "" and c is not None:
                        current_leaf_slug = c.slug
                    if c is None or c.level != 1:
                        saw_dept = True
                    elif cid not in shipping_leaf_ids:
                        saw_below_gate = True
                    else:
                        # level-1 shipping leaf reached but entity didn't render
                        # (guaranteed here since _renders was False) → masked.
                        saw_masked = True
                if saw_masked:
                    cause = "d"
                elif saw_below_gate:
                    cause = "c"
                elif saw_dept:
                    cause = "b"
                else:
                    cause = "a"

            cause_counts[cause] += 1

            # transparency: draft/inactive-only provider that would place-card
            # (does NOT strand) — should never land here, but count if it does.
            if not _active_nondraft(eid) and cause == "d":
                draft_only_masked += 1

            # --- bucket (B out-of-area > C dedup-twin > A stranded) ---------
            loc = loc_by_entity.get(eid)
            hay = " ".join(
                str(v or "").lower()
                for v in (
                    ent.name,
                    getattr(loc, "city", "") if loc else "",
                    getattr(loc, "address", "") if loc else "",
                    *[p.address or "" for p in provs],
                    *[p.city if hasattr(p, "city") else "" for p in provs],
                )
            )
            is_ooa = any(p.is_local is False for p in provs) or any(
                tok in hay for tok in _OOA_TOKENS
            )
            twin_name = "" if is_ooa else _twin_of(eid, ent.name)

            if is_ooa:
                bucket = "B"
            elif twin_name:
                bucket = "C"
            else:
                bucket = "A"
            bucket_counts[bucket] += 1

            # --- proposed leaf (bucket A only) -----------------------------
            proposed_leaf = ""
            proposer = ""
            dept_hint = ""
            p0 = provs[0]
            if bucket == "A":
                proposed_leaf, proposer = _propose_leaf(p0, live_leaf_slugs)
                if not proposed_leaf:
                    dept_hint = _dept_hint(p0)

            rows.append(
                {
                    "entity_id": eid,
                    "provider_name": (p0.provider_name or ent.name or "").strip(),
                    "google_primary_category": _primary_type(p0),
                    "current_leaf_slug": current_leaf_slug,
                    "proposed_leaf": proposed_leaf,
                    "proposer": proposer,
                    "bucket": bucket,
                    "cause": cause,
                    "twin_of": twin_name,
                    "dept_hint": dept_hint,
                }
            )

    # ---- write the review CSV ---------------------------------------------
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "entity_id",
        "provider_name",
        "google_primary_category",
        "current_leaf_slug",
        "proposed_leaf",
        "proposer",
        "bucket",
        "cause",
        "twin_of",
        "dept_hint",
    ]
    rows.sort(key=lambda r: (r["bucket"], r["cause"], r["provider_name"].lower()))
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # ---- report -----------------------------------------------------------
    total = len(rows)
    cause_label = {
        "a": "a  no is_primary entity_categories row",
        "b": "b  primary → department / non-leaf / dangling category",
        "c": "c  primary → level-1 leaf below the publish gate (leaf 404s)",
        "d": "d  primary → shipping leaf, but is_local=False masks the provider",
    }
    bucket_label = {
        "A": "A  stranded in-city business  (repoint to a correct leaf)",
        "B": "B  out-of-area                (deactivate — Session-5 pattern)",
        "C": "C  dedup twin                 (collapse the retired twin)",
    }
    print(f"BROWSE-ORPHANS (provider-backed, active): {total}\n")
    print("per-cause:")
    for k in ("a", "b", "c", "d"):
        print(f"  {cause_counts.get(k, 0):>4}  {cause_label[k]}")
    print("\nper-bucket:")
    for k in ("A", "B", "C"):
        print(f"  {bucket_counts.get(k, 0):>4}  {bucket_label[k]}")

    a_rows = [r for r in rows if r["bucket"] == "A"]
    proposed = sum(1 for r in a_rows if r["proposed_leaf"])
    print(
        f"\nbucket A proposals: {proposed}/{len(a_rows)} have a proposed leaf "
        f"({len(a_rows) - proposed} blank → Casey fills)"
    )
    by_proposer = Counter(r["proposer"] for r in a_rows if r["proposer"])
    for name, n in by_proposer.most_common():
        print(f"    {n:>4}  {name}")
    if place_guard_skipped:
        print(f"\nplace-name guard skipped: {place_guard_skipped} civic-place rows")
    if draft_only_masked:
        print(f"draft-only (place-card, not truly stranded): {draft_only_masked}")

    print(f"\nreview CSV: {args.csv}")
    print("\nREAD-ONLY — nothing written to prod. Phase 2 waits on CSV review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
