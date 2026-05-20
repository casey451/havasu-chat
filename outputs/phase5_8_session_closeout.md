# Phase 5.8 — Events — Session close-out (2026-05-17)

> **What this is:** the close-out for the single-session Phase 5.8 that
> picked up at `8dfa2a2` (the 5.8 kickoff doc pre-staged by Phase 5.7
> session 2) and pushed through to SHIP with all 6 gate items cleared.
> Phase 5.8 SHIPPED at `2808146`.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.8 session 1
> (2026-05-17) post-SHIP.

---

## §1 Commit chain (origin `8dfa2a2 → 2808146`)

| # | Commit | Subject | Source | Task |
|---|---|---|---|---|
| 1 | `0b426e1` | `fix(scripts)` — _PRIMARY_TYPE_MAP extend for Phase 5.8 sustainability layer | Cowork | §1 sustainability (Option A — 7 direct events primary_type mappings) |
| 2 | `f139be7` | `chore(outputs)` — Phase 5.8 narrow-label discovery wrapper | Cowork | §1 Layer 1 prep — Path A narrow-scope wrapper |
| 3 | `2808146` | `chore(outputs)` — Phase 5.8 SHIPPED — all 6 gate items cleared | Cowork | **SHIP** (bundles audit + apply-scripts + gate verification + close-out + 5.9 boot prompt) |

**Plus 5 DB-only writes** (no commit; events.db is gitignored):
1. **§1 Layer 1 load** — 52 in-LHC rows → 1 insert (cat-7 via catch-all) + 29 updates + 22 ambig + 0 unmapped
2. **§2 first apply** (Slice A 15 NEW + Slice B-2 + Slice C) — 17 new cat-2 rows
3. **§2 second apply** (Slice A 16th NEW — Lake Havasu Museum of History & Havasu Rocks, reclassified from Slice B-1) — 1 new cat-2 row
4. **§4 heat_exposure** — 19 entities set (17 indoor + 2 outdoor; the WORCS Racing override hit the 3rd outdoor seat); Buses By The Bridge + Desert Storm HQ already had heat_exposure from 5.7 lane? Actually all 19 had NULL pre-apply per the dry-run; first apply set 17 indoor + 3 outdoor; rerun no-op
5. **§4 crowd_notes** — 10 long-form notes on the top-10 by review_count

**Pytest baseline:** 1964 collected (5.7 baseline 1946 + 18 from `0b426e1`'s
`test_phase5_8_places_load_resolver.py` regression suite — 7 parametrized
event-type mappings + 1 place-type-default gate + 10 preservation tests).

**Ruff:** Clean throughout, except one I001 (import-sort) violation on
the crowd_notes apply-script's inline imports — fixed in-place via Edit
before commit (moved `from sqlalchemy import and_` + `from app.db.models
import Category, EntityCategory` to the top of the file).

**CI:** ✅ Green on `0b426e1` + `f139be7` + the SHIP commit. The sibling
`parks-rec-scrapes` cron continues to ❌ on schedule — root cause was
identified in Phase 5.7 §4.5 sidebar (Postgres FK constraint violation
in `scripts/parks_rec_prune.py`) and handed off to Phase 6 / sidecar
lane. Out of 5.8 scope.

---

## §2 Phase 5.8 acceptance gate — ALL 6 CLEARED ✅

