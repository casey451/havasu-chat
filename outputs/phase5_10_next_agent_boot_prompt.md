# Phase 5.10 — Next-agent boot prompt

> Drop-in artifact for the operator to paste into a fresh Cowork session.
> Mirrors `outputs/phase5_9_next_agent_boot_prompt.md` shape
> (which booted the Phase 5.9 session that SHIPPED at `4527ca1`
> 2026-05-17).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.9 session 1
> (2026-05-17) post-`4527ca1` SHIP + `bc08bf6` SHA-cleanup.
> Updated post-kickoff-authoring to lock category pick at
> `lodging-vacation-rentals` and correct the prior "single-domain"
> misframing (lodging-vacation-rentals is actually a TWO-DOMAIN
> bundle including `lake_recreation` — see kickoff §1 framing
> correction). Pastable as-is below the `---` line.

---

You're picking up Phase 5.10 (Lodging & Vacation Rentals,
`lodging-vacation-rentals`, cat-10) from scratch — the kickoff
session. Phase 5.9 (Classes, Sports & Recreation) SHIPPED on origin at
`4527ca1` (2026-05-17) with all 6 gate items cleared and CI green;
SHA-cleanup at `bc08bf6`; Phase 5.10 kickoff doc pre-staged at
`<KICKOFF-COMMIT>`. Top of `origin/main` is `<KICKOFF-COMMIT>` (or
later if the Phase 6 lane shipped the consolidated amend5-8 dispatch
between sessions). Find your own context before doing anything else.

Working directory: `C:\Users\casey\projects\havasu-chat`.

1. `git log --oneline -10` to confirm `<KICKOFF-COMMIT>` is top of main;
   the 5.9 → 5.10-pre-stage chain is
   `0af5f73 → a99e2c4 → 4527ca1 → bc08bf6 → <KICKOFF-COMMIT>` on top
   of the 5.8 SHIP at `2808146`.
2. Read these four docs end-to-end, in this order:
   a. `outputs/phase5_10_next_agent_boot_prompt.md` (THIS file — the
      boot prompt for this session — read FIRST; it sets the scope
      framing and notes the §1 sustainability is conditional, NOT
      pre-required)
   b. `outputs/phase5_9_session_closeout.md` (the just-shipped 5.9
      state index — carries the §4 lesson on DB-verify before
      cross-cat moves caught prospectively via dupe-check + the
      §3 cp1252-codec / ASCII-only-stdout lesson + the §2 DUAL-cat
      Slice D pattern via `_dual_add_category` helper)
   c. `outputs/phase5_10_lodging_vacation_rentals_kickoff.md` (the
      5.10 runbook — authoritative for the §6 acceptance gate
      definitions + §1 Narrow-scope decision (5 in-scope labels of
      16 in the two-domain bundle) + §1 sustainability decision
      DEFERRED to §1 load output (may not be needed) + §3 Option C
      verifier resolution + §4 mixed heat_exposure rubric with new
      water_adjacent overrides)
   d. `outputs/phase5_9_classes_sports_recreation_kickoff.md` (the
      5.9 runbook the 5.10 kickoff mirrors — for shape continuity)

After you've read those, surface a short context-discovery report to
me: which docs you read, the carry-forward items you spotted, your
understanding of the 6 gates + the §1 Narrow scope decision + the §2
cross-cat axes (primary axis: cat-3 on-the-water for waterfront
resorts), and any ambiguities you want resolved. Then propose your
§0 pre-flight execution plan + your §1 sustainability commit plan (or
note no sustainability commit needed if §1 load shows 0 unmapped).

Do not start any scrape (`places_discovery` / enrichment / load),
verification run, or DB-write apply-script before operator
confirmation. The §0 → §1-sustainability (conditional) → §1-load →
§2 audit → §4 heat/crowd_notes → ship cadence in 5.8 + 5.9 followed
this pattern strictly. Continue the cadence: operator confirms each
step before dispatch.

