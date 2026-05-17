# Phase 5.11 -- Next-agent boot prompt

> Drop-in artifact for the operator to paste into a fresh Cowork session.
> Mirrors `outputs/phase5_10_next_agent_boot_prompt.md` shape
> (which booted the Phase 5.10 session that SHIPPED at `592ee74`
> 2026-05-17).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.10 session 1
> (2026-05-17) post-`592ee74` SHIP. Pastable as-is below the `---`
> line.

---

You're picking up Phase 5.11 (Pets, `pets`, cat-11) from scratch -- the
kickoff session. Phase 5.10 (Lodging & Vacation Rentals) SHIPPED on
origin at `592ee74` (2026-05-17) with all 6 gate items cleared and CI
green; SHA-cleanup at `accc06d`; Phase 5.11 kickoff doc pre-staged at
`7472b4a`. **Phase 5.11 is the LAST remaining Tier-1
category** -- 13 of 13 slugs after this. Top of `origin/main` is
`7472b4a` (or later if the Phase 6 lane shipped the
consolidated amend5-X dispatch between sessions). Find your own
context before doing anything else.

Working directory: `C:\Users\casey\projects\havasu-chat`.

1. `git log --oneline -10` to confirm `7472b4a` is top of main;
   the 5.10 -> 5.11-pre-stage chain is
   `ef8325d -> d597ef9 -> bf24e16 -> 592ee74 -> accc06d -> 7472b4a`
   on top of the 5.9 SHIP at `4527ca1` + 5.9 SHA-cleanup at `bc08bf6`.
2. Read these four docs end-to-end, in this order:
   a. `outputs/phase5_11_next_agent_boot_prompt.md` (THIS file -- the
      boot prompt for this session -- read FIRST; it sets the scope
      framing and locks the category pick at `pets`)
   b. `outputs/phase5_10_session_closeout.md` (the just-shipped 5.10
      state index -- carries the 4 lessons on dual-place_id observation
      patterns (HEAT Bar <-> Heat Hotel + Havasu Dunes Resort <->
      GetAways), the 2 cross-cat axis reframe (forecast didn't
      materialize -- 0 waterfront DUAL adds), the 5.9 reporting-bug
      fix validation (select(func.count()) + session.flush() works),
      and the sustainability-conditional cadence that landed
      Vanderpump-style edge case via NEW (None, "lodging") catch-all)
   c. `outputs/phase5_11_pets_kickoff.md` (the 5.11 runbook --
      authoritative for the 6 acceptance gate definitions + the
      single-domain clean scope (no Narrow scope decision needed --
      all 4 pets labels are in scope) + 1 sustainability conditional
      cadence + 3 Option C verifier resolution)
   d. `outputs/phase5_10_lodging_vacation_rentals_kickoff.md` (the
      5.10 runbook the 5.11 kickoff mirrors -- for shape continuity)

After you've read those, surface a short context-discovery report to
me: which docs you read, the carry-forward items you spotted, your
understanding of the 6 gates + the 1 scope decision + the 2 cross-cat
axes, and any ambiguities you want resolved. Then propose your 0
pre-flight execution plan + your 1 sustainability commit plan (or
note no sustainability commit needed if 1 load shows 0 unmapped).

Do not start any scrape (`places_discovery` / enrichment / load),
verification run, or DB-write apply-script before operator
confirmation. The 0 -> 1-sustainability (conditional) -> 1-load -> 2
audit -> 4 heat/crowd_notes -> ship cadence in 5.8 + 5.9 + 5.10
followed this pattern strictly. Continue the cadence: operator confirms
each step before dispatch.

