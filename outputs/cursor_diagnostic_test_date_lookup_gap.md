# Cursor diagnostic dispatch — `test_date_lookup_gap_includes_contribute` failure

> **Type:** investigation / diagnostics. **NOT** an implementation dispatch. Do not modify production code or commit anything. Read-only investigation with one pinned-test rerun pattern. Report findings to the operator; the operator decides whether to fix.
>
> **Authored by:** Cowork primary, 2026-05-20 / 21 post-Phase-8a-ship.
>
> **Origin/main tip at dispatch:** `8a905c6` (feat(phase8a)). Verify at boot.
>
> **Status:** time-boxed diagnostic, ~30-45 min. Hand off findings; let operator route fix.

---

## §0 Boot prereqs

Verify before starting:

1. `git log --oneline -3` — top should show `8a905c6` (Phase 8a). If older, halt and ask the operator.
2. `git status --short` — should be clean (no uncommitted changes).
3. `python -m alembic current` — should show `d8e9f0a1b2c3 (head)`. If error, halt and surface to operator.
4. **Reproduce the failure deterministically** before investigating:
   ```powershell
   python -m pytest tests/test_gap_template_contribute_link.py::test_date_lookup_gap_includes_contribute -x --tb=long
   ```
   Expected: FAIL with assertion against `"Closest match in the catalog is City Events. Ask again with that name, or /contribute can add a different listing."` instead of a gap-template tail.
   - If it PASSES on this isolated run → it's a test-ordering flake. Note that and proceed to §1.b (test isolation investigation).
   - If it FAILS deterministically → proceed to §1.a (routing investigation).

---

## §1 Investigation paths

### §1.a Routing investigation (if failure is deterministic in isolation)

The actual response is the **Phase 7.5.1 near-match dym** template ("Closest match in the catalog is X. Ask again with that name, or /contribute can add a different listing."), which means `near_match_subject_overlaps()` returned True and the router took the dym branch instead of the gap-template branch.

Read:

- `tests/test_gap_template_contribute_link.py` — the failing test. Understand the query string + the expected `_GAP_TAIL` assertion.
- `app/chat/entity_intent.py` — find `near_match_subject_overlaps()` (Phase 7.5.1 rewrite at line ~245-257 with content-token check + `_CATEGORY_TOKENS` stoplist + rapidfuzz typo escape hatch at partial_ratio≥80). Trace why the test query reaches this function and returns True.
- `app/chat/entity_intent.py` lines 89-93 (`_FAKE_ENTITY_MARKER_RE`) + 141 (`query_mentions_fake_entity_marker`) + 245-257 (rapidfuzz escape hatch).
- `app/chat/unified_router.py` lines 113-119 + 122-125 (`_ABOUT_GATE_STRICT_PATTERNS` + `_WHAT_IS_ENTITY_RE`), 282-302 (`_unknown_entity_about_gate`), the dym branch (grep for "Closest match in the catalog").
- The dev DB: query for entities matching "City Events" or any city/event combination. Use Python to inspect:
  ```python
  from app.db.database import SessionLocal
  from app.db.models import Entity
  with SessionLocal() as db:
      rows = db.query(Entity).filter(Entity.name.ilike('%city%event%')).all()
      print([(e.id, e.slug, e.name, e.entity_type) for e in rows])
  ```

**Diagnostic questions to answer in your report:**

1. What is the exact query string the failing test sends?
2. Is there an entity in the dev DB whose `name` fuzzy-matches that query via `near_match_subject_overlaps()`?
3. Does the router invocation path return the dym branch because:
   - (a) The rapidfuzz escape hatch at `partial_ratio ≥ 80` fires when it shouldn't (too-loose threshold for this query shape)
   - (b) The content-token check + stoplist let this query through when it should have been rejected
   - (c) The dev DB has a contaminated entity that shouldn't be there
   - (d) Something else
