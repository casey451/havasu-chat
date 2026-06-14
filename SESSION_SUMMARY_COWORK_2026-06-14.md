# Ask Hava — Cowork Session Summary (2026-06-14)

Single source of truth for everything done in this session. Two halves:
**LIVE IN PROD now** (data writes, all reversible) and **MERGEABLE CODE**
(validated, sitting in the working tree for you to branch/commit/PR — nothing is
deployed until you merge).

---

## 1. LIVE IN PROD NOW (data — reversible, nothing deleted)

All writes are soft (`is_active=False`) or field reassignments, each with a JSON
undo snapshot in the repo root. 86 rows total.

| Change | Rows | Undo snapshot |
|---|---|---|
| §6.8 non-local hidden | 27 | `locality_snapshot_20260614T191212Z.json` |
| §6.3 hotels (VR / no-website) hidden | 27 | `hotels_audit_snapshot_20260614T192518Z.json` |
| §6.1 Quick Bites → Restaurants (subcategory move) | 30 | `merge_quick_bites_snapshot_20260614T192426Z.json` |
| §6.3 recat HEAT Bar→bars, Turtle Grille→restaurants | 2 | `recat_hotel_mislabels_snapshot_20260614T193425Z.json` |

Net: Hotels 59→30 real hotels; Restaurants +30; ~27 out-of-town listings hidden.
To undo any item: re-activate the ids in its snapshot (`is_active=True`, or
restore the prior subcategory/primary_category).

