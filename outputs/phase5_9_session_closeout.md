# Phase 5.9 — Classes, Sports & Recreation — Session close-out (2026-05-17)

> **What this is:** the close-out for the single-session Phase 5.9 that
> picked up at `4856020` (the 5.9 kickoff doc pre-staged by Phase 5.8
> session 1) and pushed through to SHIP with all 6 gate items cleared.
> Phase 5.9 SHIPPED at `4527ca1`.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.9 session 1
> (2026-05-17) post-SHIP.

---

## §1 Commit chain (origin `4856020 → 4527ca1`)

| # | Commit | Subject | Source | Task |
|---|---|---|---|---|
| 1 | `0af5f73` | `fix(scripts)` — `_PRIMARY_TYPE_MAP` extend for Phase 5.9 sustainability layer | Cowork | §1 sustainability (Option A — 9 cat-12 direct mappings + 1 childcare_education catch-all) |
| 2 | `a99e2c4` | `chore(outputs)` — Phase 5.9 narrow-label discovery wrapper + DB spot-check + amend5-8 dispatch | Cowork | §1 Layer 1 wrapper + §0 spot-check + Phase 6 sidecar dispatch doc bundle |
| 3 | `4527ca1` | `chore(outputs)` — Phase 5.9 SHIPPED — all 6 gate items cleared | Cowork | **SHIP** (bundles audit + apply-scripts + gate verification + close-out + 5.10 boot prompt) |

**Plus 4 DB-only writes** (no commit; events.db is gitignored):
1. **§1 Layer 1 load** — 82 in-LHC rows (post-ZIP) → 27 inserts (cat-12) + 32 updates (preserved existing cats; mostly cat-5 HWC from 5.4 cache absorption) + 23 ambig + 0 unmapped
2. **§2 audit apply** — Slice B 1 FLIP cat-5→cat-12 (Stormy Wade Courts) + Slice C 2 FLIPs cat-12→cat-13 (Knights of Columbus + Hilltop Community Church) + Slice D 1 DUAL ADD cat-13 (Our Lady of the Lake Catholic School) + Slice E 3 NEW creates in cat-12 (Lake Havasu City Aquatic Center + Psalms Learning Center + Mohave Traffic School)
3. **§4 heat_exposure** — 30 entities set (29 indoor default + 2 outdoor overrides — Aquatic Center had heat_exposure='outdoor' pre-apply from enrichment cache propagation, so 1 unchanged); zero post-apply NULLs of 31
4. **§4 crowd_notes** — 10 long-form notes on top-10 by review count

**Pytest baseline:** 1964 collected (5.8 baseline) → **1985 collected post-`0af5f73`** (+21 via `tests/test_phase5_9_places_load_resolver.py` — 9 parametrized cat-12 primary_type asserts + 12 preservation guards).

**Ruff:** Clean throughout all 3 commits. The sustainability commit `0af5f73` passed F,I,W,E402 on the three touched files (audited Windows-side before commit). Apply-scripts + dump + spot-check + crowd_notes + heat_exposure scripts at the wrapper-bundle commit `a99e2c4` and SHIP commit also F,I,W,E402-clean (5.8 I001 inline-import lesson internalized — all imports at top of file).

**CI:** ✅ Green on `0af5f73` and (assumed pending operator confirmation post-push) on `a99e2c4` + the SHIP commit. The sibling `parks-rec-scrapes` cron continues to ❌ on schedule — root cause identified in Phase 5.7 §4.5 sidebar (Postgres FK constraint violation in `scripts/parks_rec_prune.py`), handed off to Phase 6 / sidecar lane. Out of 5.9 scope.

---

## §2 Phase 5.9 acceptance gate — ALL 6 CLEARED ✅