4. Would this query produce the same dym response on prod's catalog? (Quick PowerShell probe: `Invoke-RestMethod -Method Post -Uri "https://havasu-chat-production.up.railway.app/api/chat" -ContentType "application/json" -Body '{"query":"<the exact test query>"}'`)
5. Is the right fix:
   - Update the test to expect the dym response (if the routing is correct and the test was over-pinned)?
   - Tighten `near_match_subject_overlaps()` thresholds (if the routing is too eager)?
   - Remove the City Events entity from dev fixtures (if it's a dev-DB-only artifact)?
   - Something else?

### §1.b Test isolation investigation (if failure is order-dependent)

If the test passes in isolation but fails in the full sweep, the cause is test ordering / shared state.

Read:

- `tests/conftest.py` — any session-scoped fixtures that could mutate the DB.
- `tests/test_gap_template_contribute_link.py` — does it have transactional rollback? Or does it run against a persistent dev DB?
- Look for tests that run BEFORE `test_date_lookup_gap_includes_contribute` in the alphabetical or pytest-collected order that could add a "City Events" entity to the DB (search `tests/` for `City Events` literal):
  ```powershell
  Select-String -Path "tests\*.py" -Pattern "City Events"
  ```

Document the failure-inducing predecessor test if found.

---

## §2 Out-of-scope hard rules

- **Do NOT modify `app/chat/entity_intent.py`, `app/chat/unified_router.py`, or `app/db/models.py`.** This is a diagnostic, not a fix.
- **Do NOT modify any test files.** If your diagnosis suggests a test needs updating, propose the change in your report — operator decides.
- **Do NOT modify the dev DB.** No `db.add`, no `db.commit`, no seed-data changes. Read-only DB inspection only.
- **Do NOT commit anything.**
- **Do NOT investigate Phase 8a code or wiring.** This failure is in the 7.5.3 / 7.5.1 surface. Phase 8a is healthy on prod.
- **Do NOT spend more than 45 minutes.** If the cause isn't clear by then, surface what you've found and recommend whether a deeper investigation is needed.

---

## §3 Report format

When done, produce a §3 report with:

1. **Failure determinism verdict:** deterministic / flaky-on-order / unknown (with evidence).
2. **Root cause hypothesis:** one paragraph with concrete code citations.
3. **Recommended fix:** one of (a) update test pin / (b) tighten near-match thresholds / (c) update dev fixtures / (d) further investigation needed. Be specific with file paths + line numbers + the change you'd propose.
4. **Severity:** is this a real bug that could manifest on prod, or a test-only / dev-only artifact?
5. **Prod check result:** the PowerShell probe of the test query against prod, and what it returned.
6. **Time spent:** how long the investigation took.

Do NOT apply the fix. Hand off to operator.

---

## §4 Background (for context)

- Phase 7.5.1 (commit `fd695d2`, 2026-05-19) rewrote `near_match_subject_overlaps` from fail-open to content-token check + `_CATEGORY_TOKENS` stoplist + rapidfuzz typo escape hatch. Closed q22 ("rating for Fabricated Hotel Name 555" → no longer surfaces real Heat Hotel entity).
- Phase 7.5.3 (commit `ac7c2fc`, 2026-05-20) tightened 7 `/contribute` substring assertions to full-template equality via `_GAP_TAIL` constant + `tier_used == "gap_template"` check. F4 polish lane. The 7.5.3 §12 reported 21/21 PASS on `test_gap_template_contribute_link.py` + `test_phase38_gap_and_hours.py`.
- Phase 7.7 (commit `eb489a7`) added the honest-empty tier-2 template at `tier2_handler.py`. Unrelated to this failure surface but the lane that surfaced multiple environment-conditional failures.
- Phase 8a (commit `8a905c6`, just shipped) added conditions + alerts + chat live-conditions wiring at `unified_router.py:846`. Should NOT affect routing for date-lookup queries; the wiring only adjusts `chat_ctx.temperature_f` for ranking. **Verify Phase 8a is not the cause** by reading the diff at unified_router.py around line 846 — if the chat-live-conditions wiring affects entity matching or near-match logic somehow, that's the bug.

The pre-8a-ship `test_gap_template_contribute_link.py` was PASSING per Phase 7.5.3's §12 report (21 passing including parametrized). Post-8a-ship, this test is now FAILING with a near-match dym response. The hypothesis is: either Phase 8a's unified_router.py edit unexpectedly affects this path, OR the dev DB drifted between Phase 7.5.3's verification and now.

---

## §5 First step

After §0 boot prereqs verify, your first action is to run the failing test in isolation and report:

- Is the assertion failure deterministic (same response on every run)?
- What is the exact query string sent + the exact response received?

Then drill into §1.a or §1.b based on the determinism verdict.

---

*Authored 2026-05-20 / 21 post-Phase-8a-ship. Time-boxed at 45 min. Saved to `outputs/cursor_diagnostic_test_date_lookup_gap.md`.*
