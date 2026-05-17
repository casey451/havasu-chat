# Phase 5.9 — Next-agent boot prompt

> Drop-in artifact for the operator to paste into a fresh Cowork session.
> Mirrors `outputs/phase5_8_events_next_agent_boot_prompt.md` shape
> (which booted the Phase 5.8 session that SHIPPED at `2808146`
> 2026-05-17).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.8 session 1
> (2026-05-17) post-`2808146` SHIP. Pastable as-is below the
> `---` line.

---

You're picking up Phase 5.9 from scratch. Nothing shipped yet for 5.9 —
this is the kickoff session. Phase 5.8 (Events) SHIPPED on origin at
`2808146` (2026-05-17) with all 6 gate items cleared and CI
green. Top of origin/main is `2808146` (or later if the Phase 6
lane shipped Amendment 8 between sessions — check `git log -3` first).

Working directory: `C:\Users\casey\projects\havasu-chat` (Windows-side
operator env); sandbox bash mounts under
`/sessions/.../mnt/havasu-chat/`.

READ THESE THREE DOCUMENTS END-TO-END BEFORE DOING ANYTHING ELSE, IN
THIS ORDER:

  1. `outputs/phase5_8_session_closeout.md` — the close-out for the
     prior Phase 5.8 session. §1 has the 3-commit chain (`0b426e1`
     sustainability → `f139be7` narrow-scope wrapper → `2808146`
     SHIP). §3 documents the §1 sustainability commit (Option A — 7
     direct `_PRIMARY_TYPE_MAP` entries for events primary_types).
     §4 documents the substantial NEW-create surface in §2 audit (16
     Slice A NEW entity creates + 1 cross-cat move + 1 DRAFT, vs
     5.7's FLIPs-out-of-cat-7 surface). §6 has the carry-forward
     list. §9 has the pre-flight scaffold. **The Lake Havasu Museum
     of History reclassification mid-apply (Slice B-1 → Slice A) is
     the audit-trail lesson for 5.9** — always DB-verify the
     "existing entity in cat-X" premise before authoring cross-cat
     moves; the kickoff framing may misread the actual DB state.
  2. `outputs/phase5_9_classes_sports_recreation_kickoff.md` — THE
     runbook for Phase 5.9. **Pre-staged by Phase 5.8 session 1**
     (mirrors the `8dfa2a2` precedent where 5.7 session 2 pre-staged
     the 5.8 kickoff). The category pick is `classes-sports-recreation`
     (cat-12) per the 5.8-session operator decision; the kickoff
     commits to that scope and lays out the §1 sustainability PIVOT
     (Option A — direct `_PRIMARY_TYPE_MAP` entries for the 9
     in-scope primary_types + a new `(None, "childcare_education")`
     catch-all). If the operator wants to switch to `pets` or
     `lodging-vacation-rentals` at boot, author a fresh kickoff and
     archive this one.
  3. `outputs/phase5_8_events_kickoff.md` — the previous phase's
     runbook. Reads as the structural template the 5.9 kickoff
     mirrors. Particularly read §1 (the Narrow scope rationale +
     sustainability layer PIVOT shape — Option A pattern for direct
     `_PRIMARY_TYPE_MAP` entries), §3 (verifier surface — Option C
     pattern that 5.9 may repeat), and §4 (operator-curated rubric).

PHASE 5.9 SCOPE — KEY FRAMING:

  • **Category selection — operator picks at session start.** The
    remaining Tier-1 slugs (from `scripts/places_categories.json` +
    `master_build_plan.md`) are likely:
      - **`classes-sports-recreation` (cat-12)** — gyms, yoga,
        pilates, crossfit, martial arts, dance studios, swimming
        pools, tennis courts, pickleball — i.e., the deferred 11
        `fitness_sports` labels from 5.7's Narrow scope decision.
        Plus the 5.8 §9 carry-overs (Lake Havasu City Aquatic
        Center, Nomadic coworking, etc.) and 5.7 V1.5 dual-cat
        candidates (SARA Disc Golf, Motocross Park, Ofd Racing,
        Thompson Bay Beach, Sportsman's Club).
      - **`pets` (cat-11)** — pet stores, dog groomers, dog
        boarding, dog trainers. Much smaller LHC density than
        classes-sports-recreation; likely a faster lane.
      - **`lodging-vacation-rentals` (cat-10)** — resorts, vacation
        rentals, B&B. Bigger than pets, smaller than
        classes-sports-recreation.
    Operator picks at kickoff; the boot prompt assumes one of the
    above.

  • **Discovery domain depends on category.** Per
    `app/contrib/google_places_scraper.py:DISCOVERY_CATEGORY_TO_DOMAINS`:
      - `classes-sports-recreation` → `frozenset({"fitness_sports"})` —
        single-domain mapping (mirrors 5.8's events shape).
      - `pets` → `frozenset({"pets"})` — single-domain mapping.
      - `lodging-vacation-rentals` → `frozenset({"lodging"})` —
        single-domain mapping.

  • **Sustainability layer PIVOT required IF picking classes-sports-
    recreation.** The 5.4 `fc51940` commit added
    `(None, "fitness_sports") → "health-wellness-care"` as a
    domain-wide catch-all (Phase 5.4 HWC absorbed gyms/yoga/pilates).
    For 5.9 cat-12 this routes the wrong way — every gym/yoga/pilates
    primary_type would land in HWC instead of cat-12. Three options
    (same shape as 5.8's PIVOT):
      **(A — recommended)** Add direct `_PRIMARY_TYPE_MAP` entries
      for the expected cat-12 primary_types (`gym`, `yoga_studio`,
      `pilates_studio`, `crossfit_gym`, `martial_arts_school`,
      `dance_studio`, `swimming_pool`, `tennis_court`, `pickleball_
      court`, etc.). Direct mappings beat the catch-all per resolver
      order, so the HWC-overlap entries stay in HWC while new
      cat-12 entries route correctly.
      **(B)** Re-route the catch-all from HWC to cat-12; add explicit
      cat-5 mappings for the medical/wellness primary_types.
      **(C — hybrid)** Both A + B.
    **Recommended: Option A.** Minimal diff, no need to revert 5.4's
    catch-all (which is correct for 5.4's scope).

  • **Sustainability layer PIVOT NOT NEEDED if picking pets or
    lodging-vacation-rentals** — both have their own discovery
    domains with no existing catch-alls that would mis-route.

  • **Cross-cat overlap expected.** If picking
    classes-sports-recreation, expect substantial overlap with the
    HWC entities loaded in 5.4 (gyms primarily). 5.4 §2 forecast
    "0 real misroutes" held — most reconciler ambig-skips were
    benign. 5.9 §2 audit will need a primary axis on cat-5/cat-12.

WORKING PATTERNS TO INTERNALIZE FROM THE 5.8 CLOSE-OUT:

  • **Pass dicts directly to JSON-typed SQLAlchemy columns**
    (`Entity.crowd_notes`). Do NOT `json.dumps()` first. (5.3 `f35d5e4`
    bug write-up — 5.4 through 5.8 all avoided it by following this
    rule.)
  • **F401 + F541 + I001 ruff footguns.** `# noqa: E402` silences
    E402 only. F401 (unused imports), F541 (`f"..."` with no
    placeholders), and **I001 (un-sorted/inline imports)** all still
    fail ruff. 5.8 hit I001 once on inline imports inside `main()` —
    fix is to move them to the top of the file. Watch for inline
    `from x import y` blocks in apply-scripts.
  • **PowerShell `\"` escape footgun** (5.7-discovered, 5.8-avoided).
    Use single-quoted `-m '...'` flags for git commit messages when
    the body contains `"` or `/` characters; PS single quotes are
    literal (no interpolation, no escaping).
  • **Sandbox bash mount-staleness** — pattern continues. 5.8 hit it
    twice (post-Edit `wc -l` on fresh file showed stale count;
    sandbox didn't see the up-to-date file shape until Read tool
    refresh). The Read tool is authoritative; sandbox bash is
    unreliable for ANY file-shape / git-state / DB-inspection query.
    Default to Read + `git show HEAD:` for sandbox text inspection;
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
    column. 5.8 top-10 had 100% snippet coverage (5 each); 5.9 may
    vary by category.
  • **`scripts/places_categories.json` LOCAL CORRUPTION RECURRENCE
    PATTERN** — recurred 4× across 5.4 / 5.5 / 5.6 / 5.7-boot. The
    5.7-session-2 5th-recurrence forecast did NOT materialize. The
    5.8 4-file shape check at §0 was empty. Continue the four-file
    shape check in 5.9.
  • **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a
    domain-wide catch-all** at `places_load.py:368-371`, NOT a
    `primary_type=None` filter. 5.6 routed 27 edge-case providers
    via the `(None, "retail")` catch-all; 5.7 routed ~5 via `(None,
    "entertainment_attractions")`; 5.8's direct `_PRIMARY_TYPE_MAP`
    entries beat the catch-all per resolver order (so cat-7 routing
    stays correct for unmapped types while cat-2 entries land
    directly).
  • **`entity_type` mixed (place + commercial)** — gate-1 query MUST
    use the `(e.entity_type != 'commercial' OR provider-visible)`
    OR-clause shape from `outputs/phase5_2_gate_verification.py` /
    `outputs/phase5_7_gate_verification.py` /
    `outputs/phase5_8_gate_verification.py`. (Phase 5.8's 6
    place-typed + 14 commercial-typed entries are all gate-1
    counted.)
  • **CI flakiness on intermediate commits** — 5.5 / 5.7-session-1
    both saw the same pattern (one ✓ + one ❌ on the same commit ID,
    short elapsed time = runner-orchestration flake not code).
    Try `gh run rerun <ID>` before shipping a fix commit. Final
    tree-state CI green is the ship-readiness signal.
  • **DB-verify the "existing entity in cat-X" premise** before
    authoring cross-cat moves in §2 apply-scripts. 5.8 hit this mid-
    apply: the audit doc's Slice B-1 assumed Lake Havasu Museum of
    History was in cat-6 (per kickoff §2 framing), but DB query
    confirmed no such entity existed — the kickoff framing was a
    misreading of 5.7 close-out §4's "0 flips needed" (which meant
    the museum candidate was KEPT-ambig, not flipped to cat-6).
    Pattern: query DB for `Entity.name LIKE '%<keyword>%'` before
    authoring cross-cat moves.

AFTER YOU READ THE THREE DOCS:

  1. **Author the kickoff doc** —
     `outputs/phase5_9_<category>_kickoff.md` — mirroring the 5.8
     kickoff shape with 5.9 overrides. Operator picks category at
     start. If `classes-sports-recreation` picked, the §1 PIVOT
     plan (Option A direct mappings for cat-12 primary_types) is
     load-bearing. If `pets` or `lodging-vacation-rentals` picked,
     no PIVOT needed.
  2. **Run §0 pre-flight items** (git log + status + alembic +
     pytest collect + diagnose + widened four-file shape check + CI
     status + Google Places key + DB spot-check including the 20
     baseline cat-2 entries from 5.8).
  3. **Surface §0 status to the operator.** If
     `places_categories.json` corruption has recurred (5th+
     recurrence forecast), surface immediately + ask for restore
     before proceeding.
  4. **§1 sustainability commit** — extend `_PRIMARY_TYPE_MAP`
     and/or `_DISCOVERY_DOMAIN_FALLBACK` per the §1 PIVOT plan in
     the kickoff (if needed for cat-12; not needed for pets /
     lodging). Mirror `0b426e1` (Phase 5.8 sustainability commit)
     surgical-fix shape exactly: single focused `fix(scripts)`
     commit with regression tests in
     `tests/test_phase5_9_places_load_resolver.py`. Land BEFORE
     the §1 Layer 1 dispatch (sustainability-first pattern from
     5.5 / 5.6 / 5.7 / 5.8).
  5. **§1 Layer 1 dispatch** — Google Places scrape with the in-
     scope labels (via Narrow scope wrapper if needed —
     `outputs/phase5_9_narrow_label_filter.py` mirrors `phase5_8_`).
  6. **§2 audit cycle** — mirror the 5.8 §2 cadence: dump script →
     operator runs → audit doc + apply-script → operator dispatches.
     Special-audit axes for 5.9 depend on category — for cat-12 the
     primary axis is cat-5 HWC overlap.
  7. **§4 heat_exposure + crowd_notes** — apply-scripts mirroring
     `apply_phase5_8_events_*.py`. heat_exposure default TBD in
     kickoff §4 (cat-12 splits indoor/outdoor; cat-11 pets are
     mostly indoor; cat-10 lodging is mostly indoor with some
     pool/outdoor amenities).
  8. **Gate verification + SHIP commit** — `outputs/phase5_9_gate_
     verification.py` mirroring `phase5_8_gate_verification.py`
     shape; SHIP commit bundles audit + apply-scripts + gate
     verification + session close-out + Phase 5.10 boot prompt.

DO NOT START ANY SCRAPE (`places_discovery` / enrichment / load),
VERIFICATION RUN, OR DB-WRITE APPLY-SCRIPT BEFORE OPERATOR
CONFIRMATION. The 5.8 §0 → §1 → §2 → §4 → ship cadence followed this
pattern strictly and caught the Slice B-1 misclassification mid-apply
before it became a gate-blocker. Continue the cadence: §0 status
surface → operator confirms → sustainability fix → operator review →
§1 dispatch → §2 audit → operator review + dispatch → §4 → operator
review + dispatch → ship sequence.

🚨 **Possibly relevant for THIS session specifically:** the
`parks-rec-scrapes` scheduled CI workflow is STILL ❌ on cron
triggers — root cause identified in Phase 5.7 §4.5 sidebar (Postgres
FK constraint violation in `scripts/parks_rec_prune.py`), handed off
to Phase 6 / sidecar lane. **Not in 5.9 scope** — do not investigate
unless the operator explicitly asks.

When you're confident you've understood the three docs end-to-end,
propose your §0 pre-flight execution plan to the operator, then your
kickoff-authoring plan + §1 sustainability layer plan (or note no
sustainability commit needed if picking pets / lodging), and wait
for go-ahead.