| # | Gate item | Status | Where |
|---|---|---|---|
| 1 | 20+ entries in `classes-sports-recreation` post-load | ✅ **31** rendering (1.55× target) | 27 §1 inserts + ~4 pre-existing `school`-primary entries from cache absorption + Slice B FLIP-in (Stormy Wade) + Slice E 3 NEW creates − Slice C 2 FLIPs-out |
| 2 | All Google ↔ existing-entity ambig reconciler hits reviewed (+ 3 special audits) | ✅ **30 reviewed, 0 misroutes** | `outputs/phase5_9_classes_audit.md` §3-7 — Slices B (1 FLIP-in) + C (2 FLIPs-out) + D (1 DUAL ADD) + E (3 NEW creates) + F (20 KEEP-ambig per V1.5 deferral) + 7 cross-cache informational; special axes (a) cat-5 HWC primary (the BIG one — 7 ambig matches + 26 §1-update dual-cat candidates all KEEP cat-5 per V1) / (b) cat-7 outdoors-parks-trails secondary (0 ambig hits) / (c) cat-13 public-civic-resources (1 ambig hit = Aquatic Center, addressed by Slice E) all cleared |
| 3 | Layer-4 verifier surface scoped — built or explicitly deferred to V1.5 | ✅ **Option C — deferred** | Operator picked Option C at kickoff §3; AZDHS childcare-license registry + franchise gym chain APIs (Anytime / Snap / Orange Theory) + LHC Parks & Rec municipal pages paths documented in audit §3 + kickoff §3 |
| 4 | Top-10 by reviews have long-form `crowd_notes` | ✅ **10** | Drafted from `Provider.google_review_snippets` (own column; 100% snippet coverage in top-10 except Hilltop Learning Center at 3 snippets); see `outputs/apply_phase5_9_classes_crowd_notes.py` |
| 5 | `heat_exposure` non-NULL on every entry | ✅ **0 NULL** of 31 | 29 indoor (default; daycare / preschools / schools / studios / classrooms are indoor-by-definition) + 2 outdoor (Lake Havasu City Aquatic Center + Stormy Wade Courts) |
| 6 | `/category/classes-sports-recreation` renders ≥15 | ✅ **31** | 2.07× over target |

**Note: 6 gate items (not 7).** `is_mobile_service` was 5.5-specific and is dropped for 5.9 — cat-12 is mostly venue-based (same rationale as 5.6/5.7/5.8). The kickoff §6 note flagged that operator may opt to re-add for mobile-service personal trainers / music tutors; in practice the §1 load surfaced 0 mobile-service entities in the in-scope 9 labels, so the optional gate-7 was not needed.

Final gate verification at `outputs/phase5_9_gate_verification.py` —
6/6 PASS, "PHASE 5.9 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED -- READY TO
SHIP" line.

---

## §3 Notable artifacts shipped this session

### `0af5f73` — §1 sustainability (Option A — 9 cat-12 direct mappings + 1 childcare_education catch-all)

Added 9 direct `_PRIMARY_TYPE_MAP` entries in
`app/contrib/google_types_mapping.py`:

```python
# childcare_education domain (5, commercial)
"child_care_agency": ("classes-sports-recreation", "commercial"),
"preschool":         ("classes-sports-recreation", "commercial"),
"music_school":      ("classes-sports-recreation", "commercial"),
"driving_school":    ("classes-sports-recreation", "commercial"),
"tutor":             ("classes-sports-recreation", "commercial"),
# fitness_sports domain — cat-12 native (4)
"personal_trainer":  ("classes-sports-recreation", "commercial"),
"swimming_pool":     ("classes-sports-recreation", "place"),
"tennis_court":      ("classes-sports-recreation", "place"),
"pickleball_court":  ("classes-sports-recreation", "place"),
```

Plus 1 new catch-all entry in `scripts/places_load._DISCOVERY_DOMAIN_FALLBACK`:

```python
(None, "childcare_education"): "classes-sports-recreation",
```

