# Phase 5.6 next-agent boot prompt

> **What this is:** a single paste-and-go briefing for the operator to
> drop into a fresh Cowork chat to start the Phase 5.6 (Shopping,
> Grocery & Essentials) session. Mirrors the shape of
> `outputs/phase5_5_next_agent_boot_prompt.md` that started Phase 5.5.
>
> **How to use:** paste everything between the `>>> BEGIN` and `<<< END`
> markers below into the first user message of a new Cowork chat. The
> agent will read the three referenced docs, run §0 pre-flight, surface
> the results, and wait for your go-ahead before starting any work.

---

## Paste the block below into a fresh Cowork chat

```
>>> BEGIN BOOT PROMPT (Phase 5.6 — Shopping, Grocery & Essentials) >>>

You're picking up Phase 5.6 (Shopping, Grocery & Essentials) from
scratch. Nothing shipped yet for 5.6 — this is the kickoff session.
Phase 5.5 (Auto, RV & Fuel) SHIPPED on origin at 08d5ff3 (2026-05-16)
with all 7 gate items cleared and CI green. Top of origin/main is
08d5ff3 (or later if the Phase 6 lane shipped Amendment 5 between
sessions — check git log -3 first).

Working directory: C:\Users\casey\projects\havasu-chat (Windows-side
operator env); sandbox bash mounts under
/sessions/.../mnt/havasu-chat/.

READ THESE THREE DOCUMENTS END-TO-END BEFORE DOING ANYTHING ELSE, IN
THIS ORDER:

  1. outputs/phase5_5_session_closeout.md — the close-out for the
     prior Phase 5.5 session. §1 has the 4-commit lane chain
     7c96ec9 → 08d5ff3. §3 lists the surgical fix shipped
     mid-session (4d41944 _DISCOVERY_DOMAIN_FALLBACK extension for
     'auto' domain). §3 also documents the sandbox-bash MOUNT-STALENESS
     gotcha (Read tool is authoritative for file state; never trust
     sandbox bash wc -l / tail for post-Edit verification — the 5.5
     session had a false-alarm where a properly-applied Edit appeared
     to truncate a file but was actually fine). §5 has the
     sustainability matrix.

  2. outputs/phase5_6_shopping_grocery_essentials_kickoff.md — THE
     runbook for Phase 5.6. §0 pre-flight (note the NEW item #6 — git
     diff scripts/places_categories.json must be empty; this file
     corrupted locally twice in the 5.5 session); §1 scrape sequence
     (23 labels in the 'retail' discovery domain — larger than 5.5's
     14); §2 ambiguous-queue review (including special audit for gas
     station/convenience store cross-list against 5.5's auto-rv-fuel
     loads); §3 Layer-4 verifier surface OPTIONS (A: AZ TPT
     transaction-privilege-tax license Playwright build, B: BBB
     cross-reference, C: defer to V1.5 — operator picks); §4
     operator-curated field-entry rubric (heat_exposure + crowd_notes
     — NOTE: is_mobile_service is NOT a 5.6 gate item, retail is
     brick-and-mortar by definition); §6 acceptance gate (6 items not
     7).

  3. outputs/phase5_5_auto_rv_fuel_kickoff.md — the previous phase's
     runbook. Reads as the structural template the 5.6 kickoff
     mirrors. Particularly read §3 (verifier surface — Option C
     pattern that 5.6 will most likely repeat) and §4 (operator-
     curated rubric) for pattern continuity.

WORKING PATTERNS TO INTERNALIZE FROM THE 5.5 CLOSE-OUT:

  • Pass dicts directly to JSON-typed SQLAlchemy columns
    (Entity.crowd_notes). Do NOT json.dumps() first. See 5.3 f35d5e4
    bug write-up — 5.4 and 5.5 both avoided it by following this rule
    from the start.

  • # noqa: E402 silences E402 only. F401 (unused imports) still
    fails ruff. Audit apply-script imports for unused 'json',
    'Category', 'EntityCategory' before committing — see 5.3 bff4a79.
    Run ruff check Windows-side with the project config before commit.

  • Sandbox bash hits a git-index gotcha
    (`fatal: unknown index entry format 0xffff0000`) — use
    git rev-parse / git show HEAD: for index-free reads. Operator
    runs index-dependent ops (git status / git commit / git push)
    Windows-side via PowerShell.

  • 🚨 SANDBOX BASH MOUNT STALENESS (new in 5.5): after a Read tool
    Edit, sandbox `wc -l` / `tail` / file-size queries may serve a
    stale view of the file for several seconds. The Read tool is
    authoritative; never use sandbox bash for post-Edit verification.
    If bash says a file is truncated but you just edited it via the
    Read/Edit tools, use the Read tool to confirm BEFORE asking the
    operator to restore.

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
    documented this correction; 5.5 used it directly.

  • 🚨 scripts/places_categories.json LOCAL CORRUPTION RECURRENCE:
    the working tree file has been observed to drift from HEAD twice
    in the 5.5 session — working tree 202 lines vs HEAD 211 lines,
    ends mid-token `"chil`. Cause unknown (suspect external editor —
    possibly Word with the ~$va_api_catalog.docx lock file open, or
    similar). The §0 pre-flight item #6 in the 5.6 kickoff requires
    `git diff scripts/places_categories.json` to be empty BEFORE §1;
    restore via `git restore scripts/places_categories.json` if
    drifted.

  • CI flakiness on intermediate commits: 5.5's 6fb74ac (audit + apply
    commit) initially showed X red but a rerun went green; root cause
    was transient (`gh run view --log-failed` returned empty, suggesting
    runner-orchestration not code). If a single intermediate commit is
    red on CI, try `gh run rerun <ID>` before shipping a fix commit.
    Final tree state CI green is the ship-readiness signal.

