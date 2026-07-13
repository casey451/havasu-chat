# Upcoming-events source audit — 2026-07-13

**Report only. No database writes were made.** This is a discrepancy report to review before any expire/dedup/fix data-op (which stays gated per CLAUDE.md: dry-run → counts → Casey approves → apply).

## Method

- **Source of truth for “what’s stored”:** the live production feed `https://askhava.com/events.ics` (every `status=live` event, no date filter). DB-free by design — the repo `.env` points at the internal Railway host, so there is no local prod-DB; the ICS is the authoritative DB-free mirror.
- **Verification engine:** the repo’s own live source-verifier `scripts/prelaunch_verify.py :: verify_source` (re-fetches each event’s URL cold with a Googlebot UA, parses JSON-LD `Event`, and field-compares date/time/venue; double-confirms any dead-link/date verdict to suppress flaky origins) plus the full `app.events.lint` battery.
  - Note on the named tools: `verify_event_sources_2026_06.py` only does *structural* URL classification and needs the prod DB (unreachable locally); it does **not** re-fetch sources or compare date/time/venue. `verify_source` above is the live-fetch verifier that actually does the source diff, so it is the engine used here. `schedule_drift_check` covers the 15 recurring class schedules (separate dataset) — summarized at the end.
- **Added passes** the engine doesn’t cover: past-dated-still-live, and duplicate detection (title+date clustering).
- **Window:** ALL upcoming (`date ≥ 2026-07-13`), through 2027-10-15. Recurring RRULE events are handled separately (their DTSTART is a 2024 anchor, so per-occurrence date/time can’t be diffed from the feed).

## Scope

- Live VEVENTs in feed: **388**  —  recurring **15**, non-recurring **373**
- **Upcoming (audited): 321**  |  past-dated still live: **52**
- Running build: `3e4b053d1223`

## Findings by severity

| Severity | Count |
|---|---|
| high | 72 |
| medium | 49 |
| low | 131 |
| info | 10 |
| **total** | **262** |

## Findings by type

| Flag | Sev | Count |
|---|---|---|
| Past-dated but still `status=live` (expire backlog) | high | 52 |
| Wrong or suspicious time | high | 19 |
| Wrong date (source disagrees) | high | 2 |
| Duplicate events (same title + date + venue) | high | 2 |
| Dead / broken source link | high | 1 |
| Source unreachable to our bot (recheck) | medium | 38 |
| Wrong venue (source names a different place) | medium | 5 |
| Season/holiday word vs. date | medium | 2 |
| Weak provenance (homepage only, not per-event) | low | 62 |
| Venue stored as a bare street address | low | 35 |
| Source reachable but no machine-readable schema | low | 31 |
| ALL-CAPS / title quality | low | 3 |
| Same title + date at different venues (likely distinct) | info | 10 |

> Full per-event detail (all columns incl. source URL) is in `event_source_audit_2026-07-13.csv`.

---

## 1. Past-dated but still `status=live` (expire backlog) — 52 (high)

Every row below is a non-recurring event whose end is **before today** yet is still `status=live`. These no longer show on the `/calendar` past-day grid (that was fixed) but the rows remain live (searchable, permalinked). Almost all are from the last week (07-06 → 07-12) — consistent with the expire-past-events cron having a gap. Candidate for a gated expire sweep.

