# Ask Hava search coverage — fix + punch-list (2026-06-20)

**Reported by Casey:** typing `pool builders` (also `pool cleaners`, and many
other plain service terms) into Ask Hava returns "sorry, no results" instead of
a page listing the businesses that do that service.

## Root cause

The Ask Hava search box submits to `GET /chat?q=…` → `serve_chat` →
`leaf_query.match_leaf_query()`. That matches the query against a hand-maintained
dictionary, `_QUERY_TO_LEAF` (in `app/categories/leaf_query.py`), which maps a
phrasing to a category/leaf page. On a hit you're 302-redirected to that page; on
a miss the query falls through to a conversational answer that often ends in
"no results."

`pools-and-spas` **already exists and has businesses** — but only `"pool service"`
and `"pool cleaning"` were wired to it. `"pool builders"`, `"pool cleaners"`,
`"pool repair"`, etc. were never in the dictionary, so they fell through. The same
gap existed across the whole taxonomy: agent-noun forms (`-er`/`-ers`), many
plurals, and most synonyms were missing, and **five rendering pages had zero
search terms at all** (`quick-bites-and-takeout` = 29 businesses,
`kids-classes-and-camps` = 19, `specialty-food` = 8, `colleges-and-higher-ed` = 6,
`vacation-rentals` = 3).

## What was fixed in code (this change)

Pages that **already exist and render** are now reachable by every plausible
phrasing. No data/DB work required — pure routing.

- `app/categories/leaf_query.py` — added **731 new search terms across 121
  leaves** (`_QUERY_TO_LEAF_EXPANSION_2026_06_20`) plus 8 bare single-word forms
  (`_QUERY_TO_LEAF_BARE_FORMS_2026_06_20`), merged with `setdefault` so existing
  entries always win (zero key collisions). Covers agent-noun/plural/synonym
  forms and the five zero-term pages above.
- `app/chat/normalizer.py` — added ~48 high-frequency category/trade misspelling
  aliases (e.g. `resteraunt→restaurant`, `matress→mattress`, `jewlery→jewelry`,
  `poool→pool`). These apply at every chat layer. Correctly-spelled terms already
  benefit from the existing fuzzy corrector now that the vocabulary grew.
- `tests/test_search_coverage_2026_06_20.py` — new DB-free tests: the exact
  `pool *` regression, broad routing samples, misspellings, and structural drift
  guards.

**Examples now routing correctly:** `pool builders`, `pool cleaners`,
`pool repair`, `swimming pool`, `hot tub repair`, `roofing contractors`,
`house cleaners`, `tree service`, `tow truck`, `animal hospital`, `law firm`,
`eye doctor`, `quick bites`, `takeout`, `tacos`, `butcher shop`, `summer camps`,
`college`, `vacation rental`, `jewelry`, `vape`, plus misspellings and
`…in lake havasu` / `near me` / `best …` variants.

### Gate (must run on Windows / CI — not the sandbox)

The Cowork sandbox mount serves stale/truncated copies of edited files (see
`CLAUDE.md`), so I could not run the suite here. Before merging, on your machine:

```
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
```

Routing logic was validated independently (41/41 cases) against the term list,
but `pytest` + `ruff` are the authoritative gate.

---

## Punch-list — services that still return nothing (need a PAGE + real businesses)