PHASE 5.11 SCOPE -- KEY FRAMING:

  * **Category committed: `pets` (cat-11).** This is the LAST remaining
    Tier-1 slug. 13 of 13 Tier-1 categories after 5.11 ships.
    Operator's commit at 5.11 dispatch time.

  * **Discovery domain is SINGLE-domain.** Per
    `app/contrib/google_places_scraper.py:DISCOVERY_CATEGORY_TO_DOMAINS`,
    `"pets": frozenset({"pets"})` -- a clean single-domain mapping.
    Unlike 5.10's two-domain bundle (lodging + lake_recreation), 5.11
    has NO bundle collision with prior phases. The
    `_DISCOVERY_DOMAIN_FALLBACK` has NO `(None, "pets")` catch-all
    today.

  * **Narrow scope decision: NOT NEEDED -- single-domain CLEAN.** Per
    `scripts/places_categories.json:195-198`, the `pets` domain has
    exactly 4 labels (pet stores, dog groomers, dog boarding, dog
    trainers) -- all in scope. No bundle collision; no deferred
    labels. Use `python -m scripts.places_discovery --category pets`
    directly (no narrow-label-filter wrapper needed). Note: vet
    clinics are NOT in 5.11 scope (no `veterinarians` label); 5.4 HWC
    absorbed them via `medical_clinic` primary type.

  * **Sustainability layer PIVOT is CONDITIONAL, not pre-required.**
    Mirrors 5.10's conditional cadence:
      * `veterinary_care` direct mapping -> cat-11 (pre-Phase-5)
      * `pet_store` direct mapping -> cat-11 (pre-Phase-5)
      * Google's actual pets primary_types (`veterinary_care`,
        `pet_store`, possibly `dog_groomer`, `pet_boarding`,
        `dog_trainer`) -- the first two are mapped; the latter three
        may not be.
    **Decision deferred to 1 load output:** check `category_id
    unmapped (operator queue)` count. If 0, no sustainability commit
    needed. If non-zero, author per kickoff 1 Option A pattern
    (e.g., add `dog_groomer` / `pet_boarding` / `dog_trainer` direct
    mappings + new `(None, "pets") -> "pets"` catch-all).

  * **Cross-cat overlap expected -- minimal.** Pets is a relatively
    isolated domain in LHC. Some potential cross-cat axes:
      - cat-5 health-wellness-care (if a HWC entity also offers pet
        services -- unlikely but possible)
      - cat-1 eat-drink (pet-friendly restaurants -- decorative
        cross-cat, probably not gate-relevant)
      - cat-7 outdoors-parks-trails (dog parks already in cat-7 via
        `dog_park` direct map; pets cat-11 won't include those by
        primary identity)
    Expected: 0-3 cross-cat DUAL/FLIP candidates.