PHASE 5.10 SCOPE — KEY FRAMING:

  • **Category committed: `lodging-vacation-rentals` (cat-10).** The
    last remaining Tier-1 slug is `pets` (cat-11), which becomes the
    target for Phase 5.11. Operator's commit at 5.10 dispatch time.

  • **Discovery domain is a TWO-DOMAIN BUNDLE.** Per
    `app/contrib/google_places_scraper.py:87`,
    `"lodging-vacation-rentals": frozenset({"lodging",
    "lake_recreation"})` — same shape as 5.9's classes-sports-
    recreation. The `lake_recreation` domain has the 5.2 `(None,
    "lake_recreation") → "on-the-water"` catch-all already in place
    at `scripts/places_load._DISCOVERY_DOMAIN_FALLBACK:216`.

  • **Narrow scope decision: 5 in-scope lodging-domain labels** per
    kickoff §1:
      - hotels
      - motels
      - resorts
      - vacation rentals
      - bed and breakfast
    **The 11 lake_recreation labels defer to V1.5** (5.2 absorbed
    the marina/boat shape; RV parks already in cat-10 via `rv_park`
    direct mapping; campgrounds + RV dealers/rentals can be
    re-evaluated per-label in V1.5). Narrow-scope wrapper script
    `outputs/phase5_10_narrow_label_filter.py` mirrors 5.9's wrapper
    exactly (Path A.2 — standalone outputs/ wrapper, no production
    code touched).

  • **Sustainability layer PIVOT is CONDITIONAL, not pre-required.**
    Unlike 5.9 (where the 5.4 `(None, "fitness_sports") → HWC`
    catch-all was actively mis-routing cat-12-native types), 5.10's
    existing setup may just work:
      - `lodging` direct mapping → cat-10 (pre-Phase-5; catches the
        generic case via secondary types[] entries)
      - `rv_park` direct mapping → cat-10 (pre-Phase-5)
      - Google's actual lodging primary_types (`hotel`, `motel`,
        `resort_hotel`, `bed_and_breakfast`, `extended_stay_hotel`)
        may not be in `_PRIMARY_TYPE_MAP` directly — BUT
        `map_google_types_to_slug_and_place_type` iterates the
        `types[]` array first-match, and `lodging` is almost always
        present as a secondary type for any lodging-shape place.
    **Decision deferred to §1 load output:** check `category_id
    unmapped (operator queue)` count. If 0, no sustainability commit
    needed. If non-zero, author per kickoff §1 Option A pattern (5
    direct mappings + new `(None, "lodging") → "lodging-vacation-
    rentals"` catch-all).

  • **Cross-cat overlap expected — primary axis cat-3 on-the-water.**
    Waterfront resorts (London Bridge Resort, Nautical Beachfront
    Resort, Heat Hotel, Havasu Springs) likely already in cat-3 from
    5.2 lake_recreation absorption. 5.10 §2 audit may need 2-5
    DUAL-cat additions (cat-3 + cat-10) per the 5.9 Slice D
    pattern (Our Lady DUAL cat-12 + cat-13). Secondary axes: cat-1
    eat-drink (hotel restaurants), cat-2 events (resort event venues).

