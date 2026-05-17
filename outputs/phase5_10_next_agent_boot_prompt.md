# Phase 5.10 — Next-agent boot prompt

> Drop-in artifact for the operator to paste into a fresh Cowork session.
> Mirrors `outputs/phase5_9_next_agent_boot_prompt.md` shape
> (which booted the Phase 5.9 session that SHIPPED at `<SHIP-COMMIT>`
> 2026-05-17).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.9 session 1
> (2026-05-17) post-`<SHIP-COMMIT>` SHIP. Pastable as-is below the
> `---` line.

---

You're picking up Phase 5.10 from scratch. Nothing shipped yet for 5.10 —
this is the kickoff session. Phase 5.9 (Classes, Sports & Recreation)
SHIPPED on origin at `<SHIP-COMMIT>` (2026-05-17) with all 6 gate items
cleared and CI green. Top of origin/main is `<SHIP-COMMIT>` (or later
if the Phase 6 lane shipped the consolidated amend5-8 dispatch between
sessions — check `git log -3` first).

Working directory: `C:\Users\casey\projects\havasu-chat` (Windows-side
operator env); sandbox bash mounts under
`/sessions/.../mnt/havasu-chat/`.

READ THESE THREE DOCUMENTS END-TO-END BEFORE DOING ANYTHING ELSE, IN
THIS ORDER:

  1. `outputs/phase5_9_session_closeout.md` — the close-out for the
     prior Phase 5.9 session. §1 has the 3-commit chain (`0af5f73`
     sustainability → `a99e2c4` wrapper-bundle → `<SHIP-COMMIT>`
     SHIP). §3 documents the §1 sustainability commit (Option A — 9
     direct `_PRIMARY_TYPE_MAP` entries for cat-12 primary_types + 1
     new childcare_education catch-all). §4 documents the §2 audit
     Slice plan (B/C/D/E + KEEPs). §6 has the carry-forward list. §9
     has the pre-flight scaffold. **The Lake Havasu City Aquatic
     Center reclassification mid-audit (kickoff §2 framed as FLIP →
     dupe-check confirmed NOT in DB → reclassified as Slice E NEW-
     create) is the audit-trail lesson for 5.10** — DB-verify the
     "existing entity in cat-X" premise before authoring cross-cat
     moves. Caught prospectively in 5.9 via
     `outputs/phase5_9_dupe_check.py` BEFORE the audit doc was
     finalized (vs 5.8 Slice B-1 which caught it mid-apply); apply
     the same prospective pattern in 5.10.
  2. `outputs/phase5_10_<category>_kickoff.md` — THE runbook for
     Phase 5.10. **The category pick is operator's** — either
     `lodging-vacation-rentals` or `pets` per the remaining 5.x slug
     list. **Author this kickoff if not yet present**, mirroring
     `outputs/phase5_9_classes_sports_recreation_kickoff.md` shape
     with 5.10-specific overrides.
  3. `outputs/phase5_9_classes_sports_recreation_kickoff.md` — the
     previous phase's runbook. Reads as the structural template the
     5.10 kickoff mirrors. Particularly read §1 (Narrow scope rationale
     + sustainability layer PIVOT shape if applicable), §3 (verifier
     surface — Option C pattern that 5.10 likely repeats), and §4
     (operator-curated rubric).