| event_id | start_date | title | source |
|---|---|---|---|
| c036c005-49a1-40b4-a907-5cda9bbf08e5 | 2026-07-06 | Summer Free Movies “Dora and the Lost City of Gold” Star Cinemas | riverscenemagazine.com |
| 15b26a4a-54fc-4fcb-89da-1ecd2a775aca | 2026-07-06 | Toptracer Range — Family Night Golf | ironwolfgcc.com |
| 74457a55-161d-4798-97dd-32010bacadff | 2026-07-06 | Rainforest Rush Kids Camp 2026 | abundantgracelhc.churchcenter.com |
| 1ef38651-5f94-4f67-bbf5-dda85a6acc4d | 2026-07-07 | Popsicles in the Park | lhcaz.gov |
| 4664c644-2de5-44ac-9d2e-32680e4a5e5e | 2026-07-07 | Junior Jump Time (Ages 6 & Under) | altitudetrampolinepark.com |
| 06f60dfe-77ad-45f8-93f9-e4a466f27a44 | 2026-07-07 | Mexican Train Dominoes | lhcaz.gov |
| 4a046fda-13f5-45e7-a19e-2f18a979d3e8 | 2026-07-07 | Big Fish Little Fish at the Aquatic Center | golakehavasu.com |
| 8018eee0-2644-41b2-9d84-31c36b8bfb24 | 2026-07-07 | HAVASU STAR SEARCH - 2nd Season | golakehavasu.com |
| 0d7d83b0-39b0-4ad9-b58f-a91e5a8cdd79 | 2026-07-07 | BMX Local Race | usabmx.com |
| 3b2660c0-aa7c-4b0b-8020-0e7454c56da6 | 2026-07-08 | Board of Adjustment Meeting | lakehavasucity.legistar.com |
| 87a14987-79dd-4eab-9d02-17b7d1fd9d5c | 2026-07-08 | Christmas in July | lakehavasuseniorcenter.com |
| b6f6762e-e2af-404e-bb5c-aed351acdbe7 | 2026-07-08 | Christmas in July | lakehavasuseniorcenter.com |
| c3cc923a-c35b-4c46-ac5f-10ff3bd807e2 | 2026-07-08 | Popsicles in the Park | lhcaz.gov |
| 5b5bd33f-7ffa-4fa5-9285-0ecac13a8206 | 2026-07-08 | Toptracer Range — Family Night Golf | ironwolfgcc.com |
| 8c3e6cd1-63c6-48df-a9fe-e5d27009701f | 2026-07-08 | Glow in the Park — All Ages | altitudetrampolinepark.com |
| aa6908c7-2515-4d93-a9a8-60d42e68e79a | 2026-07-08 | Glow in the Dark Family Painting | register.lhcaz.gov |
| 6f358454-252c-495f-86c9-19e1b48bfbfb | 2026-07-08 | Kids Pizza Party Cooking Class | register.lhcaz.gov |
| 81b7abc3-beb4-4747-bac3-c12d49c13f29 | 2026-07-08 | Sip, Mingle & Shop | golakehavasu.com |
| 5278ee46-3bea-4f75-98f9-79ea3776e7e3 | 2026-07-09 | Pickleball Open Play | lakehavasupickleball.com |
| 1ace80f1-9315-4b5b-a65d-c583d57b9d27 | 2026-07-09 | Pickleball Open Play | lakehavasupickleball.com |
| d4d86321-a2d0-4e81-a52e-1328b5a54df4 | 2026-07-09 | Big Fish Little Fish at the Aquatic Center | golakehavasu.com |
| 58246e56-035d-4aae-9d44-54341ac8a48a | 2026-07-09 | Tiny Tots - Open Gym Play | lhcaz.gov |
| cf963b6d-8493-4a8d-9d13-4db0293b29dd | 2026-07-09 | Junior Jump Time (Ages 6 & Under) | altitudetrampolinepark.com |
| 2be9f4e4-6670-4130-bb0d-278784ac3e93 | 2026-07-09 | Pickleball Round Robin | register.lhcaz.gov |
| 5f3f0879-5138-45a6-9979-cf642ecf2025 | 2026-07-09 | Grief & Mental Health | allevents.in |
| 3de1e7ed-1ae3-4aa0-9e45-49105d07f96c | 2026-07-09 | Kids Art - Painting with Sponges | lhcaz.gov |
| 40a25df6-6451-4346-985b-8fe701a565fc | 2026-07-09 | Red, White and Blue Bunco Party | my.cheddarup.com |
| 52e13149-3fed-4276-8655-4ca4c043cbae | 2026-07-09 | 10 Year Anniversary Ribbon Cutting River Valley Home Health & Hospice | allevents.in |
| 2af19abc-f44e-480f-8d42-5023bab0ac27 | 2026-07-09 | Toptracer Range — Family Night Golf | ironwolfgcc.com |
| 309c1884-7ba7-4a37-a138-08792d3d43aa | 2026-07-09 | Bag Charm Making with Summer | golakehavasu.com |
| 66178f03-6d33-47d8-8388-78094082eba8 | 2026-07-09 | BMX Local Race | usabmx.com |
| cf52c2e4-1c76-4fdf-a679-ea70fe98935e | 2026-07-09 | Elective Theatre Acoustic Duo | allevents.in |
| 2984ee1b-86c0-45f9-a3b7-8786ba4c6062 | 2026-07-10 | Pickleball Open Play | lakehavasupickleball.com |
| 5896f0a8-042f-4c03-88cf-b6aeffd63078 | 2026-07-10 | Fishing Fridays | lhcaz.gov |
| d4b3c95d-6131-4a44-a31f-e7d876db2ce7 | 2026-07-10 | Pickleball Open Play | lakehavasupickleball.com |
| 3dcfe24c-c872-445e-afd6-523bea0039dc | 2026-07-10 | Toptracer Range — Family Night Golf | ironwolfgcc.com |
| 42403965-cf27-4067-a21a-0339cfaf9fe6 | 2026-07-10 | 80HD - Avalon Nights Live | allevents.in |
| 2e391f65-d9e0-4466-83ca-9dc49177eaf6 | 2026-07-10 | Friday Pool Party at Iron Wolf | ironwolfgcc.com |
| 33f9a9d5-8ac8-4905-9775-a7c15a10fffe | 2026-07-10 | Cosmic Bowling | havasulanesaz.com |
| ef8a25b3-eea4-4d8e-81c5-efc6ab4d12a4 | 2026-07-10 | Grace Arts Live Presents Alice In Wonderland Jr. | graceartslive.com |
| e30c969b-5ec2-4ec3-a5b6-ba8ee7ef0d8e | 2026-07-11 | Pickleball Open Play | lakehavasupickleball.com |
| 4773cdfb-c9b3-4db5-8ddd-053d29636d5d | 2026-07-11 | Pickleball Open Play | lakehavasupickleball.com |
| 462ad47f-5a61-4ca0-810a-f7d819b89779 | 2026-07-11 | Lake Havasu Farmers Market | lakehavasufarmersmarket.com |
| 1de7d0a0-64d7-4647-bf43-972ba809d96e | 2026-07-11 | Toptracer Range — Family Night Golf | ironwolfgcc.com |
| f40d29df-2d1a-4c41-a144-dc3eb2aca4aa | 2026-07-11 | Cosmic Bowling | havasulanesaz.com |
| 3eb38156-1eeb-44d5-9f36-5a4d622584a4 | 2026-07-11 | Glow in the Park — All Ages | altitudetrampolinepark.com |
| 08b2f736-e421-4db3-bb83-75127570709a | 2026-07-11 | Live music at Legendz | golakehavasu.com |
| da69eaba-cf00-42e9-81d4-0df1236cb85f | 2026-07-12 | Pickleball Open Play | lakehavasupickleball.com |
| 9bd98fa2-5638-4a47-a01b-3c3cf892e56c | 2026-07-12 | Line Dancing | lhcaz.gov |
| fee283f6-987b-4d5e-af0c-42a10e23fd5a | 2026-07-12 | Toptracer Range — Family Night Golf | ironwolfgcc.com |
| 8a7f358d-915a-4ed1-9a5f-5dcc69b0e328 | 2026-07-12 | Havasis Free Swim Day | allevents.in |
| 3ca92764-0db8-4994-8201-96eecb222bbe | 2026-07-12 | Briana Marie | allevents.in |

