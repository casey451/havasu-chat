# Phase 5.7 — Outdoors, Parks & Trails — Session 2 boot prompt

> Drop-in artifact for the operator to paste into a fresh Cowork session
> to pick up Phase 5.7 mid-flight (after session 1 cleared §0 + §1 +
> §1-sustainability + §1-load + authored the §2 dump script).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.7 boot session
> (2026-05-17) post-`0c011ae` + post-§1-load. Pastable as-is below the
> `---` line.

---

You're picking up Phase 5.7 (Outdoors, Parks & Trails) MID-FLIGHT at
gates §2 → §4 → §5. Phase 5.7's first session (2026-05-17) shipped
§0 + §1 + §1-sustainability + §1-load (cache-reload then fresh-sweep)
and authored — but did not yet run — the §2 ambig audit dump script.
3 of 6 acceptance-gate items are cleared; 3 remain (§2 audit, §4
heat_exposure, §4 crowd_notes). Top of `origin/main` is `0c011ae` (or
later if Phase 6 lane shipped Amendment 6 between sessions — check
`git log -3` first).

Working directory: `C:\Users\casey\projects\havasu-chat` (Windows-side
operator env); sandbox bash mounts under
`/sessions/.../mnt/havasu-chat/`.

READ THESE FOUR DOCUMENTS END-TO-END BEFORE DOING ANYTHING ELSE, IN
THIS ORDER:

  1. **`outputs/phase5_7_session_midpoint_checkpoint.md`** — the
     state-of-play hand-off doc from session 1. §1 has the 3-commit
     lane chain `f5d1062 → 1dfd28e → 0c011ae` + the 2 DB-only writes.
     §2 has the gate status (3 of 6 cleared). §3 documents the
     sustainability commit + wrapper script + the 3 pre-flight
     surprises (including the new sandbox-mount-staleness depth — the
     `.git/index.lock` view that's stale, and `git diff` itself
     returning stale data post-restore). §4 has the §2 audit
     pre-classification surface (which entries are clear FLIP / DRAFT
     / KEEP). §5 has the remaining-work checklist. §8 has the §0
     pre-flight scaffold.
  2. **`outputs/phase5_7_outdoors_parks_trails_kickoff.md`** — the
     Phase 5.7 runbook (authoritative for the §6 acceptance gate
     definitions + §3 Option C verifier resolution + §4.5
     parks-rec-scrapes CI sidebar). Authored at the start of session
     1; resolves the boot-prompt-framing miss (`outdoor_recreation`
     domain doesn't exist; actual mapping is
     `outdoors-parks-trails -> {fitness_sports,
     entertainment_attractions}` with Narrow scope = 3
     entertainment_attractions labels).
  3. **`outputs/phase5_6_session_closeout.md`** — the just-shipped
     5.6 close-out (carries the apply-script + audit + sustainability
     layer playbooks 5.7 reuses verbatim).
  4. `outputs/phase5_7_next_agent_boot_prompt.md` — the ORIGINAL boot
     prompt from end of session 5.6 that primed session 1. **Note:
     some of its framing is wrong** (the anticipated `outdoor_
     recreation` domain doesn't exist; the boot-prompt-framing miss
     is documented in the kickoff §0 header callout). Read for
     historical context only — the midpoint checkpoint + kickoff
     supersede it.