WORKING PATTERNS TO INTERNALIZE FROM THE 5.10 CLOSE-OUT:

  * **Pass dicts directly to JSON-typed SQLAlchemy columns**
    (`Entity.crowd_notes`). Do NOT `json.dumps()` first.
  * **F401 + F541 + I001 ruff footguns.** `# noqa: E402` silences
    E402 only.
  * **PowerShell `\"` escape footgun.** Use single-quoted `-m '...'`
    flags for git commit messages when the body contains `"` or
    `/` characters.
  * **5.9 cp1252 encoding gotcha INTERNALIZED.** Avoid all non-ASCII
    in script stdout; route Unicode to JSON files instead (UTF-8 by
    default). 5.10 produced ~10 new script artifacts all
    pure-ASCII-clean.
  * **Sandbox bash mount-staleness -- pattern continues**
    (5.5/5.6/5.7/5.8/5.9/5.10 all hit it). Read tool is
    authoritative; sandbox bash file-shape queries are unreliable for
    ANY working-tree state / git-index / DB-inspection query. Default
    to Read + `git show HEAD:` for sandbox text inspection;
    Windows-side `python` + `git status` / `git diff` for working-
    tree state + DB query.
  * **Sandbox bash git-index gotcha** -- use `git rev-parse` / `git
    show HEAD:` for index-free reads.
  * **DB-write apply-scripts: stop the FastAPI dev server if running**
    (`events.db` lock).
  * **`Provider.google_review_snippets` is its OWN COLUMN** on
    Provider. Drafts for top-10 long-form `crowd_notes` source from
    this column.
  * **`scripts/places_categories.json` LOCAL CORRUPTION RECURRENCE
    PATTERN** -- recurred 4x across 5.4 / 5.5 / 5.6 / 5.7-boot. The
    5.7 / 5.8 / 5.9 / 5.10 sessions found the four-file shape check
    clean. Continue the four-file shape check in 5.11 0.
  * **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a
    domain-wide catch-all** at `places_load.py:368-371`. 5.10 added
    `(None, "lodging") -> "lodging-vacation-rentals"` as NEW at
    `bf24e16`. 5.11 may add `(None, "pets") -> "pets"` as NEW if 1
    load reveals unmapped.
  * **`entity_type` mixed (place + commercial)** -- gate-1 query MUST
    use the `(e.entity_type != 'commercial' OR provider-visible)`
    OR-clause shape from
    `outputs/phase5_10_gate_verification.py`. (For 5.11 all entries
    expected `commercial`; OR-clause is still required for
    route-render shape.)
  * **CI flakiness on intermediate commits** -- 5.5 / 5.7-session-1 /
    5.8 all saw the same pattern; 5.9 / 5.10 didn't hit it. Try `gh
    run rerun <ID>` before shipping a fix commit.
  * **DB-verify the "existing entity in cat-X" premise BEFORE
    finalizing audit doc** (5.9 + 5.10 prospective-catch lesson).
    Author `outputs/phase5_11_dupe_check.py` EARLY in 2 audit. For
    5.11 specifically: verify any pet-business co-located cat-5 HWC
    entities (e.g., a veterinary clinic that might already be in HWC
    as a "medical_clinic" -- unlikely but worth confirming).
  * **5.10 same-business dual-place_id patterns** (HEAT Bar / Heat
    Hotel + Havasu Dunes / GetAways) -- watch for similar Google
    Places dual-listings in 5.11 (e.g., a veterinary clinic with a
    separate place_id for its grooming arm).
  * **5.9 2 in-session reporting bug FIXED in 5.10 apply-script**
    (`select(func.count())` + `session.flush()` before COUNT). Mirror
    the fix in 5.11 apply-script.

AFTER YOU READ THE FOUR DOCS:

  1. **Run 0 pre-flight items** (git log + status + alembic + pytest
     collect + diagnose + widened four-file shape check + CI status
     + Google Places key + DB spot-check including the 73 baseline
     cat-10 entries from 5.10 + 31 baseline cat-12 from 5.9 + 20
     baseline cat-2 from 5.8 + ~5-10 baseline cat-11 entries from
     pre-Phase-5 `veterinary_care` + `pet_store` direct mappings).
  2. **Surface 0 status to the operator.** If
     `places_categories.json` corruption has recurred (8th+
     recurrence forecast), surface immediately + ask for restore
     before proceeding.
  3. **1 Layer 1 dispatch** -- author the Narrow-scope wrapper
     `outputs/phase5_11_narrow_label_filter.py` first (mirror
     `outputs/phase5_10_narrow_label_filter.py` with the pets labels).
     Then Google Places scrape via the wrapper + enrichment +
     places_load dry-run + places_load.
  4. **1 sustainability commit (CONDITIONAL)** -- if 1 load shows
     `category_id unmapped (operator queue): 0`, NO sustainability
     commit needed. If non-zero, mirror `bf24e16` (Phase 5.10
     sustainability) surgical-fix shape exactly: single focused
     `fix(scripts)` commit adding the unmapped primary_types as
     direct mappings + 1 new `(None, "pets")` catch-all + regression
     tests in `tests/test_phase5_11_places_load_resolver.py`.
  5. **2 audit cycle** -- author `outputs/phase5_11_dupe_check.py`
     EARLY (before finalizing audit doc) per the 5.9 + 5.10
     prospective-catch discipline. Then mirror the 5.10 2 cadence:
     dump script -> operator runs -> audit doc + apply-script ->
     operator dispatches. Special-audit axes for 5.11: TBD per kickoff
     (likely cat-5 HWC primary for vet/medical-clinic overlap; cat-7
     outdoors-parks-trails secondary for dog park overlap).
  6. **4 heat_exposure + crowd_notes** -- apply-scripts mirroring
     `apply_phase5_10_lodging_*.py`. heat_exposure default `indoor`
     for vet clinics / pet stores / groomers / pet daycare;
     **NEW for 5.11:** consider `outdoor` overrides for pet
     boarding kennels with outdoor runs + dog park-adjacent services.
  7. **Gate verification + SHIP commit** -- `outputs/phase5_11_gate_
     verification.py` mirroring `phase5_10_gate_verification.py`
     shape; SHIP commit bundles audit + apply-scripts + gate
     verification + session close-out. **No 5.12 boot prompt needed
     -- 5.11 is the LAST Tier-1 category.** Instead, the close-out
     documents V1 acceptance and hands off to V1.5 / Phase 6 lanes.

**Possibly relevant for THIS session specifically:**

- The `parks-rec-scrapes` scheduled CI workflow is STILL failing on
  cron triggers -- root cause identified in Phase 5.7 4.5 sidebar
  (Postgres FK constraint violation in `scripts/parks_rec_prune.py`),
  handed off to Phase 6 / sidecar lane. **Not in 5.11 scope** -- do
  not investigate unless the operator explicitly asks.
- The **Phase 6 amend backlog (potentially 5/6/7/8/9/10 = 6 deep) at
  `outputs/claude_code_dispatch_phase6_amend5_to_8.md`** is ready for
  Claude Code parallel agent dispatch. Operator may want to extend to
  amend5-11 (adding the 5.11 SHIP line) at 5.11 SHIP time. Coordinate
  with 5.11 lane -- file-scope disjoint with `scripts/` + `outputs/`
  + `app/` + `tests/`. May dispatch in parallel with 5.11 0
  pre-flight.
- **5.11 is the LAST 5.x Tier-1 category lane.** V1 acceptance gate
  (Phase 6) becomes the next major milestone. The 5.11 SHIP commit
  should reference V1 readiness in its close-out doc.

When you're confident you've understood the four docs end-to-end,
propose your 0 pre-flight execution plan to the operator, then your
1 Layer 1 dispatch plan + conditional sustainability layer plan, and
wait for go-ahead.