## 2. Duplicate events (same title + date + venue) — 2 rows / 1 cluster(s) (high)

Only clusters that share **title + date + venue** count as true duplicates:

- **“Crosscutt at the Flying X Saloon”** on **07-31** is a genuine **cross-source** duplicate: one row from `allevents.in`, one from `golakehavasu.com` — same venue (Flying X Saloon), title case differs. (These two also disagree on start time — 20:00 vs 20:30, see §5.)

| event_id | date | title | venue | source |
|---|---|---|---|---|
| 66ad5275-9c79-4713-a416-b468eb8758d3 | 2026-07-31 | Crosscutt at The Flying X Saloon | Flying X Saloon | allevents.in |
| 8a83283d-bea7-497e-b838-dc9fbbf65e6d | 2026-07-31 | Crosscutt at the Flying X Saloon | Flying X Saloon | golakehavasu.com |

### Same title + date at different venues (likely distinct) — 10 (info, not counted as dupes)

**“Pickleball Open Play”** appears twice per day (07-13 … 07-17) but at **two different venues** — *Mike Delaney Complex* (stored **all-day**, no real time) and *The Ark Center* (8:00–11:00 AM). These are almost certainly two legitimate daily sessions, **not** duplicates — flagged only for transparency. The one real issue in the pair is that the Mike Delaney rows carry a placeholder all-day time instead of real hours.