| # | Gate item | Status | Where |
|---|---|---|---|
| 1 | 20+ entries in `events` post-load | ✅ **20** rendering (1.00× target) | 2 pre-existing + 0 §1 net insert (routed to cat-7 via catch-all) + 16 §2 Slice A NEW creates + 1 §2 Slice B-2 cross-cat move + 1 §2 Slice C DRAFT |
| 2 | All Google ↔ existing-entity ambiguous reconciler hits reviewed (+ 3 special audits) | ✅ **33 reviewed, 0 misroutes** | `outputs/phase5_8_events_audit.md` §3-7 — 17 FLIPs + 1 DRAFT + 15 KEEPs; special axes (a) cat-7 / (b) cat-13 / (c) seasonal-activation de-dup all cleared |
| 3 | Layer-4 verifier surface scoped — built or explicitly deferred to V1.5 | ✅ **Option C — deferred** | Operator picked Option C at kickoff §3; AZ event aggregators + LHC Tourism Board paths documented in audit §9 + kickoff §3 |
| 4 | Top-10 by reviews have long-form `crowd_notes` | ✅ **10** | Drafted from `Provider.google_review_snippets` (own column; 100% snippet coverage in top-10); see `outputs/apply_phase5_8_events_crowd_notes.py` |
| 5 | `heat_exposure` non-NULL on every entry | ✅ **0 NULL** of 20 | 17 indoor (default; theaters/bowling/galleries/museums are indoor-by-definition) + 3 outdoor (Buses By The Bridge, Desert Storm Headquarters, WORCS Racing) |
| 6 | `/category/events` renders ≥15 | ✅ **20** | 1.33× over target |

**Note: 6 gate items (not 7).** `is_mobile_service` was 5.5-specific and
is dropped for 5.8 — events are venue-based (same rationale as 5.6/5.7).

Final gate verification at `outputs/phase5_8_gate_verification.py` —
6/6 PASS, "PHASE 5.8 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED — READY TO
SHIP" line.

---

## §3 Notable artifacts shipped this session

### `0b426e1` — §1 sustainability (Option A — 7 direct events primary_type mappings)

Added 7 direct `_PRIMARY_TYPE_MAP` entries in
`app/contrib/google_types_mapping.py`:

```python
"event_venue":     ("events", "commercial"),
"art_gallery":     ("events", "place"),
"museum":          ("events", "place"),
"live_music_venue":("events", "commercial"),
"movie_theater":   ("events", "commercial"),
"bowling_alley":   ("events", "commercial"),
"amusement_arcade":("events", "commercial"),
```

Direct mappings beat the 5.7 `(None, "entertainment_attractions") →
"outdoors-parks-trails"` catch-all per the resolver order in
`scripts/places_load._resolve_category_id` — so cat-7 routing stays
correct for wildlife_refuge / tourist_attraction / etc. while these 7
event primary_types route to cat-2 events.

**Sustainability validation at §1 load:** 0 unmapped of 52 ✅ — the
catch-all-vs-direct-mapping resolver order works as designed.

Regression tests at `tests/test_phase5_8_places_load_resolver.py` —
18 collection items (7 parametrized event-type mappings + 1 place-
type-default gate + 10 preservation tests for 5.7 + 5.6 / 5.5 / 5.4 /
5.3 / 5.2 fallbacks). Pytest 1946 → 1964.

### `f139be7` — §1 Layer 1 narrow-scope wrapper

`outputs/phase5_8_narrow_label_filter.py` — short-circuits the
discovery loop to the 7 in-scope entertainment_attractions labels
(event venues, live music venues, art galleries, museums, movie
theaters, bowling alleys, arcades), deferring the 3 cat-7 labels
(parks, golf courses, mini golf) since 5.7 already absorbed them.
Mirrors `outputs/phase5_7_narrow_label_filter.py` exactly (Path A.2 —
standalone outputs/ wrapper, no production code touched).

sys.path bootstrap at lines 77-79 carried verbatim from 5.7. **First
dry-run smoke worked cleanly** — the 5.7 boot-session sys.path bug
did NOT re-surface.

### `2808146` — Phase 5.8 §2 audit + §4 apply-scripts + gate verification

Bundles all session §2-§4 work in one chunk:

- `outputs/phase5_8_events_audit.md` — combined post-load audit (§1
  summary + §2 §1-updates + §3 ambig aggregate + §4 Slice A/B/C
  decisions + §5-7 three special-audit axes + §8 gate-1 projection
  + §9 carry-forwards).