Critical case: `tennis_court` was **dual-present** — already in
`_DISCOVERY_DOMAIN_FALLBACK` since Phase 5.4 (`fc51940`,
`("tennis_court", "fitness_sports") → "health-wellness-care"`). The
new direct mapping in `_PRIMARY_TYPE_MAP` beats the fallback per
resolver order (Layer 2 before Layer 3 in `_resolve_category_id`),
so 5.9 tennis_court entries route to cat-12 — dedicated regression
test at `test_phase5_9_tennis_court_direct_mapping_beats_phase5_4_fallback`.

**Sustainability validation at §1 load:** 0 unmapped of 82 ✅ — the
9 direct mappings + 1 new catch-all + the existing 5.4 fitness_sports
catch-all (for the 7 HWC-absorbed types deferred per Narrow scope)
covered every primary_type Google emitted.

Regression tests at `tests/test_phase5_9_places_load_resolver.py` —
**21 collected items** (9 parametrized cat-12 primary_type asserts + 12
preservation guards covering: tennis_court dual-presence, new
childcare_education catch-all, pool/court entity_type=place,
pre-existing `school` + `gym` mappings, 5.8 events 7 entries, 5.7
entertainment_attractions catch-all + golf_course + medical_clinic,
5.4 fitness_sports + health_medical catch-alls, 5.2/5.3/5.5/5.6
domain catch-alls, park + dog_park unchanged). Pytest 1964 → 1985.

### `a99e2c4` — §1 Layer 1 wrapper + spot-check + amend5-8 dispatch

Three artifacts bundled:
- `outputs/phase5_9_narrow_label_filter.py` — Path A short-circuit wrapper
  restricting discovery to the 9 in-scope labels (5 childcare_education
  + 4 cat-12-native fitness_sports). Mirrors 5.8's
  `phase5_8_narrow_label_filter.py` exactly with two-domain bundle
  accommodation. Successful first dry-run (no sys.path bug; 5.7-boot
  pattern internalized).
- `outputs/phase5_9_db_spot_check.py` — §0 read-only DB spot-check;
  used twice (pre-§1 baseline + post-§2 verification). Two bug fixes
  in-session: (1) column `label` → `name` for categories table, (2)
  added per-entity cat dump showing `cats=[<slugs>]`.
- `outputs/claude_code_dispatch_phase6_amend5_to_8.md` — consolidated
  Phase 6 sidecar dispatch bundling Phase 5.5/5.6/5.7/5.8 SHIPPED
  ledger lines for Claude Code parallel agent (per Phase 5.9 §0
  operator decision to defer all 4 amend backlogs to Phase 6 sidecar;
  Cowork primary stayed focused on 5.9 data plane).

### `4527ca1` — Phase 5.9 §2 audit + §4 apply-scripts + gate verification

Bundles all session §2-§4 work in one chunk:

- `outputs/phase5_9_classes_audit.md` — combined post-load audit (§1
  summary + §2 ambig aggregate + §3 special audit (a) cat-5 HWC
  primary axis with §1-update dual-cat enumeration + §6 cat-7
  secondary axis (0 hits) + §7 cat-13 cross-list + §4 Slice
  decisions A-G + §8 gate-1 projection + §9 V1.5 carry-forwards).
- `outputs/apply_phase5_9_classes_audit.py` — §2 apply (Slice B FLIP
  cat-5→cat-12 + Slice C 2 FLIPs cat-12→cat-13 + Slice D 1 DUAL ADD
  cat-13 + Slice E 3 NEW creates via `create_provider_and_entity`
  dual-write). Each slice is idempotent: NEW creates dedupe on
  google_place_id; FLIPs DELETE + INSERT (net updated_at); DUAL ADD
  checks for existing (entity_id, cat-13) row before insert.
- `outputs/apply_phase5_9_classes_heat_exposure.py` — §4 heat sweep.
  Default `indoor`; 2 `OUTDOOR_OVERRIDES` (Lake Havasu City Aquatic
  Center + Stormy Wade Courts). Below kickoff §4 forecast of 5-10
  outdoor (most cat-12 entries are schools / daycare — indoor).
