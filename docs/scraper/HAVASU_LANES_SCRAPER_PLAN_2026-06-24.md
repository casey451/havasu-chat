# Plan — twice-weekly scraper for Havasu Lanes (and the youth studios)

Owner handoff, 2026-06-24. Goal: keep the family-venue hours + recurring
specials that we now show in **Kids & Family** fresh automatically, instead of
hand-editing `app/home/family_venues.py`. Scope starts at Havasu Lanes (the ask)
and is built so the two class studios fold in with no new machinery.

## 1. What we show today (the thing the scraper must keep true)

As of this change the curated data lives in code:

- `OPEN_VENUES` in `app/home/family_venues.py` — drop-in venues with weekly
  hours. **Havasu Lanes** is now here: Mon–Thu 12–9, Fri–Sat 12–11, Sun 12–7,
  plus a subtitle calling out **Rock & Bowl** (black-light/"neon" bowling) every
  **Fri & Sat 6 PM–close**.
- `STUDIOS` / `class_today_rows()` — per-class schedules for **Black Belt
  Academy** (Youth Martial Arts) and **Universal Sonics** (Youth Gymnastics).

The scraper's job is to refresh those facts on a cadence and flag drift — never
to invent times. The honesty contract from `family_venues.py` still governs:
**a value only ships if a source actually published it.**

## 2. Sources and exactly what to pull

| Venue | URL | Field | How it's published | Parse difficulty |
|---|---|---|---|---|
| Havasu Lanes | `havasulanesaz.com/` | Weekly hours | Plain "Hours of Operation" list in the page DOM | **Easy** — static text |
| Havasu Lanes | `havasulanesaz.com/SPECIALS` | Rock & Bowl nights + pricing | Static text ("ROCK & BOWL EVERY FRIDAY & SATURDAY NIGHT 6PM TO CLOSE") | **Easy** |
| Black Belt Academy | `lakehavasublackbeltacademy.com/schedule/` | Class grid | **A posted PNG image** (`/wp-content/uploads/.../Screen-Shot-*.png`) | **Hard** — needs OCR or a human read; the grid is not machine text |
| Universal Sonics | `…/index.php?componentName=ClassScheduleDeluxe&scid=73927&action=view&classid=5878` | Class grid | Server-rendered text table (day → "3:00pm-4:15pm-Firecrackers…") | **Medium** — text, but irregular formatting + `*`/`**`/`***` team tiers to filter |

Two realities to design around: Black Belt's schedule is an image (so it can't be
parsed without OCR), and Universal's grid is summer-off-season and tier-coded.
Both argue for a **scrape → diff → human-approve** gate rather than auto-publish.

## 3. Target data model — two phases

**Phase 1 (recommended first, ~½ day): curated JSON behind a review gate.**
Move the hardcoded tuples in `family_venues.py` to a data file the module loads
at import, e.g. `app/home/data/family_venues.json` (+ `studio_classes.json`).
The scraper rewrites a *candidate* JSON; a human approves the diff; approved JSON
is committed. This keeps the exact rendering we just shipped, adds zero rendering
code, and the "only publish what's sourced" rule is enforced by the review step.

```
scraper run ──▶ candidate JSON ──▶ diff vs live ──▶ PR / admin approve ──▶ live JSON
```

**Phase 2 (later, ~2–3 days): promote into the DB provider pipeline.**
Emit an `EntityPayload` per venue + structured `hours` / `programs` / `schedules`
rows and route through `decide_ingest` (see `NEW_SCRAPER_CHECKLIST.md`). The
class rows then flow through the existing `class_occurrences_in_window()` path
and `class_today_rows()` can retire. This is the "right" long-term home (one
source of truth, dedup + freshness audits already run), but it is strictly more
work and isn't needed to satisfy the ask. Do it when a 3rd/4th studio appears.

Recommendation: ship Phase 1 now; revisit Phase 2 only if the curated list grows.

## 4. Implementation sketch (Phase 1)

New module `app/contrib/havasu_lanes.py` (mirror the small, single-source
scrapers like `app/contrib/gas_prices.py`):

1. **Fetch** `havasulanesaz.com/` and `/SPECIALS` (static HTML — `requests` +
   `beautifulsoup4`, both already in `requirements.txt`).
2. **Parse hours** from the "Hours of Operation" block → `{weekday: [(open,
   close)]}`. Parse the SPECIALS page for the Rock & Bowl day(s)/time/price.
3. **Normalize** into the same shape `FamilyVenue`/`StudioClass` expect and write
   a candidate JSON. Re-use `app/contrib/hours_helper.py` conventions for
   weekday keys and the Arizona (no-DST) timezone.
4. **Diff** candidate vs live; if changed, open the review artifact. **Never**
   overwrite live hours on a parse miss — a venue that fails to parse keeps its
   last-good values and raises a freshness warning (same spirit as
   `data-freshness-check.yml`).

For the **studios**: Universal's `ClassScheduleDeluxe` page is text-parseable
(drop rows whose label carries `*`/`**`/`***` team markers, keep the rec/preschool
classes we list today). Black Belt's image schedule has **no text** to scrape —
plan to either (a) run it through an OCR pass and *always* route to human review,
or (b) leave it as a periodic manual-confirm task (a scheduled reminder to
re-read the posted grid). Don't fake precision the source doesn't expose as text.

## 5. Scheduling — twice a week

Add `.github/workflows/havasu-lanes-scrape.yml` modeled on `gas-prices.yml`.
Twice-weekly cron (Mon & Thu, 14:00 UTC = 07:00 Arizona):

```yaml
on:
  schedule:
    - cron: "0 14 * * 1,4"   # Mon & Thu, 7 AM Arizona
  workflow_dispatch: {}
```

(The repo already runs every-other-day scrapers with `cron: "0 14 1-31/2 * *"`;
`* * 1,4` is the twice-weekly equivalent.) The job runs the scraper, and on a
detected change opens a PR with the candidate JSON diff for one-click review —
so an automated run can *propose* but a human *approves*, keeping the honesty
guarantee.

## 6. Idempotency, dedup, tests

- Phase 1 is naturally idempotent (it rewrites a full JSON snapshot).
- Phase 2 must route every payload through `decide_ingest` and add a dedup
  regression test (per `NEW_SCRAPER_CHECKLIST.md` step 4). Havasu Lanes already
  exists as a provider in the catalog, so the reconciler should **update**, not
  insert — assert that in the test.
- Add parser unit tests with a saved HTML fixture of each page (so a site
  redesign fails CI loudly instead of silently shipping stale hours).

## 7. Effort & sequencing

1. **(done)** Curate the current real values into `family_venues.py`.
2. Phase 1 scraper + JSON load + Mon/Thu workflow + PR-on-change — ~½ day.
3. Universal text parser with team-tier filtering — ~½ day.
4. Black Belt: decide OCR-with-review vs. manual-confirm reminder — ~½ day.
5. Phase 2 DB promotion — defer until the curated list outgrows a single file.