| event_id | date | title | venue |
|---|---|---|---|
| ae689f12-b4de-44a3-86bb-daf47c26fcea | 2026-07-13 | Pickleball Open Play | Mike Delaney Pickleball Complex at Dick Samp Park |
| dc66be93-d16c-431f-ad54-94fd7eaee622 | 2026-07-13 | Pickleball Open Play | The Ark Center |
| 229312b9-07ec-4a66-9ef2-4f3772a394a3 | 2026-07-14 | Pickleball Open Play | Mike Delaney Pickleball Complex at Dick Samp Park |
| fad0e7d6-d109-4347-9e47-41fb7b89cf0f | 2026-07-14 | Pickleball Open Play | The Ark Center |
| 04f71109-86f4-4e93-9393-8a78a031f026 | 2026-07-15 | Pickleball Open Play | Mike Delaney Pickleball Complex at Dick Samp Park |
| 9c7cac60-e2e4-46f4-b6ae-8bfd1141b6a7 | 2026-07-15 | Pickleball Open Play | The Ark Center |
| ce328fe5-ac31-42f9-85ee-2d6f4e4435e1 | 2026-07-16 | Pickleball Open Play | Mike Delaney Pickleball Complex at Dick Samp Park |
| 728bfae5-7e4e-42b5-b863-853d6e1f7b68 | 2026-07-16 | Pickleball Open Play | The Ark Center |
| 81711f70-34a5-4297-9452-079f51a24215 | 2026-07-17 | Pickleball Open Play | Mike Delaney Pickleball Complex at Dick Samp Park |
| 67de00c6-af70-4767-85e7-8802fa6e2ac0 | 2026-07-17 | Pickleball Open Play | The Ark Center |

## 3. Wrong date (source disagrees) — 2 (high, verify manually)

Source JSON-LD `startDate` shows a different calendar day than we store. Both confirmed on recheck. **Caveat:** `allevents.in` `startDate` carries a timezone offset, so an off-by-one *can* be a source-side TZ artifact — verify each against the human-readable date on the page before changing.

| event_id | our_date | title | stored | source_says | url |
|---|---|---|---|---|---|
| 9dd3a8af-7e11-455c-a692-cfe2d6c28994 | 2026-07-18 | Toddler Time \| Smiley Shark Story & Craft | 2026-07-18 | 2026-07-17 | https://allevents.in/lake-havasu-city/toddler-time-\|-smiley-shark-story-and-craft-\|-lake-havasu/200030370289859 |
| fad143e1-bb8d-4a6c-8950-3691efc833b7 | 2026-09-12 | Cirque de Masquerade Charity Gala | 2026-09-12 | 2026-09-11 | https://allevents.in/lake-havasu-city/cirque-de-masquerade-charity-gala/200030239776317 |