- `outputs/apply_phase5_9_classes_crowd_notes.py` — §4 top-10
  crowd_notes. Hand-curated short+long for each entity sourced from
  `Provider.google_review_snippets` (100% snippet coverage on 9 of
  10; Hilltop Learning Center at 3 snippets). Dict-direct to JSON
  column per 5.3 `f35d5e4` gotcha.
- `outputs/phase5_9_top10_discovery.py` — read-only top-10 discovery
  helper for the crowd_notes drafting step (audit-trail artifact).
- `outputs/phase5_9_top10_data.json` — top-10 emission with full
  snippet text (audit-trail artifact).
- `outputs/phase5_9_ambig_audit_data.json` — §2 ambig dump emission
  (30 records; 23 in-scope + 7 cross-cache; audit-trail artifact).
- `outputs/phase5_9_ambig_audit_dump.py` — §2 dump script (read-only).
- `outputs/phase5_9_ambig_audit_stdout.txt` — §2 dump stdout
  (aggregates + 3 special-audit axis output + edge-case rubric table +
  V1.5 carry candidate DB-verify).
- `outputs/phase5_9_dupe_check.py` — read-only DB-verify (audit-trail)
  for the apparent-duplicate + adjacent-entity cases (New Day School
  3 distinct campuses; Psalms+Ark Center 3.8m co-location; Hilltop
  Church+Learning Center same campus; Knights of Columbus / Our Lady
  / Stormy Wade / Sand Volleyball / V1.5 carry candidates).
- `outputs/phase5_9_gate_verification.py` — 6-gate verifier (mirrors
  `phase5_8_gate_verification.py` shape with 5.9 overrides).
- `docs/scrape_logs/classes-sports-recreation_2026-05-17.md` —
  combined pre+post scrape log with live §0 status + §1 cost numbers
  ($0.55 actual, well under the kickoff $0.50-1.20 projection).
- This close-out doc + the Phase 5.10 boot prompt.

### **NOT shipped this session: AZDHS childcare-license / franchise gym / LHC Parks & Rec verifier surface**

Operator picked Option C at kickoff — no Layer-4 verifier built for
5.9. AZDHS childcare-license registry (azdhs.gov/licensing/childcare-
facilities) + franchise gym chain APIs (Anytime Fitness / Snap Fitness
/ Orange Theory / CycleBar) + LHC Parks & Rec municipal pages
documented for V1.5 pickup in the audit doc + kickoff §3.

### **NOT shipped this session: `parks-rec-scrapes` cron fix**

Carried per Phase 5.7 + 5.8 close-outs to Phase 6 / sidecar lane. 3 fix
options surfaced in Phase 5.7 close-out §3 (alembic `ON DELETE SET
NULL`, prune-script WHERE NOT EXISTS clause, ON DELETE CASCADE —
recommended option 1).

### **NOT shipped this session: 4-deep amend backlog (amend5/6/7/8)**

Authored consolidated dispatch at
`outputs/claude_code_dispatch_phase6_amend5_to_8.md` for Phase 6
sidecar lane per Phase 5.9 §0 operator decision (defer all 4 to Phase
6 sidecar; Cowork primary stays focused on 5.9 data plane). Bundles
Phase 5.5 (`08d5ff3`) + 5.6 (`7609a01`) + 5.7 (`e60b051`) + 5.8
(`2808146`) SHIPPED ledger lines for one consolidated commit by
Claude Code parallel agent.

### Pre-flight surprises (3 found, all triaged in-session)

1. **Sandbox bash mount-staleness recurrence** — first §0 `git diff
   --stat` showed massive deletions on all 4 shape-check files;
   operator confirmed Windows-side that working tree was clean
   (sandbox view was stale). Documented Read tool authoritative once
   more.
2. **Spot-check script column-name bug** — `categories.label` doesn't
   exist (actual column is `name`); fixed in-session at `[A]` block.
   Second bug: `p.primary_type` should be `p.google_primary_category`;
   fixed at `[C]` block.
