# Phase 5.8 — Events — Next-agent boot prompt

> Drop-in artifact for the operator to paste into a fresh Cowork session.
> Mirrors `outputs/phase5_7_next_agent_boot_prompt.md` shape (which booted
> the Phase 5.7 session that SHIPPED at `e60b051` 2026-05-17).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.7 session 2
> (2026-05-17) post-`e60b051` SHIP. Pastable as-is below the `---` line.

---

You're picking up Phase 5.8 (Events) from scratch. Nothing shipped yet
for 5.8 — this is the kickoff session. Phase 5.7 (Outdoors, Parks &
Trails) SHIPPED on origin at `e60b051` (2026-05-17) with all 6
gate items cleared and CI green. Top of origin/main is `e60b051`
(or later if the Phase 6 lane shipped Amendment 7 between sessions —
check `git log -3` first).

Working directory: `C:\Users\casey\projects\havasu-chat` (Windows-side
operator env); sandbox bash mounts under
`/sessions/.../mnt/havasu-chat/`.

READ THESE THREE DOCUMENTS END-TO-END BEFORE DOING ANYTHING ELSE, IN
THIS ORDER:

  1. `outputs/phase5_7_session_closeout.md` — the close-out for the
     prior Phase 5.7 session. §1 has the 2-session-commit chain
     (`5f8fe08 F541 fix → e60b051 SHIP`) on top of session 1's
     `f5d1062 → 1dfd28e → 0c011ae → c2bdb6d` chain. §3 documents the
     §4.5 `parks-rec-scrapes` cron investigation — root cause is a
     Postgres FK constraint violation in `scripts/parks_rec_prune.py`,
     **handed off to Phase 6 / sidecar lane** with 3 fix options
     surfaced. §3 also documents a **new PowerShell `\"` escape
     footgun** (sibling to the existing empty-`-m""`-pathspec gotcha).
     §5 details the sustainability layer at `1dfd28e` —
     `(None, "entertainment_attractions") -> "outdoors-parks-trails"`
     catch-all + golf_course + medical_clinic _PRIMARY_TYPE_MAP
     widenings. **5.8 will need to PIVOT this catch-all** — see §1
     below. §6 has the carry-forward list. §9 has the pre-flight
     scaffold.
  2. `outputs/phase5_8_events_kickoff.md` — THE runbook for Phase
     5.8. **🚨 NOT YET AUTHORED — your first action is to author this
     doc**, mirroring `outputs/phase5_7_outdoors_parks_trails_kickoff.
     md` shape with 5.8-specific overrides. The 5.7 kickoff was
     authored at the start of session 1 per the established cadence
     (not at the end of 5.6); the 5.7 session ran with the kickoff +
     boot prompt + dump script + close-out + this boot prompt
     authored in-session. 5.8's kickoff should land at the start of
     5.8 session 1.
  3. `outputs/phase5_7_outdoors_parks_trails_kickoff.md` — the
     previous phase's runbook. Reads as the structural template the
     5.8 kickoff mirrors. Particularly read §1 (the Narrow scope
     rationale + sustainability layer extension shape — 5.8 will
     extend the same `_DISCOVERY_DOMAIN_FALLBACK` + `_PRIMARY_TYPE_MAP`
     in the opposite direction), §3 (verifier surface — Option C
     pattern that 5.8 will most likely repeat — no obvious public
     registry for community events; consider AZ event aggregators
     + LHC tourism board pages as deferred V1.5 paths), and §4
     (operator-curated rubric).