AFTER YOU READ THE THREE DOCS:

  1. Run §0 pre-flight items from the 5.6 kickoff (git log + status +
     alembic + pytest collect + diagnose + places_categories.json
     integrity check + CI status + Google Places key + DB spot-check).
     Expected: pytest=1920 collected; CI green on 08d5ff3; alembic
     0a1b2c3d4e5f; shopping-essentials slug present in categories
     table; places_categories.json clean (no diff vs HEAD).

  2. Surface §0 pre-flight status to the operator. If
     places_categories.json has drifted, ask operator to restore
     Windows-side before proceeding.

  3. Surface the §3 Layer-4 verifier OPTION decision (A/B/C) — this
     gates the §1 scrape only insofar as the gate item 3 phrasing
     depends on the choice. Operator picks before §1 dispatches.

  4. Then proceed with §1 scrape (operator dispatches when ready).
     Subsequent gates §2 (ambig + cross-category cat-8/cat-9 audit),
     §3 (verifier run if Option A/B), §4 (apply-scripts — heat_exposure
     + crowd_notes only, no is_mobile_service for 5.6), §5 (ship
     sequence) follow the 5.5 cadence.

DO NOT START ANY SCRAPE (places_discovery / enrichment / load),
VERIFICATION RUN, OR DB-WRITE APPLY-SCRIPT BEFORE OPERATOR
CONFIRMATION. Each step in the 5.5 lane gated on a brief operator
review-and-confirm — that pattern caught real issues mid-session
(places_categories.json corruption surfaced at §0, fallback layer
needed at first load surfacing 18 operator-queue rows, etc.).
Continue the cadence.

When you're confident you've understood the three docs end-to-end,
propose your §0 pre-flight execution plan to the operator + surface
the §3 Layer-4 verifier OPTION choice as the second decision point,
and wait for go-ahead.

<<< END BOOT PROMPT >>>
```

---

## Operator notes (NOT pasted into the chat)

- **Decision to make early:** §3 Layer-4 verifier OPTION (A vs B vs
  C). Recommended C (defer to V1.5) mirroring 5.5's choice unless you
  want symmetry with 5.3 + 5.4's verifier-surface pattern. Option A
  (AZ TPT) is ~3-5 hours of build if you want it; the AZDOR search UI
  is more complex than AZ ROC.
- **Phase 6 lane:** if you opted to land Amendment 5 (Phase 5.5
  SHIPPED ledger) in-line at the end of the 5.5 session per the
  `0addb63` precedent, the top of `git log` will show that commit
  above `08d5ff3` and the next agent's pre-flight will reflect it. If
  you instead deferred Amendment 5 to a Claude Code parallel dispatch
  during the 5.6 session, surface that to the next agent when the §0
  pre-flight surfaces the unexpected top-commit.
- **Pre-flight integrity check (NEW in 5.6):** `git diff
  scripts/places_categories.json` MUST be empty. If you've recently
  had Word open editing `hava_api_catalog.docx` (which left a
  `~$va_api_catalog.docx` lock file in the working tree), check
  whether that's coincident with the places_categories.json
  corruption — the cause was never identified in 5.5 but the lock
  file's presence pattern-matches.
- **Pre-flight expected results** (you can verify Windows-side first
  if you want to know before pasting the prompt):
  - `git log --oneline -3` → top should be `08d5ff3` (Phase 5.5
    SHIPPED) or an Amendment-5 commit on top.
  - `python -m pytest -q --collect-only 2>&1 | tail -3` → 1920
    collected.
  - `gh run list --branch main --limit 3` → ✓ on `08d5ff3` (post
    rerun) + `6fb74ac` + `4d41944`.
  - `git diff scripts/places_categories.json` → empty.

---

*Authored by Cowork primary, Phase 5 lane, end of Phase 5.5 session
(2026-05-16) post-`08d5ff3`. Operator pastes the BEGIN/END block
above into a fresh Cowork chat to start Phase 5.6.*
