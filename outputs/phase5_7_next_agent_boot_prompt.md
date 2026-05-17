# Phase 5.7 — Outdoors, Parks & Trails — Next-agent boot prompt

> Drop-in artifact for the operator to paste into a fresh Cowork session.
> Mirrors `outputs/phase5_6_next_agent_boot_prompt.md` shape (which booted
> the Phase 5.6 session that SHIPPED at `7609a01` 2026-05-16).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.6 session
> (2026-05-16) post-`7609a01` SHIP. Pastable as-is below the `---` line.

---

You're picking up Phase 5.7 (Outdoors, Parks & Trails) from scratch.
Nothing shipped yet for 5.7 — this is the kickoff session. Phase 5.6
(Shopping, Grocery & Essentials) SHIPPED on origin at `7609a01`
(2026-05-16) with all 6 gate items cleared and CI green. Top of
origin/main is `7609a01` (or later if the Phase 6 lane shipped
Amendment 6 between sessions — check `git log -3` first).

Working directory: `C:\Users\casey\projects\havasu-chat` (Windows-side
operator env); sandbox bash mounts under
`/sessions/.../mnt/havasu-chat/`.

READ THESE THREE DOCUMENTS END-TO-END BEFORE DOING ANYTHING ELSE, IN
THIS ORDER:

  1. `outputs/phase5_6_session_closeout.md` — the close-out for the
     prior Phase 5.6 session. §1 has the 3-commit lane chain
     `44e8097 → 8ab6db3 → 7609a01`. §3 lists the surgical fix shipped
     mid-session (`44e8097` `_DISCOVERY_DOMAIN_FALLBACK` extension for
     `retail` domain). §3 also documents the catch-all-routing
     surprise: the `(None, "retail")` entry acted as a domain-wide
     second-chance lookup that scooped 27 edge-case providers (Hospice,
     eye-care medical_clinics, B2B wholesale, etc.) into shopping-
     essentials — requiring the largest §2 edge-case re-route
     apply-script of any 5.x phase to date (11 FLIPs + 7 DRAFTs).
     **5.7 should anticipate this same behavior** on the
     `outdoor_recreation` domain. §6 has the carry-forward list. §9 has
     the pre-flight scaffold for the next session.
  2. `outputs/phase5_7_outdoors_parks_trails_kickoff.md` — THE runbook
     for Phase 5.7. **🚨 NOT YET AUTHORED — your first action is to
     author this doc**, mirroring `outputs/phase5_6_shopping_grocery_
     essentials_kickoff.md` shape with 5.7-specific overrides. The
     5.6 kickoff was authored at the end of the 5.5 session per the
     established cadence; the 5.6 session ran out of runway before
     authoring the 5.7 kickoff. Anticipated label set per `scripts/
     places_categories.json` `outdoor_recreation` domain (per the 5.6
     close-out §9): parks, trails, viewpoints, campgrounds
     (non-RV — RV is in 5.5's auto-rv-fuel already), playgrounds, dog
     parks, skateparks, picnic areas. Likely 8-12 labels; single-layer
     Google scrape; no Layer-4 verifier (no obvious public registry
     for parks/trails) — likely Option C analog.
  3. `outputs/phase5_6_shopping_grocery_essentials_kickoff.md` — the
     previous phase's runbook. Reads as the structural template the
     5.7 kickoff mirrors. Particularly read §3 (verifier surface —
     Option C pattern that 5.7 will most likely repeat) and §4
     (operator-curated rubric) for pattern continuity.

WORKING PATTERNS TO INTERNALIZE FROM THE 5.6 CLOSE-OUT:

  • Pass dicts directly to JSON-typed SQLAlchemy columns
    (`Entity.crowd_notes`). Do NOT `json.dumps()` first. See 5.3
    `f35d5e4` bug write-up — 5.4, 5.5, and 5.6 all avoided it by
    following this rule from the start.
  • `# noqa: E402` silences E402 only. F401 (unused imports) still
    fails ruff. Audit apply-script imports for unused `json`,
    `Category`, `EntityCategory` before committing — see 5.3
    `bff4a79`. Also watch for F541 (`f"..."` with no placeholders) —
    surfaced once in 5.6 on the audit dump script. Run ruff check
    Windows-side with the project config before commit.
  • Sandbox bash hits a git-index gotcha
    (`fatal: unknown index entry format 0xffff0000`) — use
    `git rev-parse` / `git show HEAD:` for index-free reads. Operator
    runs index-dependent ops (`git status` / `git commit` /
    `git push`) Windows-side via PowerShell.
  • SANDBOX BASH MOUNT STALENESS (5.5 documented this; 5.6 hit it
    TWICE — internalize): after a Read-tool Edit OR an operator-side
    `git restore`, sandbox bash file-shape queries (`wc -l`, `tail`,
    `json.load()`, `importlib`, etc.) may serve a stale view of the
    file for several seconds OR longer. The Read tool is
    AUTHORITATIVE for file state in sandbox; bash file-shape queries
    are unreliable. 5.6 examples: (a) `json.load(scripts/places_
    categories.json)` failed in sandbox with "Unterminated string
    line 203" even after operator's `git restore` brought the file
    back to its proper 211-line shape (Read tool showed the file
    healthy); (b) `importlib` on `app/contrib/google_types_mapping.
    py` reported `SyntaxError: '{' was never closed` while Read tool
    showed the file's `_PRIMARY_TYPE_MAP` definition complete. In
    both cases, the Read tool was correct.
  • DB-write apply-scripts: stop the FastAPI dev server if running
    (`events.db` lock).
  • PowerShell `git commit -m "" ...` footgun: empty `-m ""` between
    multiple `-m "..."` flags is treated as a pathspec by git's flag
    parser. Use multiple `-m "..."` flags WITHOUT empty separators;
    git inserts blank lines between them automatically.
  • `Provider.google_review_snippets` is its OWN COLUMN on Provider
    (per `app/db/models.py:84`, populated by `scripts/places_load.py`
    from the scraper's `review_snippets` emission). NOT inside
    `attributes.google_review_snippets`. The 5.4 close-out §4
    documented this correction; 5.5 and 5.6 used it directly.
  • `scripts/places_categories.json` LOCAL CORRUPTION RECURRENCE
    (NOW THIRD RECURRENCE in 3 sessions): the working tree file has
    been observed to drift from HEAD before every 5.x session since
    5.5. Same exact pattern: working tree 202 lines vs HEAD 211
    lines, ends mid-token `"chil`. Cause still unknown (suspect
    external editor — possibly Word with the
    `~$va_api_catalog.docx` lock file open). Pre-flight item #6 in
    the 5.6 kickoff caught this; the 5.7 kickoff should keep the
    same check. Restore via `git restore scripts/places_categories.
    json` Windows-side.
  • **`_DISCOVERY_DOMAIN_FALLBACK` catch-all behavior (5.6 new
    learning):** the `(None, <domain>)` entry acts as a domain-wide
    second-chance lookup at `places_load.py:348`
    (`_DISCOVERY_DOMAIN_FALLBACK.get((None, domain))`). When you add
    `(None, "<new-domain>"): "<target-slug>"`, you're routing ALL
    unmapped primary_types under that domain to the target slug —
    not just rows with `primary_type=None`. 5.6 routed 27 edge-case
    providers (Hospice, eye-care medical_clinics, B2B manufacturers,
    community garden) to shopping-essentials via this behavior. **5.7
    should anticipate the same** on `outdoor_recreation` — the §2
    edge-case review may surface non-park entities (e.g. parks-and-
    rec offices being civic not place-based, golf courses being
    sport not park, etc.) and may need a similar
    FLIP/DRAFT/KEEP rubric.
  • CI flakiness on intermediate commits: 5.5's `6fb74ac` initially
    showed X red but a rerun went green (transient runner-
    orchestration issue, not code). If a single intermediate commit
    is red on CI, try `gh run rerun <ID>` before shipping a fix
    commit. Final tree-state CI green is the ship-readiness signal.
  • **`medical_clinic` widening soft-edge** (5.4 + 5.6 both flagged
    this): `medical_clinic` is only in `_DISCOVERY_DOMAIN_FALLBACK`
    under `(medical_clinic, "health_medical")`, NOT in
    `app/contrib/google_types_mapping._PRIMARY_TYPE_MAP` directly.
    5.6 §4 surfaced this when 2 medical_clinic eye-care providers
    landed in shopping-essentials via the retail catch-all. A 1-line
    addition to `_PRIMARY_TYPE_MAP` would catch them regardless of
    discovery domain. **If 5.7's outdoor_recreation surface includes
    medical-adjacent entries (e.g. wellness retreats, yoga studios
    in parks), consider doing the `medical_clinic` widening as a
    soft-edge V1.5 patch in the 5.7 lane.**
  • **`entity_type` may be `place` not `commercial` for 5.7** —
    parks, trails, viewpoints, beaches are `place`-typed in the
    Phase 5.2 lake_recreation precedent. Watch the
    `to_entity_payload` caller in places_load for the place-vs-
    commercial distinction. Gate-1 query in the verification script
    should account for `entity_type='place'` correctly (see how
    `outputs/phase5_2_*` handled it).

AFTER YOU READ THE THREE DOCS:

  1. **Author the Phase 5.7 kickoff doc first** —
     `outputs/phase5_7_outdoors_parks_trails_kickoff.md`. Mirror the
     5.6 kickoff shape (§0 pre-flight, §1 scrape sequence, §2 ambig
     audit, §3 verifier options A/B/C, §4 operator rubric, §6
     acceptance gate). Specifics to derive from
     `scripts/places_categories.json` `outdoor_recreation` domain:
     label list, anticipated catch-alls, expected ambig magnitude
     (likely lower than 5.6's 181 because parks have less geo-
     density than retail strip-malls). §6 gate likely 6 items
     mirroring 5.6 (no `is_mobile_service` — parks are place-based,
     not service businesses). Acceptance threshold for gate-1 likely
     ≥20 (parks are fewer in count than retail). Heat_exposure
     default flips to `outdoor` for 5.7 (opposite of 5.6's `indoor`
     default — parks are by definition outdoor surfaces). Author
     this doc + commit it inline before §0 pre-flight dispatches.
  2. Run §0 pre-flight items from the 5.7 kickoff (git log + status
     + alembic + pytest collect + diagnose +
     places_categories.json integrity check + CI status + Google
     Places key + DB spot-check). Expected: pytest=1932 collected;
     CI green on `7609a01`; alembic `0a1b2c3d4e5f`; `outdoors-
     parks-trails` slug present in categories table (id=7);
     places_categories.json clean (no diff vs HEAD).
  3. Surface §0 pre-flight status to the operator. If
     places_categories.json has drifted (likely — fourth recurrence
     pattern), ask operator to restore Windows-side before
     proceeding.
  4. Surface the §3 Layer-4 verifier OPTION decision (A/B/C) — this
     gates the §1 scrape only insofar as the gate item 3 phrasing
     depends on the choice. Operator picks before §1 dispatches.
     Likely Option C analog (no public registry for parks).
  5. Then proceed with §1 scrape (operator dispatches when ready).
     Subsequent gates §2 (ambig + cross-category audit — especially
     against 5.2's lake_recreation cat-6 overlap for waterfront
     parks, plus 5.5's auto-rv-fuel cat-9 for RV-park edges), §3
     (verifier run if Option A/B), §4 (apply-scripts — heat_exposure
     + crowd_notes only, no is_mobile_service for 5.7), §5 (ship
     sequence) follow the 5.6 cadence.

🚨 **Possibly relevant for 5.7 specifically:** the `parks-rec-scrapes`
scheduled CI workflow has been X on cron triggers throughout 5.3 +
5.4 + 5.5 + 5.6. **This workflow is directly relevant to 5.7's
outdoor-recreation scope** (its name suggests so). The 5.6 close-out
§9 flagged it as a "Phase 5.7 should investigate" item. Consider
debugging it as part of 5.7 §0 pre-flight or §1 setup — may shorten
the path to a working data pipeline if it's a stale-but-usable
parks-data ingest.

DO NOT START ANY SCRAPE (`places_discovery` / enrichment / load),
VERIFICATION RUN, OR DB-WRITE APPLY-SCRIPT BEFORE OPERATOR
CONFIRMATION. Each step in the 5.5 + 5.6 lanes gated on a brief
operator review-and-confirm — that pattern caught real issues
mid-session (places_categories.json corruption surfaced at §0,
fallback layer needed at first load surfacing 18/21 operator-queue
rows in 5.5/5.6, the 27-row catch-all routing review in 5.6, the 2
missed medical_clinic flips in 5.6 §4 top-10 sweep, etc.). Continue
the cadence.

When you're confident you've understood the three docs end-to-end
AND authored the 5.7 kickoff doc, propose your §0 pre-flight
execution plan to the operator + surface the §3 Layer-4 verifier
OPTION choice as the second decision point, and wait for go-ahead.