WORKING PATTERNS TO INTERNALIZE FROM THE 5.9 CLOSE-OUT:

  • **Pass dicts directly to JSON-typed SQLAlchemy columns**
    (`Entity.crowd_notes`). Do NOT `json.dumps()` first.
  • **F401 + F541 + I001 ruff footguns.** `# noqa: E402` silences
    E402 only.
  • **PowerShell `\"` escape footgun.** Use single-quoted `-m '...'`
    flags for git commit messages when the body contains `"` or
    `/` characters.
  • **NEW 5.9: PowerShell cp1252 encoding gotcha.** Python print
    statements with `→` (U+2192) crash on PowerShell pipe. Use ASCII
    `->` and `--` instead. `§` (U+00A7) and `—` (U+2014) mojibake
    but don't crash. **Cleanest discipline: avoid all non-ASCII in
    script stdout; route Unicode to JSON files instead (UTF-8 by
    default).** 5.9 hit this once on dump script's V1.5 carry section.
  • **Sandbox bash mount-staleness — pattern continues** (5.5/5.6/
    5.7/5.8/**5.9 hit it at §0 first git diff**). Read tool is
    authoritative; sandbox bash file-shape queries are unreliable for
    ANY working-tree state / git-index / DB-inspection query. Default
    to Read + `git show HEAD:` for sandbox text inspection;
    Windows-side `python` + `git status` / `git diff` for working-
    tree state + DB query.
  • **Sandbox bash git-index gotcha** — use `git rev-parse` / `git
    show HEAD:` for index-free reads.
  • **DB-write apply-scripts: stop the FastAPI dev server if running**
    (`events.db` lock).
  • **`Provider.google_review_snippets` is its OWN COLUMN** on
    Provider. Drafts for top-10 long-form `crowd_notes` source from
    this column.
  • **`scripts/places_categories.json` LOCAL CORRUPTION RECURRENCE
    PATTERN** — recurred 4× across 5.4 / 5.5 / 5.6 / 5.7-boot. The
    5.7 / 5.8 / 5.9 sessions found the four-file shape check clean.
    Continue the four-file shape check in 5.10 §0.
  • **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a
    domain-wide catch-all** at `places_load.py:368-371`. 5.2's
    `(None, "lake_recreation") → "on-the-water"` stays in place for
    5.10. 5.10 may add `(None, "lodging") → "lodging-vacation-
    rentals"` as NEW if §1 load reveals unmapped.
  • **`entity_type` mixed (place + commercial)** — gate-1 query MUST
    use the `(e.entity_type != 'commercial' OR provider-visible)`
    OR-clause shape from `outputs/phase5_2_gate_verification.py` /
    `outputs/phase5_7_gate_verification.py` /
    `outputs/phase5_8_gate_verification.py` /
    `outputs/phase5_9_gate_verification.py`. (For 5.10 all entries
    expected `commercial`; OR-clause is still required for
    route-render shape.)
  • **CI flakiness on intermediate commits** — 5.5 / 5.7-session-1 /
    5.8 all saw the same pattern; 5.9 didn't hit it. Try `gh run
    rerun <ID>` before shipping a fix commit.
  • **DB-verify the "existing entity in cat-X" premise BEFORE
    finalizing audit doc** (5.9 prospective-catch lesson). Author
    `outputs/phase5_10_dupe_check.py` EARLY in §2 audit. For 5.10
    specifically: verify waterfront resort cat-3 placements, RV park
    cat-10 placements, hotel-with-restaurant cat-1 cross-links.
  • **5.9 §2 in-session reporting bug** — apply-script's "Post-apply
    EntityCategory rows" count showed 27 immediately after changes,
    but actual DB state was 31 (autoflush quirk). For 5.10 fix: use
    `select(func.count())` instead of `.all()` length; or add
    explicit `session.flush()` before the COUNT query.

AFTER YOU READ THE FOUR DOCS:

  1. **Run §0 pre-flight items** (git log + status + alembic + pytest
     collect + diagnose + widened four-file shape check + CI status
     + Google Places key + DB spot-check including the 31 baseline
     cat-12 entries from 5.9 + 20 baseline cat-2 from 5.8 + likely
     0-5 baseline cat-10 entries from 5.2).
  2. **Surface §0 status to the operator.** If
     `places_categories.json` corruption has recurred (8th+
     recurrence forecast), surface immediately + ask for restore
     before proceeding.
  3. **§1 Layer 1 dispatch** — author the Narrow-scope wrapper
     `outputs/phase5_10_narrow_label_filter.py` first (mirror
     `outputs/phase5_9_narrow_label_filter.py` with 5 lodging labels).
     Then Google Places scrape via the wrapper + enrichment +
     places_load dry-run + places_load.
  4. **§1 sustainability commit (CONDITIONAL)** — if §1 load
     shows `category_id unmapped (operator queue): 0`, NO
     sustainability commit needed. If non-zero, mirror `0af5f73`
     (Phase 5.9 sustainability) surgical-fix shape exactly: single
     focused `fix(scripts)` commit adding 5 `_PRIMARY_TYPE_MAP`
     entries + 1 new `(None, "lodging")` catch-all + regression
     tests in `tests/test_phase5_10_places_load_resolver.py`. THIS
     is unusual cadence (sustainability normally lands BEFORE the
     load); 5.10's conditional pattern is justified by the existing
     `lodging` direct mapping likely covering everything.
  5. **§2 audit cycle** — author `outputs/phase5_10_dupe_check.py`
     EARLY (before finalizing audit doc) per the 5.9 prospective-
     catch discipline. Then mirror the 5.9 §2 cadence: dump script
     → operator runs → audit doc + apply-script → operator
     dispatches. Special-audit axes for 5.10: primary cat-3
     on-the-water (waterfront resorts); secondary cat-1 eat-drink
     (hotel restaurants); tertiary cat-2 events (resort event
     venues).
  6. **§4 heat_exposure + crowd_notes** — apply-scripts mirroring
     `apply_phase5_9_classes_*.py`. heat_exposure default `indoor`;
     OUTDOOR_OVERRIDES for resort properties with outdoor primary
     draw (pools); **NEW for 5.10:** WATER_ADJACENT_OVERRIDES for
     waterfront resorts (lake-edge lodging). Mirror the 5.2 on-the-
     water heat_exposure pattern for the water_adjacent shape.
  7. **Gate verification + SHIP commit** — `outputs/phase5_10_gate_
     verification.py` mirroring `phase5_9_gate_verification.py`
     shape; SHIP commit bundles audit + apply-scripts + gate
     verification + session close-out + Phase 5.11 boot prompt.

🚨 **Possibly relevant for THIS session specifically:**

- The `parks-rec-scrapes` scheduled CI workflow is STILL ❌ on cron
  triggers — root cause identified in Phase 5.7 §4.5 sidebar
  (Postgres FK constraint violation in `scripts/parks_rec_prune.py`),
  handed off to Phase 6 / sidecar lane. **Not in 5.10 scope** — do
  not investigate unless the operator explicitly asks.
- The **4-deep Phase 6 amend backlog (5.5/5.6/5.7/5.8) consolidated
  at `outputs/claude_code_dispatch_phase6_amend5_to_8.md`** is
  ready for Claude Code parallel agent dispatch. Operator may want
  to extend to amend5-9 (adding the 5.9 SHIP line) OR amend5-10
  (adding both 5.9 + 5.10 SHIP lines) before dispatching. Coordinate
  with 5.10 lane — file-scope disjoint (Phase 6 amend touches
  `docs/STATE.md` + `docs/maintainability/master_build_plan.md`;
  5.10 touches `scripts/` + `outputs/` + `app/` + `tests/`). May
  dispatch in parallel with 5.10 §0 pre-flight.
- **The 5.9 close-out / boot prompt previously said BOTH
  lodging-vacation-rentals AND pets were "single-domain mappings
  with no existing catch-alls that would mis-route" — this was
  WRONG for lodging-vacation-rentals.** Lodging-vacation-rentals is
  a TWO-DOMAIN bundle including `lake_recreation` (which has the
  5.2 catch-all). The 5.10 kickoff at
  `outputs/phase5_10_lodging_vacation_rentals_kickoff.md` handles
  this correctly via Narrow scope (5 lodging-domain labels only).
  For pets (Phase 5.11): pets IS single-domain (per
  `DISCOVERY_CATEGORY_TO_DOMAINS["pets"] = frozenset({"pets"})`)
  with no existing pets catch-all — so the 5.11 framing should hold.

When you're confident you've understood the four docs end-to-end,
propose your §0 pre-flight execution plan to the operator, then your
§1 Layer 1 dispatch plan + conditional sustainability layer plan,
and wait for go-ahead.