- `outputs/apply_phase5_8_events_audit.py` — §2 apply (16 NEW entity
  creates via `create_provider_and_entity` dual-write + 1 cross-cat
  move + 1 DRAFT new create). Substantially larger than 5.7's
  apply-script because 5.8's primary action is NEW creates (vs 5.7's
  FLIPs-out-of-cat-7).
- `outputs/apply_phase5_8_events_heat_exposure.py` — §4 heat sweep.
  Default flipped back to `indoor` (vs 5.7's `outdoor`); 3
  `OUTDOOR_OVERRIDES` (Buses By The Bridge, Desert Storm HQ, WORCS
  Racing). Matches kickoff §4 forecast of 2-5 overrides.
- `outputs/apply_phase5_8_events_crowd_notes.py` — §4 top-10
  crowd_notes. Hand-curated short+long for each entity sourced from
  `Provider.google_review_snippets` (own column; 100% snippet
  coverage). Dict-direct to JSON column per 5.3 `f35d5e4` gotcha.
- `outputs/phase5_8_top10_discovery.py` — read-only top-10 discovery
  helper for the crowd_notes drafting step (audit-trail artifact).
- `outputs/phase5_8_top10_data.json` — top-10 emission with full
  snippet text (audit-trail artifact).
- `outputs/phase5_8_ambig_audit_data.json` — §2 ambig dump emission
  (33 records; audit-trail artifact).
- `outputs/phase5_8_ambig_audit_dump.py` — §2 dump script (read-only).
- `outputs/phase5_8_ambig_audit_stdout.txt` — §2 dump stdout
  (aggregates + 3 special-audit-axis output + edge-case rubric table).
- `outputs/phase5_8_gate_verification.py` — 6-gate verifier (mirrors
  `phase5_7_gate_verification.py` shape with 5.8 overrides).
- `docs/scrape_logs/events_2026-05-17.md` — combined pre+post scrape
  log with live §0 status + §1 cost numbers ($0.62-0.92 actual, well
  under the kickoff $0.50-1.20 projection).
- This close-out doc + the Phase 5.9 boot prompt.

### **NOT shipped this session: AZ event aggregators / LHC Tourism Board verifier surface**

Operator picked Option C at kickoff — no Layer-4 verifier built for
5.8. **Re-tag locked 2026-05-19 per V1.5 triage §8 #2 lock:**
golakehavasu.com → Phase 9 Source 2 (absorbed); visitarizona.com →
V1.5 — defer with Phase 9 Source 6 upgrade hook. See
`outputs/lane_m_retag_5_8_aggregators_decision_lock.md` for the
full decision-lock memo.

### **NOT shipped this session: `parks-rec-scrapes` cron fix**

Carried per Phase 5.7 close-out §3 to Phase 6 / sidecar lane. 3 fix
options surfaced (alembic `ON DELETE SET NULL`, prune-script WHERE
NOT EXISTS clause, ON DELETE CASCADE — recommended option 1).

### Pre-flight surprises (0 found — clean run)

5.7-session-2 forecast of a 5th `places_categories.json` corruption
recurrence did NOT materialize. 4-file shape diff was empty at §0.
Carrying the watch into 5.9.

---

## §4 §2 audit — substantial NEW-create surface (vs 5.7's FLIP-out surface)

The kickoff §2 forecast 20-60 ambig hits; the dump's wider
entertainment-label filter surfaced 33 records (22 from 5.8's actual
ambig + 11 cross-phase noise). The audit decisions:

- **16 Slice A NEW entity creates** — high-confidence event venues +
  art galleries + museums + community lodges + an event-rental
  service. Each candidate was the matched-existing-entity's
  geo-adjacent but distinct business; the reconciler ambig-skipped
  them by design and the apply-script overrode with `create_provider_
  and_entity` dual-write.
- **1 Slice B-2 cross-cat move + un-DRAFT** — Altitude Trampoline
  Park (cat-7 DRAFT → cat-2 visible). 5.7 §2 had DRAFTed it pending
  the 5.8 lane.
- **1 Slice C DRAFT** — Simply Savage Designs (art_gallery primary but
  name suggests design shop; 1 review — low signal). Place-typed
  (art_gallery → place per the sustainability commit) so it renders
  even drafted; operator can un-DRAFT or DELETE in V1.5.
- **15 KEEPs as ambig** — 4 5.8-relevant low-signal candidates +
  11 cross-phase noise records (labels not in 5.8 Narrow scope).

**0 real misroutes** — all 30 cross-cat matches in the ambig pool were
benign geo-proximity false positives; the matched eat-drink / HWC /
HPS / on-the-water / shopping / civic entities all stay in their
current cats.

**Mid-apply correction surfaced (documented for posterity):** the
audit doc's original Slice B-1 (Lake Havasu Museum of History cat-6
→ cat-2 move) was based on a misreading of the kickoff §2 framing.
DB query confirmed no pre-existing museum entity in DB — the 5.7 §1
ambig pool included a museum candidate that 5.7 close-out §4 KEPT-
ambig ("0 flips needed"), meaning no DB row was created. The 5.8
candidate "Lake Havasu Museum of History & Havasu Rocks" was added
to Slice A as the 16th NEW create. Audit doc updated to reflect.

