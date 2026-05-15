# Phase 5.1 — Eat & Drink Data-Quality Cleanup (Staged SQL)

> **What this is:** runnable SQL to deactivate the 31 clear non-eateries + 1
> redundant duplicate row identified in
> `outputs/phase5_1_eat_drink_data_quality_audit.md`. Approach: **deactivate**
> (`is_active = 0`) — fast, fully reversible, hides the rows from Phase 6's
> `/category/eat-drink` page without destroying anything. The audit doc has the
> full reasoning per row; this doc is just the artifact.
>
> **Scope:** the 32 rows below ONLY. The 15 §3 "borderline" judgment-calls
> (convenience stores, butcher shops, distillery, etc.) are deliberately **left
> untouched** — that's a separate operator call.
>
> **DB read method:** `/tmp` copy (mount can't open `events.db` directly — gotcha
> #4/#15). All 32 entity_ids verified against the live DB on 2026-05-15; the SQL
> runs Windows-side against the live `data/events.db`.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat
> (post-`aa2622d`, 2026-05-15). Brand-new `outputs/` file — safe under the
> parallel-chat scope lock.

---

## §1 What this does

Sets `is_active = 0` on **both** the `entities` row and its `providers` row for 32
entities: the 31 clear non-eateries from audit §2, plus `71ad6c09…` — the
data-poorer of the two duplicate "Lady Lee's" rows (keeping `b4d80817…`, which has
reviews + a rating). After running: **255 active** eat-drink providers/entities
remain (287 − 32), comfortably above the gate's "15+ per default filter" bar.

Reversible — flip any row back with `is_active = 1`. One caveat: if
`scripts/places_load.py` is ever re-run for eat-drink, its upsert sets
`is_active = True` and would reactivate these. Eat-drink's load is done, so that's
not expected — but worth knowing.

## §2 The runnable SQL

Run Windows-side from the repo root — `sqlite3 data/events.db < block.sql` or paste
into a `sqlite3 data/events.db` session.

```sql
-- Phase 5.1 Eat & Drink data-quality cleanup — deactivate 31 non-eateries + 1 duplicate row
-- Reversible. Leaves the 15 borderline judgment-calls (audit §3) untouched.

UPDATE entities SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id IN (
  '968b4a6e-124d-4b6f-b125-cb3b58fa3145',  -- A Toe Truck (towing company)
  '4d420b76-3451-4d89-a504-edd8d1cb45ba',  -- Hava Event Planner & Coordinator
  'afa108ea-ddf1-48a1-a9d0-9b6d300e8bb5',  -- Lovedwell Creative (creative agency)
  '0da5a4ac-111b-4734-9a07-e47666840bca',  -- Posh Planning & Event Co.
  'bae5cda8-8db2-4f4a-b541-736806b0b402',  -- River Rat Motorsports
  '61197d69-fb83-4b88-bfd8-731d261388cb',  -- Lake Havasu Cigars
  'eb5d36e9-4575-4336-b30a-3722675a1a37',  -- Farm Fresh Marijuana Dispensary
  'c020ba06-3f36-4eac-93f4-86831292e4ee',  -- Close to Downtown Nightlife... (vacation rental, dup)
  'cdae678d-4ef1-4eea-8794-d15642f51390',  -- Close to Downtown Nightlife... (vacation rental, dup)
  '240c4f19-23c6-4f19-b8e4-5be5b8eaf7b5',  -- London Bridge Resort (hotel)
  '2b38d5af-5bce-46aa-bd4a-2bc12574e334',  -- The Nautical Beachfront Resort
  '3c499705-09b0-40d6-915c-8d25b20f88c4',  -- Iron Wolf Golf & Country Club
  '1b58b28e-7ea8-4d09-8c3b-a409c77d7a7c',  -- Site Six Launch Ramp (boat ramp)
  'b0acdc8a-3c14-41bc-9e89-ab67ab95531f',  -- Hava Style Recreation (gear supplier)
  'a68f7dd8-c196-4a45-92cc-372263087cb5',  -- Lake Havasu Rodeo Grounds
  '1b82d3fe-85e0-4b14-b6e9-4b4b2c50766e',  -- McCulloch Center Plaza (shopping plaza)
  'c0c513fb-20ab-4245-a080-24dfaa1d49d1',  -- Havasu 95 Speedway
  '1920fe0f-aff9-4178-825b-ffd02a2cb7f5',  -- Grace Arts Live (theater)
  'f0497e6e-d433-4df9-9a0f-278dd1fe0f1d',  -- London Bridge Beach (park)
  'b3b1c0f7-e999-48fa-ba5f-05d8c2793f9e',  -- Movies Havasu (movie theater)
  'bf3fe419-de3a-43b4-a4a4-e5452a391251',  -- London Bridge Swap Meet
  '5020a3b8-b3dd-40e5-b4cb-d6d82c23e1a3',  -- DELI LAUNDROMAT (laundromat)
  '6737ecc9-4a4f-4e93-a7fa-b27e2fe7a005',  -- Sunshine Indoor Play (kids playground)
  'b7731508-0993-4538-b58e-770ba3dac2fc',  -- The Back Nine Golf (indoor golf)
  'dc9b2e08-7e6e-4733-947c-f0f9669488d7',  -- Lake Havasu Golf Club
  '791cf1e6-df8b-401e-9840-e4250f426d07',  -- W.A.V.E. Culinary and Hospitality (school)
  'e3272eaa-28e7-4583-bf24-3e023a5a6f0d',  -- Western States Restaurant Consulting (firm)
  'afa6dc88-9a55-465e-af4d-776fc22e9144',  -- Detail Specialties & Ceramic Coating (auto detail)
  'b8dfe489-6b11-42d4-8966-69200427e9d3',  -- Martin Swanty's Paradise Auto (car dealer)
  'b996edfe-0c54-4941-91d3-26fb84e4895b',  -- Our Shabby Shack & Book Exchange (bookstore)
  '368c5360-c3bd-465d-9337-83e9cc201d24',  -- The Speakeasy Beauty Lounge (beauty salon)
  '71ad6c09-f6c7-4d4f-a137-d653d697cbc1'   -- Lady Lee's (duplicate row; keeping b4d80817...)
);

UPDATE providers SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE entity_id IN (
  '968b4a6e-124d-4b6f-b125-cb3b58fa3145',
  '4d420b76-3451-4d89-a504-edd8d1cb45ba',
  'afa108ea-ddf1-48a1-a9d0-9b6d300e8bb5',
  '0da5a4ac-111b-4734-9a07-e47666840bca',
  'bae5cda8-8db2-4f4a-b541-736806b0b402',
  '61197d69-fb83-4b88-bfd8-731d261388cb',
  'eb5d36e9-4575-4336-b30a-3722675a1a37',
  'c020ba06-3f36-4eac-93f4-86831292e4ee',
  'cdae678d-4ef1-4eea-8794-d15642f51390',
  '240c4f19-23c6-4f19-b8e4-5be5b8eaf7b5',
  '2b38d5af-5bce-46aa-bd4a-2bc12574e334',
  '3c499705-09b0-40d6-915c-8d25b20f88c4',
  '1b58b28e-7ea8-4d09-8c3b-a409c77d7a7c',
  'b0acdc8a-3c14-41bc-9e89-ab67ab95531f',
  'a68f7dd8-c196-4a45-92cc-372263087cb5',
  '1b82d3fe-85e0-4b14-b6e9-4b4b2c50766e',
  'c0c513fb-20ab-4245-a080-24dfaa1d49d1',
  '1920fe0f-aff9-4178-825b-ffd02a2cb7f5',
  'f0497e6e-d433-4df9-9a0f-278dd1fe0f1d',
  'b3b1c0f7-e999-48fa-ba5f-05d8c2793f9e',
  'bf3fe419-de3a-43b4-a4a4-e5452a391251',
  '5020a3b8-b3dd-40e5-b4cb-d6d82c23e1a3',
  '6737ecc9-4a4f-4e93-a7fa-b27e2fe7a005',
  'b7731508-0993-4538-b58e-770ba3dac2fc',
  'dc9b2e08-7e6e-4733-947c-f0f9669488d7',
  '791cf1e6-df8b-401e-9840-e4250f426d07',
  'e3272eaa-28e7-4583-bf24-3e023a5a6f0d',
  'afa6dc88-9a55-465e-af4d-776fc22e9144',
  'b8dfe489-6b11-42d4-8966-69200427e9d3',
  'b996edfe-0c54-4941-91d3-26fb84e4895b',
  '368c5360-c3bd-465d-9337-83e9cc201d24',
  '71ad6c09-f6c7-4d4f-a137-d653d697cbc1'
);
```

## §3 Verification

```sql
SELECT is_active, COUNT(*) FROM providers GROUP BY is_active;
-- expect:  0 -> 32   |   1 -> 255

SELECT is_active, COUNT(*) FROM entities GROUP BY is_active;
-- expect:  0 -> 32   |   1 -> 255
```

Spot-check one deactivated + the kept Lady Lee's:

```sql
SELECT name, is_active FROM entities WHERE id = 'f0497e6e-d433-4df9-9a0f-278dd1fe0f1d';  -- London Bridge Beach -> 0
SELECT name, is_active FROM entities WHERE id = 'b4d80817-c326-4157-a3b8-e61a018f5eda';  -- Lady Lee's (kept)   -> 1
```

## §4 Notes

- **Order doesn't matter** between the two UPDATEs — they touch different tables.
- **Recategorization later:** deactivating doesn't lose anything. If you later want
  these in their correct Tier-1 categories (lodging, on-the-water, etc.), the rows
  are still there to recategorize + reactivate. Coordinate that with the Phase 6
  agent since it changes what renders where.
- **The 15 borderline rows (audit §3)** stay active. If you decide some of those
  also don't belong, they're a quick add to this same pattern — say which.
- This is the last open data-quality item before Phase 6 renders the eat-drink
  page cleanly.

---

## §5 References

- `outputs/phase5_1_eat_drink_data_quality_audit.md` — the full audit + per-row reasoning (§2 the 31, §3 the borderline 15, §4 the duplicates)

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`aa2622d`,
2026-05-15). Lives at `outputs/phase5_1_eat_drink_cleanup_staged.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. All 32 entity_ids verified
against a `/tmp` copy of the live `data/events.db`; the SQL runs Windows-side.*