## 4. Dead / broken source link — 1 (high)

| event_id | date | title | url | result |
|---|---|---|---|---|
| 99a38686-d69e-4ed4-a12f-5a4c1fe7c66c | 2026-10-31 | London Bridge Days Parade | https://londonbridgedays.com/parade/ | HTTP 404 |

## 5. Wrong or suspicious time — 19 (mixed)

Two kinds: **`ampm_flip` lint** (start at midnight/early-AM — probable PM-entered-as-AM *or* a placeholder time) and **`TIME_MISMATCH`** (source JSON-LD gives a different start). **Caveat:** several early-AM hits are legitimately-early sport (golf shotgun 6:30 AM, trail runs 6:30 AM) — those are review, not confirmed flips. The `00:00` rows read as missing/placeholder time. The strongest single fix: **Shoreline to Skyline UTV Adventure** stored `00:00`, source says `18:00`.

| event_id | date | title | stored | source_says | note |
|---|---|---|---|---|---|
| afc5a12d-1cc5-45a6-af3f-48e216bf5c7c | 2026-08-28 | Omega Combat 1: Genesis | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| 58f0902d-7c8c-473d-ae99-0a82270dadff | 2026-09-11 | Sleepless in Havasu | lint:ampm_flip |  | starts 06:00:00 — probable PM entered as AM |
| e9743895-2335-428f-bb18-c9d1c8dc86f2 | 2026-09-11 | Michael Alan Sleepless in Havasu | lint:ampm_flip |  | starts 06:00:00 — probable PM entered as AM |
| 530ae81a-09ea-4ae3-ab62-5f0dc7110b3e | 2026-09-25 | Pro Watercross USA *Road to Havasu* | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| 86cbd5f7-c21f-4f8f-8440-f8739a6c535f | 2026-10-03 | SBT IJSBA World Finals | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| 3be32e75-a7aa-4540-894a-e1ac2cc1908f | 2026-10-03 | IJSBA Short Block Technologies World Finals | lint:ampm_flip |  | starts 06:00:00 — probable PM entered as AM |
| 9ef124cd-69d5-4756-aacb-dbf288d9b254 | 2026-10-09 | Havasu Halloween Festival with Kottonmouth Kings and Property Six | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| 5556de30-1532-48c4-9d98-d81a7014c1ee | 2026-10-10 | End of Summer Lake Cleanup | lint:ampm_flip |  | starts 07:00:00 — probable PM entered as AM |
| 0e5cf483-3fdb-426f-9bd0-c256c0098605 | 2026-10-17 | Lizard Peak Scramble Trail Runs | lint:ampm_flip |  | starts 06:30:00 — probable PM entered as AM |
| 2c736561-0684-4b43-ab60-d740c5da67af | 2026-10-24 | Lake Havasu Halloween Scream Baseball Tournament | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| 9b1ff44a-cc22-4422-b3f6-75d23f89a3e0 | 2026-11-07 | Havasu Heroes Memorial Golf Tournament | lint:ampm_flip |  | starts 06:30:00 — probable PM entered as AM |
| 741b4a89-06ca-429e-b6c3-f51984560988 | 2027-01-14 | Shoreline to Skyline UTV Adventure | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| 1a5a3c81-00ea-45ed-84c9-cd3270507b86 | 2027-01-14 | Buses by the Bridge | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| c78f0b9b-80a1-48b1-8ede-b4cb221401dd | 2027-02-06 | 2027 Winterfest Street Festival | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| 87d4c113-ad5b-4d94-a2be-124ace9fcc31 | 2027-10-15 | IWWF World Waterski Racing Titles | lint:ampm_flip |  | starts 00:00:00 — probable PM entered as AM |
| 66ad5275-9c79-4713-a416-b468eb8758d3 | 2026-07-31 | Crosscutt at The Flying X Saloon | 20:00 | 20:30 | TIME_MISMATCH: source shows a different start time |
| 29e9105e-b901-4606-ab5d-bcd3b3ced3c2 | 2026-08-01 | Crosscutt at the Flying X Saloon | 20:00 | 20:30 | TIME_MISMATCH: source shows a different start time |
| 0e5cf483-3fdb-426f-9bd0-c256c0098605 | 2026-10-17 | Lizard Peak Scramble Trail Runs | 06:30 | 06:45 | TIME_MISMATCH: source shows a different start time |
| 741b4a89-06ca-429e-b6c3-f51984560988 | 2027-01-14 | Shoreline to Skyline UTV Adventure | 00:00 | 18:00 | TIME_MISMATCH: source shows a different start time |