PHASE 5.8 (EVENTS) SCOPE — KEY FRAMING:

  • **Discovery domain:** `events` maps to
    `frozenset({"entertainment_attractions"})` per
    `app/contrib/google_places_scraper.py:89`. **Single-domain mapping**
    (no fitness_sports collision risk that 5.7 had to work around with
    the narrow-label-filter wrapper). The full
    `entertainment_attractions` label set per `scripts/places_
    categories.json` (lines 184-193) is 10 labels:
    movie theaters, bowling alleys, arcades, mini golf, golf courses,
    parks, museums, art galleries, live music venues, event venues.
  • **Scope decision needed in the kickoff:** parks / golf / mini
    golf are ALREADY in outdoors-parks-trails (cat-7) from 5.7. The 7
    deferred labels (event venues, live music venues, art galleries,
    museums, movie theaters, bowling alleys, arcades) are the
    natural 5.8 input pool. Recommend EXCLUDE the 3 cat-7 labels via
    a Narrow scope wrapper or similar — same Path A.2 pattern as 5.7
    via `outputs/phase5_7_narrow_label_filter.py`.
  • **Baseline (entries already in cat-2 events from 5.7 §2 FLIPs):**
    2 entries — Buses By The Bridge (event_venue, annual bus festival)
    + Desert Storm Headquarters (event_venue, annual boat poker run
    venue). Both are seasonal-activation event_venues, not place-based.
    **5.8 should net at least +18 entries** to clear a ≥20 gate (or
    the kickoff §6 can pick a different threshold given LHC's smaller
    event venue density).
  • **Sustainability layer PIVOT required.** 5.7's `1dfd28e` added
    `(None, "entertainment_attractions") -> "outdoors-parks-trails"`
    as a domain-wide catch-all. **For 5.8 this routes the wrong way**
    — 5.8's `art_gallery` / `event_venue` / `live_music_venue` /
    `museum` / `movie_theater` / `bowling_alley` / `arcade` primary_
    types would land in outdoors-parks-trails instead of events.
    Three options for the sustainability fix (decide in 5.8 kickoff
    §1):

    **(A — recommended) Add direct `_PRIMARY_TYPE_MAP` entries** for
    the expected events primary_types. Direct mappings beat catch-all
    per resolver order, so wildlife_refuge / golf_course stay in
    outdoors-parks-trails while the new event primary_types route to
    events. Example shape:
    ```python
    "event_venue": ("events", "commercial"),
    "art_gallery": ("events", "place"),
    "museum": ("events", "place"),
    "live_music_venue": ("events", "commercial"),
    "movie_theater": ("events", "commercial"),
    "bowling_alley": ("events", "commercial"),
    "amusement_arcade": ("events", "commercial"),
    ```
    The `commercial`-vs-`place` distinction follows 5.7's pattern:
    venues that charge admission / run shows = `commercial`; venues
    that are primarily-public-good = `place`.

    **(B) Re-route the catch-all** — change `(None, "entertainment_
    attractions") -> "outdoors-parks-trails"` to `... -> "events"`,
    then add 1-2 `_PRIMARY_TYPE_MAP` entries for `wildlife_refuge`
    and other 5.7-specific edge cases. Reverses the default but
    preserves wildlife_refuge → cat-7 explicitly.

    **(C — hybrid)** — add the 7 event primary_types via Option A,
    AND re-route the catch-all to events via Option B. Most explicit
    + future-proof but slightly bigger surface area.

    **Recommended: Option A.** Minimal diff, no need to revert 5.7's
    catch-all (which was correct for 5.7's scope), direct mappings
    are the cleanest pattern.

  • **Cross-cat cleanup expected.** The 5.7 §2 audit FLIPped 2
    entries to cat-2 events that arrived via the
    `entertainment_attractions` discovery. 5.8 §1 will likely
    surface MANY more event_venue primary_types from the deferred 7
    labels — some of which may already be in cat-7 (drafted or
    KEEP'd from 5.7). Cross-cat reconciliation between 5.7 cat-7
    and 5.8 cat-2 is the §2 audit special surface for 5.8 (analog
    to 5.6's gas-station/convenience cat-9/cat-8 axis and 5.7's
    cat-6 on-the-water cross-list).

WORKING PATTERNS TO INTERNALIZE FROM THE 5.7 CLOSE-OUT:

  • Pass dicts directly to JSON-typed SQLAlchemy columns
    (`Entity.crowd_notes`). Do NOT `json.dumps()` first. (5.3
    `f35d5e4` bug write-up — 5.4, 5.5, 5.6, 5.7 all avoided it by
    following this rule.)
  • `# noqa: E402` silences E402 only. F401 (unused imports) and
    **F541 (`f"..."` with no placeholders)** still fail ruff. The
    5.7 `c2bdb6d` dump-script bundle hit F541 in 9 places —
    fixed-forward at `5f8fe08`. Run ruff check Windows-side with
    the project config before commit. Watch for f-strings in
    concatenated `print(f"abc" f"def")` patterns where individual
    pieces may lack `{}` interpolation.
  • **PowerShell `\"` escape footgun (NEW for 5.7).** `\"` inside a
    PowerShell `"..."` string is NOT an escape sequence; embedding
    `\"\"\"` in a `git commit -m "..."` body causes git's flag
    parser to parse subsequent tokens as pathspecs (`fatal: /: '/'
    is outside repository`). Use **single-quoted `-m '...'`** flags
    for git commit messages when the body contains `"` or `/`
    characters; PS single quotes are literal (no interpolation, no
    escaping). Sibling to the existing empty-`-m""`-pathspec
    footgun.
  • Sandbox bash hits a git-index gotcha
    (`fatal: unknown index entry format 0xffff0000`) — use
    `git rev-parse` / `git show HEAD:` for index-free reads.
    Operator runs index-dependent ops (`git status` / `git commit`
    / `git push`) Windows-side via PowerShell.
  • **SANDBOX BASH MOUNT STALENESS — pattern continues to deepen.**
    5.5 documented this as a new gotcha (file-shape queries); 5.6
    hit it twice (json.load + importlib); 5.7 hit it THREE TIMES
    with new depth: (a) `.git/index.lock` view existed sandbox-side
    but not Windows-side; (b) `git diff` output didn't update
    post-restore; (c) `data/events.db` mtime showed May 8 (weeks
    before recent commits). **The Read tool is the source of truth
    in sandbox.** Sandbox bash is unreliable for ANY file-shape /
    git-state query AND for SQLite DB inspection. Default to Read
    tool + `git show HEAD:` for text inspection; Windows-side
    `python` + `git status` / `git diff` for working-tree state +
    DB query.
  • DB-write apply-scripts: stop the FastAPI dev server if running
    (`events.db` lock).
  • `Provider.google_review_snippets` is its OWN COLUMN on Provider
    (per `app/db/models.py:84`, populated by `scripts/places_load.py`
    from the scraper's `review_snippets` emission). NOT inside
    `attributes.google_review_snippets`. Drafts for top-10 long-form
    `crowd_notes` source from this column. Expected snippet coverage
    for events: TBD per the kickoff — event venues may have less
    abundant reviews than parks (which were 100% coverage in 5.7's
    top-10 with 5 snippets each).
  • `scripts/places_categories.json` LOCAL CORRUPTION RECURRENCE
    PATTERN — recurred 4× across 5.4 / 5.5 / 5.6 / 5.7-boot. The
    5.7-session-2 fifth-recurrence forecast did NOT materialize.
    Pre-flight item #6 in the 5.7 kickoff is widened to a
    **four-file shape check** (places_categories.json + places_load.py
    + app/db/models.py + app/contrib/google_types_mapping.py).
    Continue that shape check in 5.8.
  • `_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a domain-wide
    catch-all at `places_load.py:368-371`, NOT a `primary_type=None`
    filter. 5.6 routed 27 edge-case providers via the
    `(None, "retail")` catch-all; 5.7 routed ~5 via `(None,
    "entertainment_attractions")` (Bill Williams NWR etc.); 5.8's
    sustainability fix should account for this if pivoting (see §1
    PIVOT options above).
  • `entity_type` mixed (place + commercial) — gate-1 query MUST
    use the `(e.entity_type != 'commercial' OR provider-visible)`
    OR-clause shape from `outputs/phase5_2_gate_verification.py` /
    `outputs/phase5_6_gate_verification.py` /
    `outputs/phase5_7_gate_verification.py`. (Phase 5.7's 27
    post-apply entries are all `commercial`; 5.8's `event_venue` +
    `live_music_venue` will likely also be commercial,
    `art_gallery` + `museum` may be place per the §1 PIVOT shape.)
  • **CI flakiness on intermediate commits**: 5.5 / 5.7-session-1
    both saw the same pattern (one ✓ + one ❌ on the same commit ID,
    short elapsed time = runner-orchestration flake not code). Try
    `gh run rerun <ID>` before shipping a fix commit. Final
    tree-state CI green is the ship-readiness signal.

AFTER YOU READ THE THREE DOCS:

  1. **Author the kickoff doc** —
     `outputs/phase5_8_events_kickoff.md` — mirroring the 5.7 kickoff
     shape with 5.8 overrides (Narrow scope picking the 7 deferred
     labels; Option C verifier resolution likely; §1 sustainability
     PIVOT plan; §4 operator-curated rubric — heat_exposure default
     is mixed for events; event venues are often indoor BUT
     festivals + outdoor concerts are outdoor; ~50/50 split forecast
     but kickoff §4 should pick a default + override list).
  2. **Run §0 pre-flight items** (git log + status + alembic +
     pytest collect + diagnose + widened four-file shape check + CI
     status + Google Places key + DB spot-check including the 2
     baseline events entries from 5.7's FLIP).
  3. **Surface §0 status to the operator.** If `places_categories.
     json` corruption has recurred (fifth+ recurrence likely), surface
     immediately + ask for restore before proceeding.
  4. **§1 sustainability commit** — extend `_DISCOVERY_DOMAIN_FALLBACK`
     and/or `_PRIMARY_TYPE_MAP` per the §1 PIVOT plan in the kickoff.
     Mirror `1dfd28e` / `44e8097` / `4d41944` / `fc51940` / `7c994aa`
     surgical-fix shape exactly: single focused `fix(scripts)` commit
     with regression tests in `tests/test_phase5_8_places_load_
     resolver.py`. Land BEFORE the §1 Layer 1 dispatch
     (sustainability-first pattern from 5.5 / 5.6 / 5.7).
  5. **§1 Layer 1 dispatch** — Google Places scrape with the 7
     deferred labels (via Narrow scope wrapper if needed).
  6. **§2 audit cycle** — mirror the 5.7 §2 cadence: dump script →
     operator runs → audit doc + apply-script → operator dispatches.
     Special-audit axes for 5.8: (a) cat-7 outdoors-parks-trails
     cross-list (recap which entries 5.7 KEPT in cat-7 vs which
     might want to move to cat-2); (b) cat-13 public-civic-resources
     cross-list (event_venue at LHC City Hall? Museum at LHC
     Library?); (c) seasonal-activation de-dup (the 5.7-FLIPped
     Buses By The Bridge + Desert Storm HQ are annual events — are
     there separate Provider rows for different years' events that
     should be merged?).
  7. **§4 heat_exposure + crowd_notes** — apply-scripts mirroring
     `apply_phase5_7_parks_*.py`. heat_exposure default TBD in
     kickoff §4 (events split indoor/outdoor); crowd_notes top-10
     by review_count.
  8. **Gate verification + SHIP commit** — `outputs/phase5_8_gate_
     verification.py` mirroring `phase5_7_gate_verification.py`
     shape; SHIP commit bundles audit + apply-scripts + gate
     verification + session close-out + Phase 5.9 boot prompt.

DO NOT START ANY SCRAPE (`places_discovery` / enrichment / load),
VERIFICATION RUN, OR DB-WRITE APPLY-SCRIPT BEFORE OPERATOR
CONFIRMATION. The 5.7 §1 + §1-sustainability cadence followed this
pattern strictly and it caught real issues mid-session (`places_
categories.json` corruption + wider drift at §0; wrapper sys.path
bug at first dry-run smoke; cache-reload-vs-fresh-sweep distinction
that surfaced because the operator skipped the broken wrapper).
Continue the cadence: §0 status surface → operator confirms →
sustainability fix → operator review → §1 dispatch → §2 audit →
operator review + dispatch → §4 → operator review + dispatch → ship
sequence.

🚨 **Possibly relevant for THIS session specifically:** the
`parks-rec-scrapes` scheduled CI workflow is STILL ❌ on cron
triggers — 5.7 §4.5 sidebar investigated and identified the root
cause (Postgres FK constraint violation in `scripts/parks_rec_prune.
py`, NOT either of the original kickoff §4.5 hypotheses). 3 fix
options surfaced in `outputs/phase5_7_session_closeout.md` §3. **Not
in 5.8 scope** — Phase 6 / sidecar lane territory. Do not
investigate during 5.8 unless the operator explicitly asks.

When you're confident you've understood the three docs end-to-end,
propose your §0 pre-flight execution plan to the operator, then your
kickoff-authoring plan + §1 sustainability layer plan, and wait for
go-ahead.