WORKING PATTERNS TO INTERNALIZE FROM THE 5.6 + 5.7-session-1
HISTORY:

  • Pass dicts directly to JSON-typed SQLAlchemy columns
    (`Entity.crowd_notes`). Do NOT `json.dumps()` first. (5.3
    `f35d5e4` lesson.)
  • `# noqa: E402` silences E402 only. F401 (unused imports) still
    fails ruff. F541 (`f"..."` with no placeholders) also fails.
    Audit imports + f-strings before committing. (5.3 `bff4a79`
    lesson; 5.6 hit F541 inline; 5.7 hit E402 on the wrapper's
    sys.path-insert imports — `# noqa: E402` markers added inline.)
  • **Sandbox bash MOUNT-STALENESS — pattern deepening.** 5.5
    documented file-shape staleness; 5.6 hit it twice (json.load +
    importlib); 5.7-session-1 hit it THREE TIMES with new depth:
    (a) `.git/index.lock` view existed sandbox-side but not
    Windows-side; (b) `git diff` output didn't update post-restore
    (continued reporting -440 lines on places_load.py for the whole
    session); (c) post-Edit `wc -l` continued showing pre-restore
    line counts. **The Read tool is the source of truth in sandbox.**
    Sandbox bash is unreliable for ANY file-shape OR git-state
    query. Use `git show HEAD:` for index-free file reads.
    Windows-side `git status` / `git diff` / `git restore` are
    operator-authoritative.
  • Sandbox bash git-index gotcha (`fatal: unknown index entry
    format 0xffff0000`) on `git status` / `git commit` / `git push`
    — operator runs Windows-side via PowerShell.
  • PowerShell `git commit -m "" ...` footgun: empty `-m ""`
    between multiple `-m "..."` flags is treated as a pathspec by
    git's flag parser. Use multiple `-m "..."` flags WITHOUT empty
    separators; git inserts blank lines automatically.
  • DB-write apply-scripts: stop the FastAPI dev server if running
    (`events.db` lock).
  • `Provider.google_review_snippets` is its OWN COLUMN on Provider
    (per `app/db/models.py:84`, populated by `scripts/places_load.py`
    from the scraper's `review_snippets` emission). NOT inside
    `attributes.google_review_snippets`. Drafts for top-10 long-form
    `crowd_notes` source from this column. Expected snippet coverage
    for parks: ~70-85% (5.4=70.6%, 5.5=85%, 5.6=~80%).
  • `scripts/places_categories.json` LOCAL CORRUPTION recurred a
    FOURTH time at the start of session 1. **Plus** a wider drift
    pattern across `scripts/places_load.py` + `app/db/models.py` +
    `app/contrib/google_types_mapping.py` (suspected stale checkout
    / external-editor crash). §0 item 6 in the kickoff is widened to
    a four-file shape check; the boot-session also added a sandbox
    `.git/index.lock` staleness check (lock may exist sandbox-side
    but not Windows-side). Restore via `git restore .` Windows-side.
  • **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a
    domain-wide catch-all** at `places_load.py:368-371`, not a
    `primary_type=None` filter. 5.6 routed 27 edge-case providers
    via this behavior; 5.7's `(None, "entertainment_attractions")`
    catch-all caught `wildlife_refuge` (Bill Williams River NWR)
    cleanly — same shape, smaller volume due to Narrow scope.
  • `entity_type` mixed (place + commercial) — gate-1 query MUST
    use the `(e.entity_type != 'commercial' OR provider-visible)`
    OR-clause shape from `outputs/phase5_2_gate_verification.py`
    and `outputs/phase5_6_gate_verification.py`. (Phase 5.7's 30
    §1-loaded entries are all `commercial`; see midpoint checkpoint
    §4 for why.)
  • **CI flakiness on intermediate commits**: 5.5 `6fb74ac`
    initially showed X red but a rerun went green; 5.7-session-1
    saw the same pattern on the post-boot-prompt commit (one ✓ + one
    ❌ on the same commit ID, 17s elapsed = runner-orchestration
    flake not code). Try `gh run rerun <ID>` before shipping a fix
    commit. Final tree-state CI green is the ship-readiness signal.

AFTER YOU READ THE FOUR DOCS:

  1. **Run §0 pre-flight items** from the kickoff §0 + midpoint
     checkpoint §8 (git log + status + alembic + pytest collect +
     diagnose + WIDENED four-file shape check + CI status + Google
     Places key + DB spot-check). Expected: pytest=1946 collected;
     CI green on `0c011ae`; alembic `0a1b2c3d4e5f`; clean four-file
     shape; outdoors-parks-trails DB state = 30 entries / 0 verified
     / 30 heat_exposure=NULL / 0 long-form crowd_notes / 0 draft.
  2. **Surface §0 status to the operator.** If anything's drifted
     (places_categories.json corruption fifth recurrence likely;
     wider drift possible), surface immediately + ask for restore
     before proceeding.
  3. **§2 audit cycle dispatch.** Per midpoint checkpoint §5
     gate-blocking item #1:
     a. Operator runs `python outputs/phase5_7_ambig_audit_dump.py`
        (produces `outputs/phase5_7_ambig_audit_data.json` +
        stdout aggregates across 3 special-audit axes: cat-6
        on-the-water cross-list, cat-12 classes-sports-recreation
        cross-list, SARA Park same-cat de-dup). Operator surfaces
        the JSON + stdout to you.
     b. **Commit the dump script** Windows-side (mirrors 5.6's
        `phase5_6_ambig_audit_dump.py` landing alongside the audit;
        ~22KB).
     c. You read the JSON + author
        `outputs/phase5_7_parks_audit.md` (audit doc mirroring
        `outputs/phase5_6_shopping_essentials_audit.md` shape).
        Pre-classification surface in midpoint checkpoint §4 gives
        you the head start: clear FLIPs (Buses By The Bridge +
        Desert Storm HQ → cat-2 events), clear DRAFTs (Altitude
        Trampoline Park indoor, Parks & Rec Dept civic), review-
        needed (Sportsman's Club, Motocross Park, Ofd Racing,
        Thompson Bay Beach, Butterfly Garden, ASU SWANSON FIELDS),
        SARA Park de-dup (KEEP all 6 per V1 recommendation), 21
        clear KEEPs (the actual parks/golf/state-parks/wildlife
        refuge).
     d. You author `outputs/apply_phase5_7_parks_audit.py` (FLIPs +
        DRAFTs from the audit doc, mirroring
        `outputs/apply_phase5_6_shopping_audit.py` shape).
     e. Surface the audit doc + apply-script to operator for
        review.
     f. Operator dispatches the apply-script (stops FastAPI dev
        server first per the documented gotcha).
  4. **§4 heat_exposure apply-script.** Mirror
     `outputs/apply_phase5_6_shopping_heat_exposure.py` BUT
     **flip the default to `outdoor`** + populate `INDOOR_OVERRIDES`
     instead of `OUTDOOR_OVERRIDES`. Only obvious indoor candidate
     today is Altitude Trampoline Park (which will get FLIP'd or
     DRAFT'd in §2 anyway). Expected post-script: 0 NULL
     heat_exposure across 30 (or fewer after §2 FLIPs/DRAFTs).
  5. **§4 crowd_notes top-10 apply-script.** Mirror
     `outputs/apply_phase5_6_shopping_crowd_notes.py` exactly. Pass
     dict directly to `Entity.crowd_notes` JSON column (no
     `json.dumps()`). Source drafts from
     `Provider.google_review_snippets` (its OWN column, not in
     attributes). Expected snippet coverage ~70-85%; some entries
     (state parks, popular city parks, golf course) will have
     abundant reviews.
  6. **Gate verification script.** Author
     `outputs/phase5_7_gate_verification.py` mirroring
     `outputs/phase5_6_gate_verification.py` shape with 5.7
     overrides: 6 gates (no `is_mobile_service`); threshold ≥20 not
     ≥40; `outdoors-parks-trails` slug everywhere; gate-1 OR-clause
     query handling `entity_type='place'` correctly per
     `outputs/phase5_2_gate_verification.py`.
  7. **SHIP commit.** `chore(outputs)` — Phase 5.7 SHIPPED — all 6
     gate items cleared. Co-commit the audit doc + apply-scripts +
     gate verification script + session close-out
     (`outputs/phase5_7_session_closeout.md` — mirrors
     `outputs/phase5_6_session_closeout.md` shape with SHIPPED
     state) + the next-phase boot prompt
     (`outputs/phase5_8_<next-slug>_next_agent_boot_prompt.md` —
     next Tier-1 slug TBD; likely `events` or
     `classes-sports-recreation` per the remaining 12-slug list).

🚨 **Possibly relevant for THIS session specifically:** the
`parks-rec-scrapes` scheduled CI workflow has been X on cron
triggers throughout 5.3 + 5.4 + 5.5 + 5.6 + 5.7-session-1.
Decision 3 (operator-confirmed at session 1) defers investigation to
the §4.5 sidebar (post-gate-2, not blocking). **Investigate after
your §2 audit clears.** Hypotheses per kickoff §4.5: (a) workflow
authored against pre-Phase-3.2 `outdoors-and-parks` slug — 1-line
slug-rename PR fixes; (b) workflow scrapes outdoors-parks-trails and
fell into the `(None, "entertainment_attractions")` gap that the §1
sustainability commit (`1dfd28e`) just patched — may go green
retroactively on next cron without code change.

DO NOT START ANY SCRAPE (`places_discovery` / enrichment / load),
VERIFICATION RUN, OR DB-WRITE APPLY-SCRIPT BEFORE OPERATOR
CONFIRMATION. The §1 + §1-sustainability cadence in session 1
followed this pattern strictly and it caught real issues mid-session
(places_categories.json corruption + wider drift at §0; wrapper
sys.path bug at first dry-run smoke; the cache-reload-vs-fresh-
sweep distinction that surfaced because the operator skipped the
broken wrapper and ran enrichment+load against the existing cache).
Continue the cadence: §2 dump → operator review → audit doc →
operator review → apply-script → operator review + dispatch → §4 →
operator review + dispatch → ship sequence.

When you're confident you've understood the four docs end-to-end,
propose your §0 pre-flight execution plan + your §2 audit cycle
dispatch plan to the operator, and wait for go-ahead.