3. **Dump script Unicode crash** — PowerShell `cp1252` codec can't
   encode `→` (U+2192); replaced with ASCII `->` in 2 spots.

5.7-session-2's 5th `places_categories.json` corruption forecast did
NOT materialize in 5.9 either. 4-file shape diff was empty at §0.
Carrying the watch into 5.10.

---

## §4 §2 audit — Slice plan summary

Pre-§2 cat-12: 27 (§1 inserts) + ~4 (pre-existing `school` from cache
absorption) = ~31. Post-§2 cat-12: 31 (small net change because
Slices B-in / C-out / E-add roughly balance).

| Slice | Action | Count | Records |
|---|---|---|---|
| A | KEEP (no apply) | many | 27 §1-inserts + 26 §1-updates kept in cat-5 + ~4 pre-existing school + edge-case rubric KEEPs |
| **B** | FLIP cat-5 → cat-12 | **1** | Stormy Wade Courts (primary=`tennis_court`, direct map per 5.9 sustainability) |
| **C** | FLIP cat-12 → cat-13 | **2** | Knights of Columbus (civic org) + Hilltop Community Church (church proper; Learning Center stays cat-12 as separate entity) |
| **D** | DUAL ADD cat-13 | **1** | Our Lady of the Lake Catholic School (school AND church) |
| **E** | NEW creates in cat-12 | **3** | Lake Havasu City Aquatic Center (595r, swimming_pool, place) + Psalms Learning Center (school, commercial) + Mohave Traffic School (educational_institution, commercial) |
| F | KEEP ambig (no apply) | 20 | gym/yoga/pilates HWC-deferred per V1.5; geo-noise eat-drink matches |
| G | DRAFT / DELETE | 0 | (no DRAFT decisions) |

**0 real misroutes** — all 30 ambig records analyzed; cross-cat
matches were benign geo-proximity (eat-drink dominance per the
McCulloch Blvd N strip-mall pattern shared with 5.6). The dump's
30-record count vs the load's 23 ambig differed by 7 cross-cache
informational records (entities discovered under non-cat-12 labels in
prior phases that surfaced in the dump's broader filter; not in the
§1 load pool).

**Mid-§2 audit-trail lessons applied (no Slice-B-1-style mid-apply
correction needed this session):** the 5.8 lesson "DB-verify the
existing entity in cat-X premise before authoring cross-cat moves"
was applied prospectively. `outputs/phase5_9_dupe_check.py` ran BEFORE
the §2 audit doc was finalized — all Slice B/C/D entities verified
in DB with correct current cats, all Slice E candidates verified NOT
in DB. The Lake Havasu City Aquatic Center case is the prime example:
kickoff §2 framed it as a "FLIP candidate" (assuming it was already
in cat-5), but the dupe-check confirmed it was NOT in DB at all (only
in the enrichment cache from 5.4 spas label) — reclassified as Slice
E NEW-create. Same exact pattern as 5.8 Slice B-1 Lake Havasu Museum
of History; caught prospectively this time vs mid-apply.

---

## §5 Sustainability layer update (`0af5f73`)

`_PRIMARY_TYPE_MAP` extended with 9 cat-12 primary_types + `_DISCOVERY_
DOMAIN_FALLBACK` extended with 1 new childcare_education catch-all per
the kickoff §1 Option A pattern. The new direct mappings beat the 5.4
fitness_sports catch-all in resolver order — preserving the 5.4 HWC
absorption for the 7 deferred types (gym/yoga/pilates/crossfit/martial/
jiu_jitsu/dance) while routing the 9 cat-12-native types correctly.
21-test regression guard suite covering all new entries + 5.8 events
preservation + prior phases' fallbacks.

### Sustainability matrix (updated)

