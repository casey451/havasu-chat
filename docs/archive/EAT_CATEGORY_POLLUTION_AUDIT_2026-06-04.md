# Eat & Drink bucket pollution — audit findings (2026-06-04)

## Confirmed pollution (live evidence)

**Lovedwell Creative** appears in "Restaurants" chat listings and the eat-drink
category surface. It is a **wedding/event planner + florist** (founder Christina
Loya) — confirmed via [lovedwellcreative.com](https://www.lovedwellcreative.com)
and [their Instagram](https://www.instagram.com/lovedwellcreative/). Its
Provider row carries `category="Service"` but an eat-bucket `subcategory`
(likely mis-derived from Google types — their "drink & dessert carts" service
probably reads as food to the deriver).

Sampled live listings (chat API, `category` field per item) found no other
unambiguous offender in the top-rated rows, but only the prod DB can be
enumerated fully.

## Tools (in PR "zero-token about card + audit scripts")

- `scripts/audit_eat_bucket_pollution.py` — read-only; lists all eat-bucket
  members whose category/Google labels match a conservative non-food deny-list
  (event planner, florist, salon, contractor, …) with a food allow-list
  override (caterer, bakery, …). Verified against seeded fixtures.
- `scripts/fix_eat_bucket_pollution.py` — same detection; sets
  `subcategory = NULL` on flagged rows (drops them from every eat surface;
  nothing deleted; `backfill_subcategory.py` can re-derive later).
  **Dry-run by default.**

## Casey's runbook (prod flow per CLAUDE.md)

```
.venv\Scripts\python.exe scripts\audit_eat_bucket_pollution.py
.venv\Scripts\python.exe scripts\fix_eat_bucket_pollution.py            # dry-run, review counts
.venv\Scripts\python.exe scripts\fix_eat_bucket_pollution.py --apply    # after you approve the counts
```

Root-cause follow-up (optional): inspect `derive_subcategory` in
`app/categories/subcategories.py` for whatever Google type pulled an event
planner into an eat subcat, so re-running the backfill doesn't re-pollute.