---

## §5 Sustainability layer update (`0b426e1`)

`_PRIMARY_TYPE_MAP` extended with 7 events primary_types per the
kickoff §1 Option A pattern. Direct mappings beat the 5.7 catch-all
in resolver order. Plus 18-test regression guard suite covering the 7
new entries + 5.7's golf_course/medical_clinic widenings + 5.7's
entertainment_attractions catch-all + 5.6/5.5/5.4/5.3/5.2 fallbacks.

### Sustainability matrix (updated)

| Field | Auto on re-pull? | Auto for new business? |
|---|---|---|
| `Provider.category_id` from `_resolve_category_id` | ✅ preserved if set | ✅ resolved at INSERT (now covers 7 events primary_types directly + 5.7's entertainment_attractions catch-all for non-mapped) |
| `EntityCategory` linkage | ✅ via `_ensure_entity_category` | ✅ via dual-write hook |
| `Provider.verified` | ✅ not overwritten by re-pull | ❌ deferred to V1.5 (no verifier ran in 5.8) |
| `heat_exposure` | ✅ not overwritten | ❌ lands NULL — needs periodic sweep (default `indoor` for 5.8) |
| `is_mobile_service` | n/a for events (gate-dropped) | n/a |
| `crowd_notes` | ✅ not overwritten | ❌ — needs operator curation |
| `Provider.draft` | ✅ preserved | ⚠️ defaults False; operator review needed for new entries needing DRAFT |

**Phase 5.9 (next Tier-1 category)** — likely
`classes-sports-recreation` or `pets` per the remaining ~4-slug list.
5.7's deferred `fitness_sports` labels (gyms, yoga, pilates, etc.)
are the natural 5.9 input pool if 5.9 builds against
`classes-sports-recreation`. Sustainability layer extensions
expected: the existing `(None, "fitness_sports") →
"health-wellness-care"` fallback from 5.4 will need re-routing or
direct primary_type mappings if 5.9 picks `classes-sports-recreation`
(mirror Phase 5.8's PIVOT pattern via Option A).

---

## §6 Remaining work for next session (Phase 5.9)

### Gate-blocking (0) — Phase 5.8 SHIPPED at `2808146`

All 6 gate items met per `outputs/phase5_8_gate_verification.py`. The
SHIPPED commit landed on `origin/main` at `2808146` 2026-05-17.

### 🚨 Carry-over for operator-side action

- **Phase 6 lane dispatch: Phase 5.8 SHIPPED ledger amendment** —
  author `outputs/claude_code_dispatch_phase6_amend8.md` (mirrors the
  Amendment 7 pattern that itself is a Phase 5.7 carry) for operator
  to paste into Claude Code OR land in-line per the 5.4 `0addb63`
  precedent.
- **Phase 6 / sidecar lane: `parks-rec-scrapes` cron fix** — 3 fix
  options surfaced in Phase 5.7 close-out §3 (carry forward from
  Phase 5.7). Recommended: alembic migration adding `ON DELETE SET
  NULL` on `contributions.created_event_id` FK.
- **V1.5: re-evaluate art_gallery / museum entity_type from `place`
  to `commercial`** — kickoff §1 starting point chose `place`; in
  practice most LHC museums + many galleries charge admission. The
  §2 audit can be re-run with selective `commercial` flips on a
  per-entry basis if operator opts in.
- **V1.5: Lake Havasu Museum of History place_id unification** — two
  Google place_ids found for the same business (the 5.7-ambig
  "Lake Havasu Museum of History" candidate ChIJF1jVdeXt0YARb6LROJcnP4I
  was actually the same as the 5.8 "& Havasu Rocks" candidate; the
  5.8 candidate was created in 5.8 §2). Operator V1.5 picks primary
  place_id + archives the other.
- **V1.5: Simply Savage Designs DRAFT review** — art_gallery primary
  but name suggests design shop; operator decides un-DRAFT or DELETE.
- **V1.5: `wildlife_refuge` direct mapping** — soft-edge carry from
  5.7. 1-line addition same shape as 5.7's `golf_course` /
  `medical_clinic` widenings.
- **V1.5 soft-edges from 5.7**: 5 entries (SARA Disc Golf / Motocross
  / Ofd Racing / Thompson Bay Beach / Sportsman's Club) flagged for
  dual-cat consideration. Sara Park Hiking Trail ↔ Trail Head
  ~16m-apart pair. Butterfly Garden investigation. ASU SWANSON
  FIELDS uppercase normalization.
- **86 of 265 HWC providers remain `verified=False`** — carry-over
  from 5.4. Operator-driven DBA→NPI follow-up surface (optional
  V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable
  (carry-over from 5.3 + 5.4 + 5.5 + 5.6 + 5.7).
- **Google Places API key rotation** still deferred per operator
  ("all keys will be changed at the conclusion of this project").

### Soft-edges (4 deferred per `phase5_8_events_audit.md` §9)

- Lake Havasu City Aquatic Center (HWC discovery label, civic
  facility — V1.5 dual-cat with cat-12 or cat-13)
- Nomadic coworking space (V1.5 cat-12 candidate)
- Lions Dog Park (cat-7 candidate not yet in DB)
- Main Street Commons (park with cat-7 label, 110 reviews — V1.5
  hand-curation)

None are gate-blocking.

### Files-to-prune carry-over

`hava_api_catalog.docx` + `~$va_api_catalog.docx` (Word lock) + 2
`outputs/ci_*_log_failed.txt` historical CI logs + `outputs/_deltest`
in working tree. Unrelated to the 5.8 lane; operator prunes when
comfortable.

### `data/events.db.bak-*` files (carry-over from 5.3 + 5.4 + 5.5 + 5.6 + 5.7)

Backup files may continue to accumulate. Operator prunes when
comfortable.

### Sandbox bash MOUNT STALENESS — pattern continues

5.8 hit it twice: (a) `wc -l` on a freshly-Edited file showed 133
when HEAD was 176 (post-Edit count would have been ~210); (b)
post-Edit lints surfacing inline imports as I001 only ran cleanly
when actually invoked Windows-side via ruff. The Read tool remains
authoritative; sandbox bash file-shape queries are unreliable for
post-Edit verification. Continue to default to Read + `git show
HEAD:` for sandbox-side text inspection; Windows-side `python` +
`git status` / `git diff` for working-tree state + DB query.

### PowerShell `\"` escape footgun (5.7 carry)

The 5.7-discovered footgun didn't bite this session (used
single-quoted `-m '...'` for git commits throughout). Continue the
single-quoted-`-m` discipline in 5.9.

---

## §7 Coordination summary (one-line)

| Lane | Coordination need |
|---|---|
| Phase 6 (parallel agent OR in-line) | Amend `master_build_plan.md` + `STATE.md` with Phase 5.8 SHIPPED at `2808146` via `outputs/claude_code_dispatch_phase6_amend8.md`; ALSO `parks-rec-scrapes` cron fix per 5.7 close-out §3 |
| Cursor | No dispatches pending (Phase 5.8 produced its own regression tests in-lane: +18 at 1964 via `0b426e1`) |
| Operator | Audit doc carry-over actions (V1.5 verifier build, art_gallery/museum entity_type flip review, Simply Savage Designs DRAFT review, Lake Havasu Museum place_id unification, wildlife_refuge widening), file-prune list (.bak files + stray .docx + historical CI logs + `outputs/_deltest`), API key rotation (deferred to project end) |

---

## §8 Read order for the next session (Phase 5.9)

1. **This document** — the state of play (close-out + commit chain).
2. `outputs/phase5_9_<category>_kickoff.md` — Phase 5.9 runbook
   (authoritative for the §6 acceptance gate definitions; **next
   agent authors this if not yet present**, mirroring
   `outputs/phase5_8_events_kickoff.md` shape).
3. `outputs/phase5_9_next_agent_boot_prompt.md` — next-phase
   boot prompt authored this session for 5.9 priming.
4. `outputs/phase5_8_events_audit.md` — combined post-load audit doc
   (template the 5.9 audit will mirror).
5. `outputs/apply_phase5_8_events_audit.py` /
   `_heat_exposure.py` / `_crowd_notes.py` — template apply-scripts
   that 5.9 equivalents will mirror.
6. `outputs/phase5_8_gate_verification.py` — template for
   `outputs/phase5_9_gate_verification.py`.

---

## §9 Pre-flight for the next session

1. **`git log --oneline -15`** — origin should top at `2808146`
   or later (Phase 6 lane may push `0addb63`-shape Amendment 8
   between sessions).
2. **`git status`** — clean. Note the carry-over file-prune list above.
3. **`python -m alembic current`** — `0a1b2c3d4e5f` (unchanged across
   all 5.x phases unless the parks-rec-scrapes sidecar lands first).
4. **`python -m pytest -q --collect-only 2>&1 | Select-Object -Last 3`**
   — expect **1964 collected** (5.8 baseline). Verify no drift.
5. **`gh run list --branch main --limit 5`** — top run should be ✓ on
   `2808146`. Note that `parks-rec-scrapes` scheduled jobs
   continue to ❌ unless the Phase 6 / sidecar fix lands first.
6. **DB state spot-check** — `events` should show **20 entries / 0
   verified / 17 indoor + 3 outdoor / 20 render (1 drafted but
   place-typed renders) / 10 long-form crowd_notes** (the 5.8 SHIPPED
   state). `outdoors-parks-trails` should show **27-28 entries** (the
   §1 net insert may have added to cat-7 too — operator can verify).
7. **WIDENED four-file shape check** per kickoff §0 item 6:
   ```powershell
   git diff --stat scripts/places_categories.json scripts/places_load.py app/db/models.py app/contrib/google_types_mapping.py
   ```
   MUST be empty. (Forecast: 5.8 didn't recur the 5.5/5.6/5.7-boot
   `places_categories.json` corruption; pattern still worth watching.)
8. **Phase 5.9 sub-trade scope** — kickoff doc should land first.
   Likely `classes-sports-recreation` (the deferred 5.7
   fitness_sports + 5.8 cat-12 carry-overs) or `pets` (much smaller
   surface; 5.7 §6 close-out listed it). Operator picks at boot.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.8 session 1
(2026-05-17) post-`2808146`. Phase 5.8 SHIPPED with all 6 gate
items cleared in a single session; 3 commits on origin/main from
`8dfa2a2` → `2808146` (`0b426e1` sustainability + `f139be7`
wrapper + SHIP). Plus 5 DB-only writes (1 load + 2 audit applies + 1
heat + 1 crowd_notes). Hand-off to Phase 5.9 next session.*