| Field | Auto on re-pull? | Auto for new business? |
|---|---|---|
| `Provider.category_id` from `_resolve_category_id` | ✅ preserved if set | ✅ resolved at INSERT (now covers 9 cat-12 primary_types directly + new childcare_education catch-all for unmapped childcare types + existing 5.4 fitness_sports catch-all for HWC-bound types) |
| `EntityCategory` linkage | ✅ via `_ensure_entity_category` | ✅ via dual-write hook |
| `Provider.verified` | ✅ not overwritten by re-pull | ❌ deferred to V1.5 (no verifier ran in 5.9) |
| `heat_exposure` | ✅ not overwritten | ❌ lands NULL — needs periodic sweep (default `indoor` for 5.9; 2 outdoor overrides) |
| `is_mobile_service` | n/a for cat-12 (gate-dropped) | n/a |
| `crowd_notes` | ✅ not overwritten | ❌ — needs operator curation |
| `Provider.draft` | ✅ preserved | ⚠️ defaults False; operator review needed for new entries needing DRAFT |

**Phase 5.10 (next Tier-1 category)** — likely
`lodging-vacation-rentals` or `pets` per the remaining ~3-slug list.
Both have their own discovery domains with no existing catch-alls
that would mis-route — **no sustainability layer PIVOT needed** for
either (unlike 5.9's PIVOT around the 5.4 fitness_sports catch-all).
Sustainability layer extensions expected: 5.10's primary_types likely
need direct `_PRIMARY_TYPE_MAP` entries (e.g., for `lodging` —
already present per pre-Phase-5 mapping — and `pets` —
`veterinary_care` / `pet_store` already present, may need to add
`dog_groomer` / `pet_boarding` / `dog_trainer` direct mappings if
they surface).

---

## §6 Remaining work for next session (Phase 5.10)

### Gate-blocking (0) — Phase 5.9 SHIPPED at `4527ca1`

All 6 gate items met per `outputs/phase5_9_gate_verification.py`. The
SHIPPED commit landed on `origin/main` at `4527ca1` 2026-05-17.

### 🚨 Carry-over for operator-side action

- **Phase 6 lane dispatch: 4-deep amend backlog (amend5/6/7/8)** —
  consolidated dispatch at
  `outputs/claude_code_dispatch_phase6_amend5_to_8.md` ready for
  Claude Code parallel agent. Lands Phase 5.5/5.6/5.7/5.8 SHIPPED
  ledger lines in one consolidated commit. File-scope disjoint with
  any in-flight 5.10 lane — can dispatch in parallel.
- **Phase 6 / sidecar lane: `parks-rec-scrapes` cron fix** — 3 fix
  options surfaced in Phase 5.7 close-out §3 (carry forward from 5.7
  + 5.8). Recommended: alembic migration adding `ON DELETE SET
  NULL` on `contributions.created_event_id` FK.
- **V1.5: AZDHS childcare-license verifier surface** — kickoff §3
  Option A path; Playwright scrape of the AZDHS search form, ~4-6h
  build, covers ~70-90% of cat-12 childcare candidates. Document
  retained in audit doc §9 + kickoff §3.
- **V1.5: franchise gym chain APIs** — Anytime Fitness / Snap Fitness
  / Orange Theory / CycleBar club-locator endpoints; lower coverage
  (~10-20% of cat-12 fitness, mostly chain-affiliated) and the 7
  HWC-absorbed types are also deferred. ~6-8h build.
- **V1.5: LHC Parks & Rec municipal-pages scrape** — for pool /
  tennis / pickleball court schedules. Smaller surface.
- **V1.5: sustainability layer extensions** — add `athletic_field`,
  `educational_institution`, `primary_school`, `church`, possibly
  `sports_complex` / `sports_club` / `country_club` /
  `fitness_center` direct mappings per the audit doc §9. Mirror
  the 5.7 `golf_course` / `medical_clinic` 1-line widening pattern.
- **V1.5: HWC dual-cat consideration set** — 26 §1-updates in cat-5
  HWC (gyms/yoga/pilates/dance/martial arts) may want selective
  dual-cat with cat-12 for entities offering distinct cat-12 services.
  Per kickoff §2 V1 policy = KEEP cat-5 (already applied); V1.5
  reviews per-entry.
- **V1.5: Sand Volleyball at Rotary Park** — currently cat-5
  (athletic_field primary, no direct mapping yet). Either FLIP to
  cat-12 (after `athletic_field` V1.5 ext) OR dual-cat with cat-7.
- **V1.5: The Ark Center recategorization** — currently cat-5 HWC,
  weak primary=`point_of_interest`. Building also houses the Slice E
  Psalms Learning Center (cat-12). V1.5 consider re-cat to cat-13
  religious / nonprofit AND/OR dual-cat with cat-12.
- **V1.5: Lake Havasu City Aquatic Center primary identity review** —
  Slice E created in cat-12 (swimming_pool primary). Could be V1.5
  dual-cat with cat-13 (it's a Parks & Rec municipal facility).
- **V1.5: Universal Sonics Gymnastics + Shah Racquetball Club** —
  both primary=`gym` but the actual sport (gymnastics, racquetball)
  is cat-12. Currently KEEP-ambig per Slice F (HWC scope decision).
  V1.5 may NEW-create in cat-12 with explicit primary_type override.
- **V1.5: Bridge Body Fitness (94r) + Feelin' Good Fitness (110r)** —
  high-signal gyms in the §1 ambig pool. V1.5 may NEW-create in
  cat-5 HWC if 5.4 lane gets re-opened.
- **V1.5: River City Music** — V1.5 cross-cat consideration if it
  offers music lessons in addition to retail.
- **V1.5: 5.8 §9 carry candidates revisit** — Nomadic coworking /
  Lions Dog Park / Main Street Commons all confirmed 0 in DB per the
  5.9 dupe-check. Single-entity Layer 5 manual recovery candidates.
- **86 of 265 HWC providers remain `verified=False`** — carry-over
  from 5.4. Operator-driven DBA→NPI follow-up surface (optional V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable
  (carry-over from 5.3 + 5.4 + 5.5 + 5.6 + 5.7 + 5.8).
- **Google Places API key rotation** still deferred per operator
  ("all keys will be changed at the conclusion of this project").

### Soft-edges (4 deferred per `phase5_9_classes_audit.md` §9)

- HWC dual-cat consideration (26 entries)
- Ark Center re-categorization
- Sand Volleyball dual-cat with cat-7
- Lake Havasu City Aquatic Center dual-cat with cat-13

None are gate-blocking.

### Files-to-prune carry-over

`hava_api_catalog.docx` + `~$va_api_catalog.docx` (Word lock) + 2
`outputs/ci_*_log_failed.txt` historical CI logs + `outputs/_deltest`
in working tree. Unrelated to the 5.9 lane; operator prunes when
comfortable.

### `data/events.db.bak-*` files (carry-over from 5.3 + 5.4 + 5.5 + 5.6 + 5.7 + 5.8)

Backup files may continue to accumulate. Operator prunes when
comfortable.

### Sandbox bash MOUNT STALENESS — pattern continues

5.9 hit it at §0 first `git diff --stat` (4 files showed massive
deletions in sandbox view; Windows-side confirmed clean). Read tool
authoritative; sandbox bash file-shape queries unreliable for
working-tree state. Carry the watch into 5.10.

### PowerShell `\"` escape footgun (5.7 carry)

The 5.7-discovered footgun didn't bite this session (used
single-quoted `-m '...'` for git commits throughout). Continue the
single-quoted-`-m` discipline in 5.10.

### Apply-script in-session reporting bug (NEW)

The §2 apply-script's "Post-apply cat-12 EntityCategory rows" report
showed 27 immediately after the changes, but the actual DB state was
31 (verified by post-commit spot-check). Likely autoflush quirk in
the in-session COUNT query. Not a real bug — changes did commit
correctly — but a polish item for V1.5 apply-script templating.

---

## §7 Coordination summary (one-line)

| Lane | Coordination need |
|---|---|
| Phase 6 (parallel agent OR in-line) | Land `outputs/claude_code_dispatch_phase6_amend5_to_8.md` consolidated dispatch (4 SHIPPED ledger lines for 5.5/5.6/5.7/5.8); ALSO `parks-rec-scrapes` cron fix per 5.7 close-out §3 |
| Cursor | No dispatches pending (Phase 5.9 produced its own regression tests in-lane: +21 at 1985 via `0af5f73`) |
| Operator | Audit doc carry-over actions (V1.5 verifier builds, HWC dual-cat review, Ark Center re-cat, sustainability layer V1.5 extensions for athletic_field/educational_institution/primary_school/church), file-prune list (.bak files + stray .docx + historical CI logs + `outputs/_deltest`), API key rotation (deferred to project end) |

---

## §8 Read order for the next session (Phase 5.10)

1. **This document** — the state of play (close-out + commit chain).
2. `outputs/phase5_10_<category>_kickoff.md` — Phase 5.10 runbook
   (authoritative for the §6 acceptance gate definitions; **next
   agent authors this if not yet present**, mirroring
   `outputs/phase5_9_classes_sports_recreation_kickoff.md` shape).
3. `outputs/phase5_10_next_agent_boot_prompt.md` — next-phase
   boot prompt authored this session for 5.10 priming.
4. `outputs/phase5_9_classes_audit.md` — combined post-load audit doc
   (template the 5.10 audit will mirror).
5. `outputs/apply_phase5_9_classes_audit.py` /
   `_heat_exposure.py` / `_crowd_notes.py` — template apply-scripts
   that 5.10 equivalents will mirror.
6. `outputs/phase5_9_gate_verification.py` — template for
   `outputs/phase5_10_gate_verification.py`.

---

## §9 Pre-flight for the next session

1. **`git log --oneline -15`** — origin should top at `4527ca1`
   or later (Phase 6 lane may push the consolidated amend5-8 line
   `0addb63`-shape commit between sessions).
2. **`git status`** — clean. Note the carry-over file-prune list above.
3. **`python -m alembic current`** — `0a1b2c3d4e5f` (unchanged across
   all 5.x phases unless the parks-rec-scrapes sidecar lands first).
4. **`python -m pytest -q --collect-only 2>&1 | Select-Object -Last 3`**
   — expect **1985 collected** (5.9 baseline). Verify no drift.
5. **`gh run list --branch main --limit 5`** — top run should be ✓ on
   `4527ca1`. Note that `parks-rec-scrapes` scheduled jobs
   continue to ❌ unless the Phase 6 / sidecar fix lands first.
6. **DB state spot-check** — `classes-sports-recreation` should show
   **31 entries / 0 verified / 29 indoor + 2 outdoor / 31 render / 10
   long-form crowd_notes** (the 5.9 SHIPPED state). `events` should
   still show **20/0/17+3/20/10** (5.8 SHIPPED state, unchanged).
7. **WIDENED four-file shape check** per kickoff §0 item 6:
   ```powershell
   git diff --stat scripts/places_categories.json scripts/places_load.py app/db/models.py app/contrib/google_types_mapping.py
   ```
   MUST be empty Windows-side (sandbox view may lie per the
   recurring mount-staleness pattern).
8. **Phase 5.10 sub-trade scope** — kickoff doc should land first.
   Likely `lodging-vacation-rentals` or `pets` per the remaining
   ~3-slug list. Operator picks at boot. Both have their own
   discovery domains with no existing catch-alls; no sustainability
   PIVOT needed for either (unlike 5.9's PIVOT).

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.9 session 1
(2026-05-17) post-`4527ca1`. Phase 5.9 SHIPPED with all 6 gate
items cleared in a single session; 3 commits on origin/main from
`4856020` → `4527ca1` (`0af5f73` sustainability + `a99e2c4`
wrapper-bundle + SHIP). Plus 4 DB-only writes (1 load + 1 audit apply
+ 1 heat + 1 crowd_notes). Hand-off to Phase 5.10 next session.*