## 6. Wrong venue (source names a different place) — 5 (medium)

Source names a specific venue; we store the generic “Lake Havasu” (placeholder city) or a landmark placeholder.

| event_id | date | title | stored_venue | source_venue | url |
|---|---|---|---|---|---|
| c26f0760-45f9-49ac-8a9d-216607509360 | 2026-08-02 | Yoga Nidra & Sound Bath Supporting DF2FM | Lake Havasu | Llamaste Yoga and Healing | https://allevents.in/lake-havasu-city/yoga-nidra-and-sound-bath-supporting-df2fm/200030260153130 |
| aafdf8f4-f0c2-4868-8a99-218b95a282ea | 2026-08-08 | Water Ballon War | Lake Havasu | Rotary Park | https://allevents.in/lake-havasu-city/water-ballon-war/200030343830349 |
| 78849908-5a31-4e38-a6f6-8bcf68e5211b | 2026-08-14 | Girls Night In | Lake Havasu | Southside District | https://allevents.in/lake-havasu-city/girls-night-in/200030364096124 |
| 94a5afe5-e691-4086-8cc2-aff636addecd | 2026-10-10 | Parade of Homes | lint:landmark_venue_mismatch |  | https://www.havasuchamber.com/ |
| d113e223-fab7-416b-9485-cfaabbbf5048 | 2026-10-24 | LHHS Class of 2016's 10 Year Reunion | Lake Havasu | Mudshark Brewery and Public House | https://allevents.in/lake-havasu-city/lhhs-class-of-2016s-10-year-reunion/100001990660275471 |

## 7. Venue stored as a bare street address — 35 (low)

Venue stored as a bare street address instead of a named place — concentrated in `lakehavasufarmersmarket.com` (~24, `2144 McCulloch Blvd N…`) and `graceartslive.com` (~10, `2146 McCulloch Blvd`). One row also has a typo venue: `2144 McCulloch Blvd NLake Havas City, AZ` (missing space / “Havasu” → “Havas”). Cosmetic on render; fold the address → named-venue backfill into the next data-op.

## Season/holiday word vs. date — 2 (medium)

Title carries a season/holiday word that contradicts the month. **Home & Garden Expo Spring Show** (Jan) is a proper-noun show name — likely a false positive; **End of Summer Lake Cleanup** (Oct) is worth a look.

| event_id | date | title | note |
|---|---|---|---|
| 5556de30-1532-48c4-9d98-d81a7014c1ee | 2026-10-10 | End of Summer Lake Cleanup | title says Summer but the date is in month 10 |
| 29f1bd4c-dc8c-4910-afba-77aff8d97de1 | 2027-01-30 | Lake Havasu Home & Garden Expo Spring Show | title says Spring but the date is in month 01 |

## ALL-CAPS / title quality — 3 (low)

ALL-CAPS titles — normalize casing (cosmetic).