PHASE 5.10 SCOPE — KEY FRAMING:

  • **Category selection — operator picks at session start.** The
    remaining ~3 Tier-1 slugs (from `scripts/places_categories.json` +
    `master_build_plan.md`) are likely:
      - **`lodging-vacation-rentals` (cat-10)** — hotels, motels,
        resorts, vacation rentals, B&B. LHC has significant tourism;
        moderate density.
      - **`pets` (cat-11)** — pet stores, dog groomers, dog boarding,
        dog trainers. Smaller LHC density; likely a faster lane.
      - **`events` is SHIPPED at 5.8 (`2808146`).**
      - **`classes-sports-recreation` is SHIPPED at 5.9
        (`<SHIP-COMMIT>`).**
    Operator picks at kickoff; the boot prompt assumes one of the
    above.

  • **Discovery domain depends on category.** Per
    `app/contrib/google_places_scraper.py:DISCOVERY_CATEGORY_TO_DOMAINS`:
      - `lodging-vacation-rentals` → `frozenset({"lodging"})` —
        single-domain mapping.
      - `pets` → `frozenset({"pets"})` — single-domain mapping.

  • **Sustainability layer PIVOT NOT NEEDED.** Unlike 5.9 (which had
    to PIVOT around the 5.4 `(None, "fitness_sports") → HWC`
    catch-all), both `lodging-vacation-rentals` and `pets` have their
    own discovery domains with no existing catch-alls that would
    mis-route. Sustainability layer extensions likely needed if
    Google emits primary_types not already in `_PRIMARY_TYPE_MAP`
    (e.g., `dog_groomer`, `dog_boarding`, `dog_trainer` are likely
    NEW additions for pets; `lodging` + `rv_park` already present
    for lodging-vacation-rentals).

  • **Cross-cat overlap expected.** If picking
    `lodging-vacation-rentals`, expect overlap with cat-2 events
    (hotels host events — see 5.8 kickoff §2). If picking `pets`,
    expect overlap with cat-5 HWC (veterinarians may be cross-listed)
    and cat-7 outdoors-parks-trails (Lions Dog Park is a 5.8 V1.5
    carry candidate; 5.9 dupe-check confirmed it's not in DB).

WORKING PATTERNS TO INTERNALIZE FROM THE 5.9 CLOSE-OUT:

  • **Pass dicts directly to JSON-typed SQLAlchemy columns**
    (`Entity.crowd_notes`). Do NOT `json.dumps()` first. (5.3 `f35d5e4`
    bug write-up — 5.4 through 5.9 all avoided it.)
  • **F401 + F541 + I001 ruff footguns.** `# noqa: E402` silences
    E402 only. F401 (unused imports), F541 (`f"..."` with no
    placeholders), and **I001 (un-sorted/inline imports)** all still
    fail ruff. 5.8 hit I001 once on inline imports inside `main()` —
    5.9 internalized: all imports at top of file.
  • **PowerShell `\"` escape footgun** (5.7-discovered, 5.8-avoided,
    5.9-avoided). Use single-quoted `-m '...'` flags for git commit
    messages when the body contains `"` or `/` characters; PS single
    quotes are literal (no interpolation, no escaping).
  • **PowerShell cp1252 encoding gotcha (NEW 5.9):** print statements
    in Python scripts that include `→` (U+2192) or other characters
    outside cp1252 will CRASH on PowerShell pipe. Use ASCII `->` and
    `--` instead. The `§` character (U+00A7) and `—` em-dash (U+2014)
    will mojibake but NOT crash. Cleaner: avoid all non-ASCII in
    script stdout; route Unicode to JSON files instead (UTF-8 by
    default).
  • **Sandbox bash mount-staleness — pattern continues** (5.5/5.6/
    5.7/5.8/**5.9 hit it at §0 first git diff**). Read tool is
    authoritative; sandbox bash file-shape queries are unreliable for
    ANY working-tree state / git-index / DB-inspection query. Default
    to Read + `git show HEAD:` for sandbox text inspection;
    Windows-side `python` + `git status` / `git diff` for working-
    tree state + DB query.
  • **Sandbox bash git-index gotcha** — use `git rev-parse` / `git
    show HEAD:` for index-free reads. Operator runs index-dependent
    ops (`git status` / `git commit` / `git push`) Windows-side via
    PowerShell.
  • **DB-write apply-scripts: stop the FastAPI dev server if running**
    (`events.db` lock).
  • **`Provider.google_review_snippets` is its OWN COLUMN** on
    Provider (per `app/db/models.py:84`, populated by
    `scripts/places_load.py` from the scraper's `review_snippets`
    emission). NOT inside `attributes.google_review_snippets`.
    Drafts for top-10 long-form `crowd_notes` source from this
    column. 5.9 top-10 had 100% snippet coverage on 9 of 10 (Hilltop
    Learning Center at 3); 5.10 may vary by category.
  • **`scripts/places_categories.json` LOCAL CORRUPTION RECURRENCE
    PATTERN** — recurred 4× across 5.4 / 5.5 / 5.6 / 5.7-boot. The
    5.7-session-2 5th-recurrence forecast did NOT materialize, nor
    did 5.8's 6th nor 5.9's 7th. Continue the four-file shape check
    in 5.10 §0.
  • **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a domain-wide
    catch-all** at `places_load.py:368-371`. 5.9 added `(None,
    "childcare_education") → "classes-sports-recreation"`. If 5.10
    picks pets, may add `(None, "pets") → "pets"` as a safety net
    (no existing pets catch-all today).
  • **`entity_type` mixed (place + commercial)** — gate-1 query MUST
    use the `(e.entity_type != 'commercial' OR provider-visible)`
    OR-clause shape from `outputs/phase5_2_gate_verification.py` /
    `outputs/phase5_7/8/9_gate_verification.py`. For 5.10
    lodging-vacation-rentals, all entries likely `commercial`; for
    pets, mostly `commercial` (pet_store / veterinary_care /
    dog_groomer all commercial).
  • **CI flakiness on intermediate commits** — 5.5 / 5.7-session-1 /
    5.8 all saw the same pattern (one ✓ + one ❌ on the same commit
    ID, short elapsed time = runner-orchestration flake not code).
    5.9 didn't hit it. Try `gh run rerun <ID>` before shipping a fix
    commit. Final tree-state CI green is the ship-readiness signal.
  • **DB-verify the "existing entity in cat-X" premise** before
    authoring cross-cat moves in §2 apply-scripts. 5.8 caught it
    mid-apply (Slice B-1 Lake Havasu Museum of History reframe to
    Slice A NEW-create); 5.9 caught it prospectively via
    `outputs/phase5_9_dupe_check.py` BEFORE finalizing the audit
    doc (Lake Havasu City Aquatic Center reframe from FLIP to NEW-
    create). Pattern for 5.10: author a `phase5_10_dupe_check.py`
    early in §2 audit to verify all cross-cat move premises.
  • **5.9 §2 apply-script in-session reporting bug (NEW)** — the
    "Post-apply cat-12 EntityCategory rows" count showed 27
    immediately after the changes, but actual DB state was 31
    (verified by post-commit spot-check). Likely autoflush quirk in
    the in-session COUNT query. The changes DO commit correctly; the
    in-session report is just stale. For 5.10, either add an explicit
    `session.flush()` before the COUNT query, OR use
    `session.expire_all()` + re-query, OR (simplest) just use
    `select(func.count())` instead of `.all()` length.

AFTER YOU READ THE THREE DOCS:

  1. **Author the kickoff doc** —
     `outputs/phase5_10_<category>_kickoff.md` — mirroring the 5.9
     kickoff shape with 5.10 overrides. Operator picks category at
     start.
  2. **Run §0 pre-flight items** (git log + status + alembic +
     pytest collect + diagnose + widened four-file shape check + CI
     status + Google Places key + DB spot-check including the 31
     baseline cat-12 entries from 5.9 + 20 baseline cat-2 from 5.8).
  3. **Surface §0 status to the operator.** If
     `places_categories.json` corruption has recurred (8th+
     recurrence forecast), surface immediately + ask for restore
     before proceeding.
  4. **§1 sustainability commit** (if needed — likely smaller surface
     than 5.9 since no PIVOT). Mirror `0af5f73`'s shape: single
     focused `fix(scripts)` commit with regression tests in
     `tests/test_phase5_10_places_load_resolver.py`. Land BEFORE
     the §1 Layer 1 dispatch (sustainability-first pattern from
     5.5 / 5.6 / 5.7 / 5.8 / 5.9).
  5. **§1 Layer 1 dispatch** — Google Places scrape. May not need a
     Narrow-scope wrapper if all labels in cat-10 / cat-11's domain
     are in-scope (unlike 5.7/5.8/5.9 which all had Narrow scopes due
     to cross-phase absorption).
  6. **§2 audit cycle** — mirror the 5.9 §2 cadence: dump script →
     operator runs → dupe-check script → operator runs → audit doc +
     apply-script → operator dispatches. Special-audit axes for
     5.10 depend on category.
  7. **§4 heat_exposure + crowd_notes** — apply-scripts mirroring
     `apply_phase5_9_classes_*.py`. heat_exposure default TBD in
     kickoff §4 (cat-10 lodging is mostly indoor with some
     pool/outdoor amenities; cat-11 pets are mostly indoor).
  8. **Gate verification + SHIP commit** — `outputs/phase5_10_gate_
     verification.py` mirroring `phase5_9_gate_verification.py`
     shape; SHIP commit bundles audit + apply-scripts + gate
     verification + session close-out + Phase 5.11 boot prompt.

DO NOT START ANY SCRAPE (`places_discovery` / enrichment / load),
VERIFICATION RUN, OR DB-WRITE APPLY-SCRIPT BEFORE OPERATOR
CONFIRMATION. The 5.9 §0 → §1 → §2 → §4 → ship cadence followed this
pattern strictly. Continue the cadence: §0 status surface → operator
confirms → sustainability fix (if needed) → operator review →
§1 dispatch → §2 audit → operator review + dispatch → §4 → operator
review + dispatch → ship sequence.

🚨 **Possibly relevant for THIS session specifically:** the
`parks-rec-scrapes` scheduled CI workflow is STILL ❌ on cron
triggers — root cause identified in Phase 5.7 §4.5 sidebar (Postgres
FK constraint violation in `scripts/parks_rec_prune.py`), handed off
to Phase 6 / sidecar lane. **Not in 5.10 scope** — do not investigate
unless the operator explicitly asks.

Also possibly relevant: the **4-deep Phase 6 amend backlog
(5.5/5.6/5.7/5.8) consolidated at
`outputs/claude_code_dispatch_phase6_amend5_to_8.md`** is ready for
Claude Code parallel agent dispatch. Coordinate with 5.10 lane —
file-scope disjoint (Phase 6 amend touches `docs/STATE.md` +
`docs/maintainability/master_build_plan.md`; 5.10 touches
`scripts/` + `outputs/` + `app/` + `tests/`). The operator may
dispatch it in parallel with 5.10 §0 pre-flight.

When you're confident you've understood the three docs end-to-end,
propose your §0 pre-flight execution plan to the operator, then your
kickoff-authoring plan + §1 sustainability layer plan (or note no
sustainability commit needed), and wait for go-ahead.
