# Phase 5.5 next-agent boot prompt

> **What this is:** a single paste-and-go briefing for the operator to
> drop into a fresh Cowork chat to start the Phase 5.5 (Auto, RV &
> Fuel) session. Mirrors the shape of the boot prompt that started
> the Phase 5.4 session (which kicked off at `outputs/phase5_4_session_midpoint_checkpoint.md`
> + `outputs/phase5_3_session_closeout.md` + the 5.4 kickoff).
>
> **How to use:** paste everything between the `>>> BEGIN` and `<<< END`
> markers below into the first user message of a new Cowork chat. The
> agent will read the three referenced docs, run §0 pre-flight, surface
> the results, and wait for your go-ahead before starting any work.

---

## Paste the block below into a fresh Cowork chat

```
>>> BEGIN BOOT PROMPT (Phase 5.5 — Auto, RV & Fuel) >>>

You're picking up Phase 5.5 (Auto, RV & Fuel) from scratch. Nothing
shipped yet for 5.5 — this is the kickoff session. Phase 5.4
(Health, Wellness & Care) SHIPPED on origin at c13dfff (2026-05-16);
close-out doc at a9a680a. Top of origin/main is a9a680a (or later if
the Phase 6 lane shipped Amendment 4 between sessions). All CI green
on a9a680a.

Working directory: C:\Users\casey\projects\havasu-chat (Windows-side
operator env); sandbox bash mounts under
/sessions/.../mnt/havasu-chat/.

READ THESE THREE DOCUMENTS END-TO-END BEFORE DOING ANYTHING ELSE, IN
THIS ORDER:

  1. outputs/phase5_4_session_closeout.md — the close-out for the
     prior Phase 5.4 session. §1 has the 12-commit lane chain
     ef23456 → c13dfff. §3 lists the 5 surgical fixes shipped
     mid-session (note especially the JSON-column gotcha avoidance
     vs 5.3 f35d5e4 + the F401 footgun guard vs 5.3 bff4a79). §4 has
     the source-of-truth correction (Provider.google_review_snippets
     is its OWN COLUMN, not inside attributes JSON). §5 has the
     sustainability matrix.

  2. outputs/phase5_5_auto_rv_fuel_kickoff.md — THE runbook for
     Phase 5.5. §0 pre-flight; §1 scrape sequence (14 labels in the
     'auto' discovery domain); §2 ambiguous-queue review (including
     the special RV cross-list audit against 5.2's lake_recreation
     loads); §3 Layer-4 verifier surface OPTIONS (A: AZ MVD Dealer
     Locator Playwright build, B: AZCC towing carrier REST, C: defer
     to V1.5 — operator picks); §4 operator-curated field-entry
     rubric (is_mobile_service + heat_exposure + crowd_notes); §6
     acceptance gate.

  3. outputs/phase5_4_health_wellness_care_kickoff.md — the previous
     phase's runbook. Reads as the structural template the 5.5
     kickoff mirrors. Particularly read §3 (verifier surface — NPI
     verifier built at 5d429aa) and §4 (operator-curated rubric) for
     pattern continuity.

WORKING PATTERNS TO INTERNALIZE FROM THE 5.4 CLOSE-OUT:

  • Pass dicts directly to JSON-typed SQLAlchemy columns
    (Entity.crowd_notes). Do NOT json.dumps() first. See 5.3 f35d5e4
    bug write-up — 5.4 avoided it by following this rule from the
    start.

  • # noqa: E402 silences E402 only. F401 (unused imports) still
    fails ruff. Audit apply-script imports for unused 'json',
    'Category', 'EntityCategory' before committing — see 5.3 bff4a79.

  • Sandbox bash hits a git-index gotcha
    (`fatal: unknown index entry format 0xffff0000`) — use
    git rev-parse / git show HEAD: for index-free reads. Operator
    runs index-dependent ops (git status / git commit / git push)
    Windows-side via PowerShell.

  • DB-write apply-scripts: stop the FastAPI dev server if running
    (events.db lock).

  • PowerShell `git commit -m "" ...` footgun: empty -m "" between
    multiple -m "..." flags is treated as a pathspec by git's flag
    parser. Use multiple -m "..." flags WITHOUT empty separators;
    git inserts blank lines between them automatically.

  • Provider.google_review_snippets is its OWN COLUMN on Provider
    (per app/db/models.py:84, populated by scripts/places_load.py:146
    from the scraper's review_snippets emission at
    app/contrib/google_places_scraper.py:464). NOT inside
    attributes.google_review_snippets. The 5.4 close-out §4
    documented this correction.

AFTER YOU READ THE THREE DOCS:

  1. Run §0 pre-flight items from the 5.5 kickoff (git log + status +
     alembic + pytest collect + CI status + diagnose_category_id_gap +
     Google Places key check). Expected: pytest=1909 collected; CI
     green on a9a680a; alembic 0a1b2c3d4e5f; auto-rv-fuel slug
     present in categories table.

  2. Surface §0 pre-flight status to the operator.

  3. Surface the §3 Layer-4 verifier OPTION decision (A/B/C) — this
     gates the §1 scrape only insofar as the gate item 3 phrasing
     depends on the choice. Operator picks before §1 dispatches.

  4. Then proceed with §1 scrape (operator dispatches when ready).
     Subsequent gates §2 (ambig + RV cross-list audit), §3 (verifier
     run if Option A/B), §4 (apply-scripts), §5 (ship sequence) follow
     the 5.4 cadence.

DO NOT START ANY SCRAPE (places_discovery / enrichment / load),
VERIFICATION RUN, OR DB-WRITE APPLY-SCRIPT BEFORE OPERATOR
CONFIRMATION. Each step in the 5.4 lane gated on a brief operator
review-and-confirm — that pattern caught real issues mid-session
(ZIP+4 false-drop at b683ad7, rapidfuzz 3.x case-fix at fbdd002,
subset false-positive at 700fa3f). Continue the cadence.

When you're confident you've understood the three docs end-to-end,
propose your §0 pre-flight execution plan to the operator + surface
the §3 Layer-4 verifier OPTION choice as the second decision point,
and wait for go-ahead.

<<< END BOOT PROMPT >>>
```

---

## Operator notes (NOT pasted into the chat)

- **Decision to make early:** §3 Layer-4 verifier OPTION (A vs B vs
  C). Recommended C (defer to V1.5) unless you want symmetry with 5.3
  + 5.4's verifier-surface pattern; Option A is ~2-4 hours of build
  if you want it.
- **Phase 6 lane:** This boot prompt does NOT dispatch a parallel
  Phase 6 amendment — Phase 5.4 SHIPPED ledger lines landed in-line
  this session (master plan + STATE.md edits at the 5.4 close-out
  commit). The next Phase 6 amendment (Amendment 5 — Phase 5.5
  SHIPPED ledger) will be authored at the end of the 5.5 session,
  not at the start.
- **Pre-flight expected results** (you can verify Windows-side first
  if you want to know before pasting the prompt):
  - `git log --oneline -3` → top should be `a9a680a` (Phase 5.4
    close-out) or a Phase 6 amendment commit on top.
  - `python -m pytest -q --collect-only 2>&1 | tail -3` → 1909
    collected.
  - `gh run list --branch main --limit 3` → ✓ on `a9a680a` and
    `c13dfff`.

---

*Authored by Cowork primary, Phase 5 lane, end of Phase 5.4 session
(2026-05-16) post-`a9a680a`. Operator pastes the BEGIN/END block
above into a fresh Cowork chat to start Phase 5.5.*