| event_id | date | title | note |
|---|---|---|---|
| 1f30b11d-255e-4ddf-b758-9ee986acb38c | 2026-07-24 | HAVASIS CHAT & CRAFT | title is ALL-CAPS — normalize casing |
| 1d657f64-c08d-4177-9d86-8711d5727bad | 2026-08-20 | HAVASIS END OF SUMMER LUNCH | title is ALL-CAPS — normalize casing |
| 20f041d7-7575-45df-96a4-c4d8dac4b382 | 2026-11-06 | HAVASU HEROES COUNTRY MUSIC FESTIVAL FEATURING MATT FARRIS | title is ALL-CAPS — normalize casing |

## Low-severity / informational source buckets (aggregate)

These are **not** clear defects — they are the expected shape of booking/landing-domain sources, or cases our bot can’t auto-verify. Listed for completeness; itemized in the CSV.

- **Source unreachable to our bot (recheck) — 38.** Top: ironwolfgcc.com (23), lakehavasufarmersmarket.com (5), desertstormlhc.com (3), lakehavasuparadeoflights.com (2), lhusd.org (1), parks.mohave.gov (1).
- **Source reachable but no machine-readable schema — 31.** Top: riverscenemagazine.com (8), lakehavasucity.legistar.com (3), legistar1.granicus.com (2), business.havasuchamber.com (2), facebook.com (2), allevents.in (2).
- **Weak provenance (homepage only, not per-event) — 62.** Top: lakehavasufarmersmarket.com (19), graceartslive.com (9), womenwithwillpower.org (3), havasis.org (3), havasuarttrail.com (3), witchpaddlelhc.com (2).

> **`ironwolfgcc.com` (23 of the 38 “unreachable”)** is bot-blocking our Googlebot UA (HTTP 4xx/5xx), **not** proof those Iron Wolf events are gone — verify via the connector, don’t quarantine. `lakehavasufarmersmarket.com` and `graceartslive.com` “homepage-only” provenance is because they’re recurring venue feeds without per-event deep links.

## Recurring events & schedule-source drift

- **15 recurring (RRULE) events** were checked for source-link reachability only (their DTSTART is a 2024 anchor, so date/time can’t be feed-diffed). Dead recurring links: **0**.
- `schedule_drift_check.py` output (the 14-venue captured class schedules) is appended below — a DRIFT means that venue changed its schedule page and needs a targeted re-capture (the recurring analog of “changed at source”).

### Appendix — `schedule_drift_check.py` (recurring class-schedule sources)

`checked=17 drifted=10 errors=2` — a **DRIFT** = that venue changed its schedule page since the 2026-06-06 capture → targeted re-capture needed. **NEW** = no fingerprint baseline yet. **ERROR** = source unreachable. (The 7 DRIFT + 3 NEW = the 10 “drifted”.)

**Drifted (7):**
- The Tap Room Jiu Jitsu — schedule source changed since 2026-06-06
- The Study Yoga Studio & Creative Center — schedule source changed since 2026-06-06
- Eight Lotus Wellness and Yoga — schedule source changed since 2026-06-06
- Universal Sonics Gymnastics & All Star Cheer — schedule source changed since 2026-06-06
- Lake Havasu City Aquatic Center — schedule source changed since 2026-06-06
- Lake Havasu Senior Center — schedule source changed since 2026-06-06
- Iron Wolf Golf and Country Club — schedule source changed since 2026-06-06

**No baseline / new (3):** Havasu CrossFit, Fit Lab 928, Feelin' Good Fitness

**Errored (2):**
- Ballet Havasu: HTTPStatusError: Client error '404 Not Found' for url 'https://www.ballethavasu.org/2025'
- Lake Havasu Yacht Club: ConnectError: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] sslv3 alert handshake failure (_ssl.c:1028)

**OK / unchanged (5):** Bridge City Combat, Elite Martial Arts Inc, Amalaya Yoga, Arizona Coast Performing Arts, Arizona Kravmaga