**Casinos (§6.7):** Bluewater (Parker) hidden via locality; Havasu Landing already
had its website; "Game Spot llc" and "Win Win Bingo Casino" kept (real local
businesses). **Library (§6.6):** kept both (the college's Hodel Library is
publicly open — the brief's "only one library" premise was incorrect).
**§6.9 verifiable-info sweep:** 0 flagged — every active listing already has a
website/phone/address/Google link.

---

## 2. MERGEABLE CODE (validated green: ruff clean; targeted pytest suites pass)

**Phase A — copy/nav**
- `app/templates/home_sandstone.html` — tagline → "Search like a local."; chips
  reordered (service last); hero trust strip removed; the two category grids
  consolidated into one (Explore) directly under the chips.
- `app/templates/desert_base.html` — trust line relocated to a site-wide footer row.
- `tests/test_home_fold_ux1.py` — updated for the new fold.

**Phase B — "On the Water" → "Lake Life"** (display labels only; slug kept)
- `app/home/queries.py`, `app/categories/queries.py`, `app/categories/subcategories.py`,
  `app/groups/themed_groups.py`, `app/home/queries_c.py`, `app/home/events_views.py`,
  `app/portal/products.py`, `app/home/router.py`, `app/home/sandstone.py`
- `tests/test_events_ui_views.py` (docstring), `tests/test_home_fold_ux1.py` (label)
- Decision: "Lake Life" = the directory category (chip + tile + nav →
  `/categories/on-the-water`); the URL slug stays `on-the-water` (SEO). The
  separate `/lake` curated-mode page still exists — reconcile/merge it later.

**Phase C — code** (data ops are in §1)
- `app/api/routes/category_pages.py` — removed the Vacation Rentals filter chip (§6.4).

**Phase F1 — Placement monetization data model** (additive; legacy Sponsor untouched)
- `app/db/monetization_models.py` — `Placement` + `PlacementPrice` (prices are
  data, not code → admin-editable). Placement types: `homepage_rotating`,
  `category_rank` (tiers 1–5), `page_ad`. Billing: monthly | recurring.
- `alembic/versions/b7c1f2a3d4e5_placements_monetization.py` — additive migration
  (two new tables), chains off `304cc3843188`.
- `app/db/__init__.py` — registers the new tables (cycle-safe).
- `tests/test_placement_model.py` — 3 tests.

**Phase F — serving logic + category-page hook**
- `app/monetization/serving.py` — sticky-tier §7.2 (`arrange_top5`,
  `apply_category_order`), homepage rotation §7.1 (`pick_homepage`), DB helpers.
- `app/api/routes/category_pages.py` — `_overlay_category_placements` hooked into
  `_sort_entity_ids`. **Dormant**: no placements sold → zero change to rendering.
- `tests/test_placement_serving.py` — 11 tests (tier-1 locked, tier-N within
  top-N, completeness, organic-preserving overlay, homepage pick).

**Alembic note:** the repo has a SINGLE head (healthy — an earlier "two heads"
alarm was a false positive from a static parse). I created a no-op merge
migration `alembic/versions/304cc3843188_*.py` before confirming that; it's a
harmless empty migration and is now the parent of `b7c1f2a3d4e5`. You can keep it
or `git rm` it (if you remove it, repoint `b7c1f2a3d4e5`'s `down_revision` to
`10c88d64d916`).

**How to merge:** feature branch off `main`, `python -m pytest -q` + `ruff check .`,
review the diff, PR. (Validation already passed on this machine; CI is the gate.)

---

## 3. OPS SCRIPTS (in `scripts/`, dry-run-gated, reusable)

Each is READ-ONLY by default; `--apply` writes + a JSON undo snapshot. Run as
`.venv\Scripts\python.exe scripts\<name>.py [--apply]`.
- `sweep_locality.py` (§6.8), `sweep_verifiable_info.py` (§6.9),
  `audit_hotels.py` (§6.3), `merge_quick_bites.py` (§6.1),
  `recategorize_hotel_mislabels.py`, `fix_casinos.py` (§6.7, precise/by-id).
- Inspectors (read-only, no writes): `inspect_casinos.py`, `inspect_food_lodging.py`,
  `inspect_cuisines.py`, `inspect_classes.py`.

---

## 4. DECISIONS LOCKED

- Payments processor: **Stripe**. Ad model: **Placement** (built). Portal/admin:
  **extend** existing, not greenfield.
- Cuisine landing pages (Phase D, §6.2) — build the 11 with 7+ listings:
  **Mexican (30), Cafés & Coffee (19), Breakfast & Brunch (19), Pizza (18),
  Sandwiches & Deli (18), Bakeries (18), Burgers & Fast Food (12),
  Dessert & Ice Cream (10), American (9), BBQ (7), Steakhouse (7).** Thinner
  cuisines (Japanese/Italian/Chinese/etc.) stay filters, not pages.
- Fitness subcategories (§3.2) reframed: class data is spread across Programs (22),
  recurring Events, and venue Schedules (classified by title), so §3.2 is a
  **calendar-grouping build (Phase E)**, not a data-table taxonomy. Proposed
  subcats: Yoga, Pilates/Barre, Martial Arts, Dance, Cycling/Spin,
  Strength/Conditioning, Aquatic (Open Swim → Kids & Family), Pickleball/Tennis,
  Gymnastics, Kids/Youth, Senior/Gentle.

---

## 5. KEY ARCHITECTURAL FINDINGS

- **Category rendering is multi-path.** The sticky-tier hook went into
  `_sort_entity_ids` (drives the themed-group/category-sort streams). The main
  leaf/niche listing pages (`/categories/{dept}/{leaf}`) render through a
  different path; the existing "Sponsored" badge is driven by
  `Provider.tier`/`sponsored_until`, which placements don't set. **Completing the
  display integration + honest "Sponsored" labeling requires mapping that path
  deliberately** — flagged, not rushed.
- Monetization integration is **dormant** until the portal can sell placements.
- **Honesty gate:** the "Sponsored clearly labeled" badge MUST ship before the
  first placement goes live (§7 requirement + trust). Build it with the portal.

---

## 6. REMAINING ROADMAP (prioritized)

1. Map the leaf/niche render path; extend the placement overlay there + add the
   "Sponsored" badge (honesty gate).
2. Wire the homepage rotating block (§7.1) into the marquee (dormant-safe).
3. Seed `placement_prices` with the brief's placeholder prices (admin-editable).
4. **F2** — ad creative model + standardized web/mobile sizes (§7.4).
5. **F3** — business portal: accounts/auth, self-serve purchase, monthly vs
   recurring, creative upload (§8).
6. **F4** — Stripe: subscriptions, refunds, transaction ledger → revenue tracking (§9).
7. **Phase E** — calendar reorg: kids-first, Open Swim → Kids & Family, fitness
   subcategories, and chat → interactive filtered calendar (§3, §5; evaluate the
   Stinger VPS only if web-layer caching isn't enough — likely it is).
8. **Phase G** — admin panel: listing editor, payments oversight, full analytics
   (search terms, time-on-page, funnels), content control, pricing UI (§10).
9. Build the cuisine landing pages on the Placement model (§6.2).

---

## 7. CLEANUP

Throwaway helper files in the repo root — safe to delete:
`del _run_*.bat _*.log` (the `_run_phasec_*.bat`, `_inspect_*`, `_f1*.log`,
`_alembic_merge.log`, `_ruff.log`, `_tests.log`, etc.). **Keep** the
`*_snapshot_*.json` files and audit CSVs — they're your undo/audit trail.
