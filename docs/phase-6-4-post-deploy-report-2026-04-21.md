# Phase 6.4 post-deploy report — 2026-04-21

## Commit and push

- **Commit:** `4c5c7cb` — `Phase 6.4: session memory (hints, prior-entity, date injection)`
- **Remote:** `main` pushed to `https://github.com/casey451/havasu-chat.git` (`f6d423f..4c5c7cb`)

## After 3 minutes — Railway

- **`railway status`:** project **Havasu chat**, environment **production**, service **Havasu chat**.
- **`railway deployment list`:** latest deployment **`86710b0b-5052-4b7b-9520-c30e65b0e2f8`** — **SUCCESS** (timestamp shown: **2026-04-21 14:05:40 -07:00**). CLI does not print commit SHA; treat the Railway UI as authoritative if you need the exact build tied to `4c5c7cb`.
- **`railway logs --deployment 86710b0b-...`:** runtime startup only (Postgres, Alembic, Uvicorn). **No `tzdata` errors** in that stream. **Note:** that command returned **runtime** logs, not a full **`pip install`** transcript, so a clean log here does not prove the install step line-by-line; on Linux, **`tzdata`** is normally a harmless wheel alongside `zoneinfo` usage.

## Production voice spot-check (default base)

Report: `scripts/output/voice_spotcheck_2026-04-21T21-09.md`

### Q6 verbatim

> This weekend (April 25–26) I don't have events or programs listed in the catalog. For what's happening, check https://www.golakehavasu.com/events or call the Lake Havasu CVB at (928) 453-3444.

### Q9 verbatim

> The catalog has no events listed for tomorrow, April 22nd. Try https://www.golakehavasu.com/events for what's posted this week.

**t3-01 on production:** Weekend and “tomorrow” are **anchored to real dates** with **no** “I don’t have the date / locked in” calendar hedge — **matches the intended closure**.

## Manual production smoke (fresh `session_id`)

### Turn 1

**Query:** “I'm visiting with my 6-year-old, we're near the channel, what should we do tomorrow.”

- **tier_used:** 3
- **Response (substance):** Recommends **Altitude** for tomorrow (**Wednesday**), **11am–7pm**, **$19** 90-minute jump — reads as **child + channel + “tomorrow”** bias and date use. **PASS** for that part.

### Turn 2

**Query:** “What time does it open?” (same session)

- **tier_used:** 3
- **Response:** Asks which place; says no business was named and offers hours if you name it. **Prior-entity / pronoun follow-up did not bind to Altitude** in this run. **FAIL** relative to the specified smoke (pronoun should resolve to the prior recommendation).

### Extra check

Same pattern with explicit name on turn 2: **“What time does Altitude open tomorrow?”** after a similar turn 1 → **tier_used: 1** and a **full weekly hours** block. So **hours retrieval works when the venue is named**; the gap is specifically **`it` → last-mentioned place** on production for this pair.

## Summary

Deploy is **SUCCESS** in CLI; production voice **Q6/Q9** confirm **t3-01** post-deploy; **tzdata** not flagged in the logs pulled; **manual smoke is mixed** — **hints + tomorrow** look good, **pronoun “it”** did **not** resolve to the prior recommendation in the tested session.
