# Phase 5.1 Field Entry — `heat_exposure` Staged SQL (Eat & Drink)

> **What this is:** the `heat_exposure` field-entry work pre-resolved against the
> actual loaded DB. Cowork queried `data/events.db` (287 eat-drink entities, all
> `heat_exposure = NULL`), matched every Eat & Drink venue on the LOCKED
> `heat_exposure_priority_30_list.md` decision tree to its real entity row, and
> wrote id-keyed `UPDATE` statements. The operator's job shrinks to: confirm 2
> PROVISIONAL rows + 1 judgment call, then run the block.
>
> **DB read method:** the bash sandbox can't open the rebuilt `events.db` directly
> on the mount (gotcha #4/#15) — Cowork read a `/tmp` copy. **These statements run
> Windows-side against the live `data/events.db`.** All ids verified against the
> live DB via that copy on 2026-05-15.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat
> (post-`d34d4c3`, 2026-05-15). Brand-new `outputs/` file — safe under the
> parallel-chat scope lock.

---

## §1 LOCKED tags — ready to run, no confirmation needed

Every row below is a ✅ LOCKED entry on `heat_exposure_priority_30_list.md`, matched
to its loaded entity by name **and** address. High confidence on all 7.

| Entity (DB name) | id | Address | List ref | Tag |
|---|---|---|---|---|
| Locos Bar and Cocina - Northside | `dc5168c6-f5ec-4e0f-ab5a-a4cbf8ed7506` | 3620 London Bridge Rd | §2 #13 | `shaded` |
| Shugrue's Restaurant and Brewery Group | `c1c8829c-b200-49ac-8cab-f69bf7ff23bd` | 1425 McCulloch Blvd N | §3 #20 | `water_adjacent` |
| Makai Cafe | `d7e8fb73-9c1f-4491-9881-821026e16220` | 1425 McCulloch Blvd N | §3 #20 | `water_adjacent` |
| Barley Brothers Brewery | `400e7926-68cf-4eb8-a94e-639b02e4c817` | 1425 McCulloch Blvd N | §3 #20 | `water_adjacent` |
| Javelina Cantina | `ba787210-66ac-45f2-b7eb-54b3a8cbff1f` | 1420 McCulloch Blvd N | §3 #20 | `water_adjacent` |
| HEAT Bar | `f491e591-256f-4dc7-8280-42ea83d584f8` | 1420 McCulloch Blvd N | §3 #20 | `water_adjacent` |
| Lake Havasu Farmers Market | `2b4b33dc-5e97-4b00-8479-0e87b35253e3` | 2144 McCulloch Blvd N | §1 #9 | `outdoor` |

Note on the Farmers Market: list §1 #9 left "does it get its own Provider entity"
to the scrape — **it did** (loaded as a normal provider), so the `outdoor` tag applies.

## §2 PROVISIONAL — confirm before tagging (the 2 heat-list breadcrumbs)

These are the `PROVISIONAL` rows from `heat_exposure_priority_30_list.md` §2 #14/#15.
ChatGPT only *inferred* their patio shade. Both loaded cleanly and matched by address:

| Entity (DB name) | id | Address | What to confirm |
|---|---|---|---|
| El Paraiso Mexican | `82d0eaea-06b7-451f-b3de-b67870ce4e09` | 1530 Palo Verde Blvd S | Is the ~60-cap patio genuinely mid-day-shaded? If yes → `shaded`; if not → leave `indoor`. |
| College Street Brewhouse & Pub | `f36fb5b3-f2e6-4236-8668-3c7e99994084` | 1940 College Dr | Confirm the tag — list flags a `shaded`-vs-`water_adjacent` question because of the lake view. |

The `UPDATE`s for these are in §6, **commented out** — uncomment the one(s) that hold up.

## §3 Operator judgment call — second Shugrue's entity

The English Village split surfaced **two** Shugrue's entities at 1425 McCulloch Blvd N:

- `Shugrue's Restaurant and Brewery Group` — in §1 above, tagged `water_adjacent` (this
  is the cluster row from list §3 #20).
- `Shugrue's Cornerside Bakery` — `3723c4ba-3115-401b-a31c-78c7724d5c27` — **same English
  Village waterfront address.** The list named "Shugrue's" as one row; the scrape gave 2.

Call to make: is the Cornerside Bakery part of the English Village waterfront cluster
(→ `water_adjacent`) or not (→ `indoor` default)? Cowork's lean: `water_adjacent` — it's
physically in the same waterfront location and the list explicitly anticipated "operator
splits into N rows." But it's your call. The `UPDATE` is in §6, commented out.

## §4 Awareness flag — not a priority-list venue

`Locos Bar and Cocina - Swanson` (`0e865f8a-b0a4-4c87-a6f4-aa1a332d2a55`, 150 Swanson Ave)
also loaded. The heat list §2 #13 row is the **Northside** location only — Swanson is
**not** on the list and correctly defaults to `indoor`. No action; flagging so the two
Locos rows don't get conflated during entry.

## §5 The `indoor` default sweep

`heat_exposure_priority_30_list.md` §4 rule 1: everything not on the list defaults to
`indoor`. The §6 block ends with a `WHERE heat_exposure IS NULL` sweep — run it **after**
the §1 LOCKED tags so the sweep catches only the genuine defaults. This satisfies the
Phase 5.1 acceptance gate item "`heat_exposure` set on every entry (no NULL)".

The sweep is idempotent and re-runnable — if Layer-5 manual recovery (§3 of the runbook)
adds more eat-drink entities later, re-run just the sweep to default the new rows.

## §6 The runnable SQL block

Run Windows-side against the live DB — e.g. `sqlite3 data/events.db < this_block.sql`,
or paste into a `sqlite3 data/events.db` session. Schema confirmed: `heat_exposure
VARCHAR(20)` with `CHECK (... IN ('indoor','shaded','outdoor','water_adjacent'))`;
`updated_at` is set explicitly because raw SQL doesn't fire the ORM `onupdate`.

```sql
-- Phase 5.1 Eat & Drink heat_exposure field entry
-- §1 LOCKED tags
UPDATE entities SET heat_exposure='shaded',         updated_at=CURRENT_TIMESTAMP WHERE id='dc5168c6-f5ec-4e0f-ab5a-a4cbf8ed7506'; -- Locos Bar and Cocina - Northside
UPDATE entities SET heat_exposure='water_adjacent', updated_at=CURRENT_TIMESTAMP WHERE id='c1c8829c-b200-49ac-8cab-f69bf7ff23bd'; -- Shugrue's Restaurant and Brewery Group
UPDATE entities SET heat_exposure='water_adjacent', updated_at=CURRENT_TIMESTAMP WHERE id='d7e8fb73-9c1f-4491-9881-821026e16220'; -- Makai Cafe
UPDATE entities SET heat_exposure='water_adjacent', updated_at=CURRENT_TIMESTAMP WHERE id='400e7926-68cf-4eb8-a94e-639b02e4c817'; -- Barley Brothers Brewery
UPDATE entities SET heat_exposure='water_adjacent', updated_at=CURRENT_TIMESTAMP WHERE id='ba787210-66ac-45f2-b7eb-54b3a8cbff1f'; -- Javelina Cantina
UPDATE entities SET heat_exposure='water_adjacent', updated_at=CURRENT_TIMESTAMP WHERE id='f491e591-256f-4dc7-8280-42ea83d584f8'; -- HEAT Bar
UPDATE entities SET heat_exposure='outdoor',        updated_at=CURRENT_TIMESTAMP WHERE id='2b4b33dc-5e97-4b00-8479-0e87b35253e3'; -- Lake Havasu Farmers Market

-- §2 PROVISIONAL — uncomment after a 30-second patio-shade confirm
-- UPDATE entities SET heat_exposure='shaded', updated_at=CURRENT_TIMESTAMP WHERE id='82d0eaea-06b7-451f-b3de-b67870ce4e09'; -- El Paraiso Mexican
-- UPDATE entities SET heat_exposure='shaded', updated_at=CURRENT_TIMESTAMP WHERE id='f36fb5b3-f2e6-4236-8668-3c7e99994084'; -- College Street Brewhouse & Pub (or 'water_adjacent' — see §2)

-- §3 Judgment call — uncomment if Cornerside Bakery counts as English Village waterfront
-- UPDATE entities SET heat_exposure='water_adjacent', updated_at=CURRENT_TIMESTAMP WHERE id='3723c4ba-3115-401b-a31c-78c7724d5c27'; -- Shugrue's Cornerside Bakery

-- §5 indoor default sweep — run AFTER §1 above
UPDATE entities SET heat_exposure='indoor', updated_at=CURRENT_TIMESTAMP WHERE heat_exposure IS NULL;
```

## §7 Verification

After running, confirm the distribution:

```sql
SELECT heat_exposure, COUNT(*) FROM entities GROUP BY heat_exposure ORDER BY 2 DESC;
```

Expected if you run §1 + §5 only (provisionals/judgment call left commented):
`indoor` 280, `water_adjacent` 5, `shaded` 1, `outdoor` 1 — total 287, **0 NULL**.
Each PROVISIONAL/judgment row you later uncomment shifts one row out of `indoor`.

Spot-check a tagged row:

```sql
SELECT name, heat_exposure FROM entities WHERE id='c1c8829c-b200-49ac-8cab-f69bf7ff23bd';
```

---

## §8 What this clears

Running §1 + §5 closes the Phase 5.1 acceptance-gate item **"`heat_exposure` set on
every entry (no NULL)"** for the current 287-row load. The 2 PROVISIONAL confirms and
the Cornerside judgment call are the only `heat_exposure` decisions left open, and none
of them block the gate (they're `indoor` → off-default bumps). `crowd_notes`,
`boat_access`, and `seasonal_hours` are separate field-entry tracks (runbook §4) — not
staged here.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`d34d4c3`,
2026-05-15). Lives at `outputs/phase5_1_heat_exposure_field_entry_staged.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. Entity ids verified against a
`/tmp` copy of the live `data/events.db`; the SQL runs Windows-side against the live DB.*