These can't be fixed by routing alone: the destination page either doesn't exist
yet or has no businesses categorized into it. Per your note ("if there's one guy
who picks up dog poop, the page will have one listing"), each needs (1) the leaf
created/seeded in the taxonomy and (2) the real Havasu businesses tagged into it —
a **production DB backfill**, which per `CLAUDE.md` runs dry-run → show counts →
your approval → apply.

### B1 — leaf already designed but not seeded (synonyms ALREADY wired; self-activate when the page ships)

These slugs are in `PENDING_LEAF_SLUGS`; their search terms are already in the
dictionary and will start working the moment the page exists with ≥1 business.

| Service | Leaf slug | Search terms already wired |
|---|---|---|
| Junk removal / hauling | `junk-removal-and-hauling` | junk removal, junk hauling |
| Property management | `property-management` | property management, property managers |
| Laundromat / dry cleaning | `laundry-and-dry-cleaning` | laundromat(s), dry cleaners, dry cleaning |
| Auto glass / windshield | `auto-glass` | auto glass, windshield repair/replacement |
| Golf carts (sales/repair) | `golf-carts` | golf carts, golf cart repair/sales |
| Window tint & wraps | `window-tint-and-wraps` | window tint(ing), vehicle/car wraps |
| Trailer sales & repair | `trailer-sales-and-repair` | trailer repair, trailer sales |
| Funeral / cremation / cemeteries | `funeral-cremation-and-cemeteries` | funeral home(s), cremation, mortuaries, cemeteries |
| Hearing aids / audiology | `hearing-and-audiology` | hearing aids, audiologist(s), hearing centers |
| Pressure washing | `pressure-washing-and-exterior-cleaning` | pressure washing, power washing |
| Mobile home services | `mobile-home-services` | mobile home repair/services |
| Shade screens / patio covers | `shade-screens-and-patio-covers` | patio covers, sun screens, awnings, shade structures |
| Pet waste removal | `pet-waste-removal` | pet waste removal, pooper scooper |
| Firearms / shooting sports | `firearms-and-shooting-sports` | gun stores/shops, firearms, shooting range(s) |
| Medical specialists / imaging | `medical-specialists-and-imaging` | *(no terms wired yet — add when seeded)* |

### B2 — common trades/shops with NO leaf and NO mapping (need a brand-new page)

These are real services people will search for that the taxonomy has no home for
today. Each needs a new leaf + synonyms + businesses:

- **Painting** — painter(s), house painting
- **Flooring** — flooring, carpet/tile/laminate install, floor installers
- **Fencing** — fence companies, fence install/repair
- **Drywall** — drywall, drywall repair
- **Concrete / masonry** — concrete, masonry, pavers, stucco
- **Carpentry / cabinets** — carpenter(s), custom cabinets, countertops
- **Welding / metal fabrication** — welder(s), fabrication
- **Gutters** — gutter install/repair, seamless gutters
- **Window & door installation** — replacement windows, door install
- **Garage doors** — garage door repair/install (SERVICE_DICT has it; no leaf)
- **Locksmith** — locksmith(s), lockout, rekey
- **Appliance repair** — currently routed to the retail `appliances-and-electronics`
  page as a stop-gap; deserves its own service page
- **Liquor stores** — liquor store, package store
- **Pawn shops** — pawn shop
- **Plant nursery / garden center** — nursery, garden center

> I deliberately did **not** point B2 terms at a loosely-related page (e.g.
> painters → general-contractors), since that would list businesses that don't do
> the job. They stay conversational until a real page exists — happy to wire them
> the instant the pages are created.

## Backfill — all 30 punch-list categories sourced (3 batches)

Verified Lake Havasu businesses were sourced from the live web (Yelp, operator
sites, Mohave Local, Yellow Pages) and staged for the **approval queue** — no
prod writes happen without your `--apply`/`--commit` + `--confirm`.

Batch 1: junk removal, property management, laundry/dry cleaning, auto glass,
painting, locksmiths. Batch 2: golf carts, window tint & wraps, pressure
washing, funeral homes, hearing aids, flooring, fencing, garage doors, concrete
& masonry. Batch 3: trailer sales/repair, mobile home services, shade screens &
patio covers, pet waste removal, firearms & shooting sports, medical specialists
& imaging, drywall, carpentry & cabinets, welding & fabrication, gutters,
windows & doors, appliance repair, liquor stores, pawn shops, nurseries & garden
centers.

**Deliverables (all dry-run by default):**

- `data/service_coverage_candidates_2026-06-20.csv` — **120 businesses across 30
  categories** with name, address, phone, website, target `leaf_slug`, and
  `source_url`. Review / trim this first; it is the source of truth for the seed
  script.
- `scripts/create_missing_service_leaves_2026_06_20.py` — creates all 30 leaf
  `categories` rows under the right departments. 15 are already-designed-but-
  unseeded (junk-removal-and-hauling, property-management, laundry-and-dry-
  cleaning, auto-glass, golf-carts, window-tint-and-wraps, pressure-washing-and-
  exterior-cleaning, funeral-cremation-and-cemeteries, hearing-and-audiology,
  trailer-sales-and-repair, mobile-home-services, shade-screens-and-patio-covers,
  pet-waste-removal, firearms-and-shooting-sports, medical-specialists-and-
  imaging); 15 are brand-new (painting, locksmiths, flooring, fencing,
  garage-doors, concrete-and-masonry, drywall, carpentry-and-cabinets,
  welding-and-fabrication, gutters, windows-and-doors, appliance-repair,
  liquor-stores, pawn-shops, nurseries-and-garden-centers). No-ops on any that
  exist; writes a rollback snapshot.
- `scripts/seed_service_businesses_2026_06_20.py` — reads the CSV and stages each
  business as a `draft=True, pending_review=True` Provider, exactly like
  `seed_family_venues.py`. They land in `/admin` → provider approval.
- Routing for all 15 brand-new leaves (`painter(s)`, `locksmith`, `flooring`,
  `fence company`, `garage door repair`, `concrete contractor`, `drywall`,
  `custom cabinets`, `welder`, `gutter installation`, `replacement windows`,
  `appliance repair`, `liquor store`, `pawn shop`, `garden center`, …) added to
  `_QUERY_TO_LEAF`; their slugs added to `PENDING_LEAF_SLUGS` so they
  self-activate when the page is seeded. The 15 already-designed leaves already
  had routing terms (and `medical-specialists-and-imaging`, which had none, was
  given `imaging`/`radiology`/`mri`/`specialists`/… terms). `appliance repair`
  was re-pointed from the retail appliances page to the new service leaf.

**Run order (you, on Windows, after reviewing the CSV):**

```
# 1. dry-runs — show the plan
.venv\Scripts\python.exe scripts\create_missing_service_leaves_2026_06_20.py
.venv\Scripts\python.exe scripts\seed_service_businesses_2026_06_20.py

# 2. apply (prod) once you approve the output
.venv\Scripts\python.exe scripts\create_missing_service_leaves_2026_06_20.py --apply --confirm
.venv\Scripts\python.exe scripts\seed_service_businesses_2026_06_20.py --commit
```

3. In `/admin` → provider approval, approve the staged rows **and set each one's
   primary category to its `leaf_slug` from the CSV** (approval is what publishes
   the listing and dual-writes the `entity_categories` link the page renders
   from). The moment a leaf has ≥1 approved business, its page renders and the
   search term works.

> The seed script intentionally stops at "draft, pending review" rather than
> writing live `entity_categories` rows directly — that keeps your dedupe +
> enrichment + review step in the loop. If you'd rather I auto-assign the leaf
> category on approval (skip the manual category pick), I can extend the script
> to set `Provider.primary_category` / write the `EntityCategory` link directly
> against a created leaf — your call.

## Remaining gaps

The original punch-list is now fully sourced — all 30 missing/thin service
categories have verified businesses staged in the CSV and a leaf ready to create.

A few categories are intentionally **thin** (only 1–2 confirmed independent
local operators found): `liquor-stores` (2) and `golf-carts` (2). They still
render (the gate is ≥1), but you may want to add the grocery-store liquor
departments or other operators at approval time. Everything else has 3–7
candidates.

If new service types surface later (e.g. a trade nobody searched for yet), the
same three-step pattern applies: add the businesses to the CSV, add the leaf to
`create_missing_service_leaves_2026_06_20.py`, and (for a brand-new leaf) add
routing terms + a `PENDING_LEAF_SLUGS` entry in `leaf_query.py`.
