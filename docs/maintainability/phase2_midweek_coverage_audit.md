# Phase 2 first-week — midweek coverage audit (#50 / #51 / #55)

**Audit date:** 2026-05-10
**Production HEAD at audit:** `df612d4`
**Pytest baseline:** 1377 passed
**Audit lane:** read-only retrospective; no code, test, or `docs/BACKLOG.md` modifications.
**Premise:** each of the three lanes that shipped 2026-05-09 wrote its own tests; this is the second-pair-of-eyes pass for coverage gaps + code observations, ranked by risk. A no-fix audit doc — any concrete follow-up tickets are listed in §"Recommended follow-ups" but **not** filed.

**Git wrinkle (per task brief):** `79f7396` carries the `feat(matcher): #50 add ≥3-char minimum-length floor` commit message but its diff is the #51 doc patch (matches `b361526`). `f9e9b06` is the actual #50 code+test commit. The audit reads code from working-tree state (= prod HEAD `df612d4`); SHAs in this doc are anchored to *content*, not commit-message labels.

---

## Ticket #55 — `confidence_tier._KNOWN_METHODS` extension for Lane 3 operator vocab

**Ship SHA:** `847f79a` (Cursor; 2026-05-09)
**Files audited:**
- `app/chat/confidence_tier.py` — added 4 `METHOD_*` constants (`phone_call`, `in_person`, `web_form_submission`, `email_confirmation`), `_OPERATOR_VOCAB_METHODS` tuple, and extended HIGH (line 271–277) and MEDIUM (line 287–302) bands.
- `tests/test_confidence_tier.py` — 21 net-new across 5 parameterized classes + 1 lock-step test.

**Existing test coverage:** 31 tests total in the file post-#55; the operator-vocab block is `tests/test_confidence_tier.py:104–169` (5 parameterized × 4 methods = 20 cases + 1 lock-step). Coverage:
- Recognition (not "unknown method") at age 5 — `test_operator_vocab_recognized_not_unknown`
- HIGH at age 5 with rationale string — `test_operator_vocab_high_within_30_days`
- HIGH at the 30-day boundary — `test_operator_vocab_high_at_30_day_boundary`
- MEDIUM at age 60 with rationale string — `test_operator_vocab_medium_31_to_90_days`
- LOW at age 120 with `"older than threshold"` rationale (the regression #55 guards) — `test_operator_vocab_low_past_90_days`
- Lock-step `_KNOWN_METHODS` ⊇ `_OPERATOR_VOCAB` — `test_KNOWN_METHODS_covers_full_operator_vocab`

### Coverage gaps identified

1. **MEDIUM-band 90-day inclusive boundary is untested for operator vocab AND for `manual`/`owner_confirmed`/`npi_registry`.** — MEDIUM. `test_operator_vocab_medium_31_to_90_days` hits age 60; the inclusive `≤ 90` cutoff at `confidence_tier.py:295` (`_MEDIUM_TRUSTED_DAYS = 90`) has no parametrized test at exactly 90 nor at 91. `test_medium_manual_31_to_90_days` (line 183) also picks 60. A future threshold tweak (e.g. tightening to 89) would slip through silently. **Suggested:** parametrize at age 90 (MEDIUM expected) and age 91 (LOW expected) for both legacy `manual`/`owner_confirmed`/`npi_registry` and the four operator-vocab values.

2. **`last_verified_at = None` interaction with the new methods is untested.** — MEDIUM. `test_low_no_verification_record` (line 194) only uses `verification_method="manual"`. The early-return at `confidence_tier.py:215–221` is method-agnostic, so the operator-vocab values *should* hit "no verification record" — but no parametrized test pins it. If a future refactor moves the no-`last_verified_at` branch *below* the method dispatch, only the `manual` case would catch the regression. **Suggested:** parametrize `test_low_no_verification_record` over `_OPERATOR_VOCAB`.

3. **Lock-step test is one-directional and uses a *test-local* fixture tuple, not the prod tuple.** — MEDIUM. `tests/test_confidence_tier.py:105–110` defines a local `_OPERATOR_VOCAB` and `test_KNOWN_METHODS_covers_full_operator_vocab` (line 164) iterates over the local copy. If a future migration adds (e.g.) `text_message` to `confidence_tier._OPERATOR_VOCAB_METHODS` but the test fixture isn't updated, the new value gets zero parametrized coverage and the lock-step still passes. **Suggested:** assert `tuple(sorted(ct._OPERATOR_VOCAB_METHODS)) == tuple(sorted(_OPERATOR_VOCAB))` so any drift between prod and test fixtures is loud.

4. **MEDIUM-band rationale string is parametrized but legacy-method MEDIUM rationale is asserted only once.** — LOW. `test_operator_vocab_medium_31_to_90_days` asserts `rationale == "verified within 90 days"`, but the legacy `test_medium_manual_31_to_90_days` (line 183) asserts only the tier and age, not the rationale. If a refactor splits the unified MEDIUM rationale per trust class, half the existing tests miss it. **Suggested:** belt-and-suspenders rationale assertions on the legacy MEDIUM tests.

5. **No `hedge_phrase()` integration test on records that classify via the operator-vocab path.** — LOW. `hedge_phrase` reads only the tier enum, so the integration is structurally safe — but the *combination* (operator-vocab record → tier → hedge fragment) has no test. Acceptable gap given the abstraction boundary; document why.

### Edge cases not tested

1. **Future-dated `last_verified_at` (negative `age_days`).** Clock skew or a bad timezone offset could make `now - last_verified_at` negative. `confidence_tier.py:240` (and every age-gated branch) tests `age <= _HIGH_OWNER_DAYS`, which is true for negative ages → record lands in HIGH with `age_days=-N`. Not a regression introduced by #55 but the new operator-vocab branch (line 271) inherits the same behavior with no test pin.
2. **Empty-string method (`verification_method = ""`).** Not `None`, not `"none"`, not in `_KNOWN_METHODS` → falls through to "unknown verification method" LOW branch. Untested for any method, including the new ones.
3. **Casing/whitespace variations (`"Phone_Call"`, `" phone_call "`, `"PHONE_CALL"`).** Treated as unknown methods. Probably correct (DB CHECK constraint enforces canonical casing) but no test pins this assumption — a downstream code path that constructs records from operator UI input could regress.
4. **Method missing AND `last_verified_at` missing simultaneously.** `test_classify_defensive_on_object_without_fields` (line 246) covers a record with no attrs at all; but a record with `last_verified_at=None` AND `verification_method=None` (both explicit None, not absent) is exercised only via `test_assessment_carries_age_days_none_for_unverified` (line 269) which doesn't exercise the new methods.

### Code observations

1. **MEDIUM rationale `"verified within 90 days"` (line 301) is generic across `manual` / `owner_confirmed` / `npi_registry` / operator-vocab.** Defensible — these all share one trust band — but if the spec ever distinguishes operator-trust MEDIUM from owner-trust MEDIUM in voice copy, the rationale string is the natural place. Worth a forward-looking comment.
2. **`_KNOWN_METHODS` (line 81–89) builds the frozenset from `*_OPERATOR_VOCAB_METHODS`.** This is the right idiom — adding to the tuple auto-extends the frozenset — but means the lock-step test's value-add is mostly bug-finding for *out-of-band* additions (e.g., someone adds a string directly to `_KNOWN_METHODS` without touching the tuple). A test asserting the inverse (`set(_KNOWN_METHODS) - set(legacy methods) == set(_OPERATOR_VOCAB_METHODS)`) would close that loop.
3. **Hedge constants `_HEDGE_HIGH = ""`, `_HEDGE_MEDIUM`, `_HEDGE_LOW` (line 123–125) are module-private and not used outside `hedge_phrase`.** No coverage concern, just noting that the prose values are not exposed for spec verification — `test_hedge_phrase_*` re-derives them through the function, which is the right scope.
4. **Lane 3 / P2.BL.45 is referenced inline (line 65, 268, 270) but no link to the migration revision (`c5d6e7f8a9b0`).** Test file links it at `tests/test_confidence_tier.py:96`; production code only mentions it by lane name. Minor doc-loop gap.

### Verdict: APPROVED

Coverage is solid for the boundary cases the lane explicitly targets (HIGH/MEDIUM/LOW × 4 methods × age points). The gaps are real but secondary — most concern *future-proofing* against drift (lock-step direction, 90-day boundary, prod-vs-test-fixture symmetry) rather than gaps in what shipped. No production-relevant edge case is uncovered; no actual bug. Recommend filing the lock-step-symmetry follow-up before the next migration adds a fifth operator-vocab method.

---

## Ticket #51 — UTF-8 charset patches in PowerShell smoke snippets

**Ship SHA:** `b361526` (content) / `79f7396` (committed under #50's message — git wrinkle, see header).
**Files audited:**
- `docs/maintainability/backlog_46_smoke_check_queries.md` (the "Why `; charset=utf-8`" callout at line 13).
- `docs/maintainability/phase1_deploy_runbook.md` (5 snippets at lines 251, 368, 429, 439, 449 — every `Invoke-RestMethod` to `/api/chat` now carries `; charset=utf-8`).
- `docs/maintainability/phase2_first_week_dispatch.md` (1 snippet at line 26).

**Existing test coverage:** none added (doc-only ship). Pre-existing coverage adjacent to the issue:
- `tests/test_chat_route_audience_forwarding.py:12` — POSTs ASCII body via `TestClient(app)`, asserts 200. Doesn't exercise UTF-8 vs latin-1 vs Win-1252.
- `tests/test_entity_matcher_adversarial.py` — exercises Class A/B/C/D smoke catalog patterns but on the matcher, not over HTTP.
- The graded voice-battery JSONL files include some ASCII Mudshark queries, but no accented input.

### Coverage gaps identified

1. **No automated regression test for the wire-level encoding behavior.** — HIGH (most material risk in this audit). The fix is documented in five PowerShell snippets — *if a future maintainer copy-pastes the smoke snippet without the `; charset=utf-8` clause, the regression returns silently for accented queries.* No `tests/test_chat_route_*` test exercises (a) accented query + UTF-8 → 200, (b) accented bytes labeled as latin-1/Win-1252/no-charset → Starlette 400. The TestClient repro CC ran in-conversation should have become a permanent test. **Suggested:** new `tests/test_chat_route_utf8.py` with four cases mirroring CC's matrix (UTF-8 → 200, latin-1 → 400, Win-1252 → 400, ASCII → 200). Use `client.post("/api/chat", content=..., headers={"Content-Type": "..."})` to control the wire bytes precisely.
2. **The smoke catalog's E3 case (`múdshärk bréwery`, line 97) gives "Match OR safely None" as expected behavior.** — MEDIUM. The class-E framing pre-dates #51's fix and suggests accent handling is "orthogonal — file separate bugs." Post-#51, the wire-level path is fixed but the matcher-side accent-folding question is still open. Acceptable gap *for #51's scope* — it's a #46-class concern — but the smoke catalog now references "#51 close-out" without specifying whether E3 is meant to verify the wire-level fix or the matcher. **Suggested:** add a parenthetical to E3 clarifying it tests the matcher path (wire-level is now precondition-met by the `; charset=utf-8` clause at line 9–11).
3. **No CI lint guard against new PowerShell snippets in `docs/` that POST to `/api/chat` without `; charset=utf-8`.** — LOW. Five out of six total snippets in the runbook now carry the clause; if a sixth snippet is added in a future ship, there's no automated check. Probably overkill for a single doc convention; flag as nice-to-have.
4. **No test verifies the exact 400 response body shape (`{"detail":"There was an error parsing the body"}`).** — LOW. The runbook callout at `backlog_46_smoke_check_queries.md:13` quotes that exact body as the failure signature. If Starlette's error message changes in a future version, the doc will mislead operators trying to diagnose. Acceptable gap; document Starlette version dependency.

### Edge cases not tested (would be tested by the suggested new file)

1. Accented query with `Content-Type: application/json` (no charset) — depends on Starlette default; should also 400 if PowerShell defaults bite.
2. Accented query as raw UTF-8 bytes with `Content-Type: application/json; charset=utf-8` — happy path, 200.
3. Accented query as latin-1-encoded bytes with `Content-Type: application/json; charset=latin-1` — fails (server can't decode as JSON).
4. Mojibake in the catalog (`múdshärk` typed as latin-1 but labeled as UTF-8) — should be a different-failure mode (matcher returns no match), not a 400.
5. Other Windows-1252 source paths: clipboard paste from Word, Outlook signatures, etc. — operationally relevant to the smoke harness but out of scope for an automated test.

### Code observations

1. **No production code changed.** This is a client-side encoding artifact — the failure was Starlette rejecting bytes that PowerShell mislabeled, not the app code. The doc-only fix is correct given that finding.
2. **However, the absence of a test means the *finding itself* (Starlette's strict charset enforcement) is not pinned.** If a future middleware adds `body = body.decode("utf-8", errors="replace")` upstream of route handlers, the 400 disappears and the original symptom (mojibake in chat logs) replaces it — strictly worse, because it's silent. The doc fix solves the operator-side problem; a regression test would solve the architectural-drift problem. The decision to ship doc-only is reasonable but leaves a known-narrow attack surface.
3. **The PowerShell `Invoke-RestMethod -Body 'literal-utf8-bytes'` pattern is idiosyncratic.** PowerShell 5.1 (matches harness env) behaves differently from PowerShell 7 here. The runbook doesn't specify which PowerShell. Minor doc-loop concern.

### Verdict: MINOR CONCERNS

The ship is correct — the failure was at the PowerShell-client layer and the documented fix addresses it cleanly. *But* the absence of any automated regression test means the architectural assumption (Starlette will refuse mislabeled bytes) is undefended. CC explicitly ran a 4-case TestClient matrix in-conversation; promoting that to a permanent regression test is the natural follow-up. Recommend filing as a P3 follow-up — won't block production, but the cost of writing it is hours and the cost of regressing is silent mojibake in chat logs.

---

## Ticket #50 — `_MIN_QUERY_LENGTH = 3` matcher floor

**Ship SHA:** `f9e9b06` (Cursor; 2026-05-09)
**Files audited:**
- `app/chat/entity_matcher.py` — added `_MIN_QUERY_LENGTH = 3` (line 637), `_normalize_for_match` helper (line 640–654), and swapped `normalize` → `_normalize_for_match` at four direct entry points: `extract_catalog_entities_from_text` (line 668), `match_entity_with_ambiguity` (line 714), `find_near_match` (line 782), `match_entity_with_rows` (line 818).
- `tests/test_entity_matcher.py` — 8 net-new test methods + 16 net-new subtests across `MinimumQueryLengthFloorTests` (line 118) and `MinimumQueryLengthFloorEntryPointTests` (line 185).

**Existing test coverage:**
- Helper-level: `test_normalize_for_match_returns_empty_for_short_input` (line 125) — empty / whitespace-only / 1-char / 2-char / whitespace-padded-1-char → `""`; 3-char identity passthrough.
- Constant pin: `test_min_query_length_constant_is_three` (line 141) — guards against silent drift up or down.
- DB-free direct-entry coverage: `test_floor_blocks_subthreshold_queries_via_match_entity_with_rows` (line 147) — 6 cases.
- DB-backed entry-point coverage: `test_match_entity_floor_on_subthreshold_queries` (line 207, 4 cases), `test_extract_catalog_entities_floor_on_subthreshold_text` (line 224, 3 cases), `test_find_near_match_floor_on_subthreshold_queries` (line 241, 3 cases).
- Positive-passthrough: `test_three_char_query_passes_floor_and_reaches_match_logic` (line 165) — `"bmx"` → match. `test_three_char_query_via_whitespace_padding_passes_floor` (line 175) — `"  bmx  "` → match (post-normalize ordering pinned).

### Coverage gaps identified

1. **`match_entity_with_ambiguity` is not tested directly for the floor — only via `match_entity` delegation.** — MEDIUM. `match_entity` delegates to `match_entity_with_ambiguity` (line 757) and the test at line 207 exercises `match_entity`, so the floor *is* hit transitively. But if a future refactor inlines `normalize` directly into `match_entity_with_ambiguity` (e.g., for performance), the delegating `match_entity` test would still pass while the direct-call surface (used by `query_has_ambiguous_entities`, line 812) silently bypasses the floor. **Suggested:** add a test that calls `match_entity_with_ambiguity("a", db)` directly and asserts `(None, False)`.

2. **`query_has_ambiguous_entities` is the fifth direct entry point (in spirit) and has zero floor coverage.** — MEDIUM. Line 805 is documented as "delegates to `match_entity_with_ambiguity`" — currently true, but the floor inheritance is implicit. The function is documented as "advisory only — no caller acts on the flag" (line 808–810), so the *risk impact* is low; but if the flag becomes load-bearing in a future router slice and `query_has_ambiguous_entities` is refactored to bypass the helper, a 1-char query would re-enter the matcher. **Suggested:** add `assert query_has_ambiguous_entities("a", db) is False` and `assert query_has_ambiguous_entities("ab", db) is False` to `MinimumQueryLengthFloorEntryPointTests`.

3. **`find_near_match` floor coverage misses empty-string and pure-whitespace cases.** — LOW. `test_find_near_match_floor_on_subthreshold_queries` (line 241) covers `"a"` / `"ab"` / `"  ab  "` only. The other entry points test more of the matrix. Asymmetric coverage; suggest extending to match `match_entity`'s 4 cases.

4. **No test asserts that `_needles_for_canonical` (line 269–280) does NOT apply the floor on the index side.** — LOW. The function deliberately calls `normalize`, not `_normalize_for_match`, so a 3-char alias like `"mtb"` (CANONICAL_EXTRAS line 47) and 3-char canonical names (e.g., the `"DBR"` test fixture at line 609) keep indexing correctly. Behavior works (covered indirectly by `test_mountain_bike_club_aliases`) but the *invariant* — "the floor is a query-side gate, never an index-side filter" — is not pinned by a direct test. **Suggested:** `assert "mtb" in _needles_for_canonical("Lake Havasu Mountain Bike Club")` plus a complementary "3-char alias is queryable directly" test (`match_entity_with_rows("mtb", [canon])` returns the canonical).

5. **No test for emoji / non-ASCII queries that pass `len(norm) >= 3` but have no useful catalog target.** — LOW. `_normalize_for_match` doesn't strip emoji (`normalize` only lowercases + collapses whitespace + strips edge punctuation). A 3-emoji query like `"🎉🎉🎉"` has length 3 and passes the floor, then fuzz-scores against ASCII canonicals (returns no match in practice). Acceptable gap — the fuzz scorer is the safety net — but worth pinning so a future `normalize` change that retains punctuation can't accidentally inflate scores.

6. **No test at the *exactly-2-char-post-normalize* edge with high-ambiguity boundary.** — LOW. The 2-char rejection is tested via `"ab"` (line 158) and `"  ab  "` (line 156). What about 2 unicode "wide" chars (CJK)? `len("中文") == 2`, so it's rejected. Behavior correct but unverified.

### Edge cases not tested

1. Mixed-case 2-char queries that normalize to 2 chars (`"AB"` → `"ab"` → blocked). Probably fine — `normalize` lowercases.
2. 2-char query with a punctuation tail (`"a!"`) — normalized to `"a"` (1 char) → blocked. Consistent with the "post-normalize floor" contract but not tested.
3. Apostrophe contractions that expand at normalize-time (`"i'm"` → `"i am"` → 4 chars → passes the floor). The `i'm → i am` contraction (`normalizer.py:18`) is on, so this is the *only* way a 3-char raw input can become a 4-char normalized query. Untested at the matcher entry — pinning would prevent a future contraction-list change from silently making `"i'm"` queryable as `"i am"` against the catalog (which has no useful match anyway, but the path is undocumented).
4. Floor interaction with the category guard (`_category_guard_skips_row`, line 215). A 3-char query that *would* be blocked by the guard — does the floor short-circuit run before the guard? Yes, per line 668/714/782/818, but no test pins the ordering.
5. Floor interaction with whitespace-stripping in `match_entity_with_rows` (the `c = c.strip()` at line 824) on the canonical-side — covered by happy-path tests but not by a 3-char canonical (`"DBR"`) + 3-char query.

### Code observations

1. **`_needles_for_canonical` (line 269) intentionally calls `normalize`, not `_normalize_for_match`.** This is correct — the floor is a query-side gate, not an index-side filter — but the *intent* is undocumented at the call site. The Backlog #50 comment block at lines 620–637 explains the floor-at-query-side rationale at length, but `_needles_for_canonical` has no inline note explaining "we deliberately keep `normalize` here so 3-char aliases like `mtb` index." A one-line comment would prevent a future tidy-up pass from "consistency-fixing" the call to `_normalize_for_match`. **Risk:** low (the test for `test_mountain_bike_club_aliases` would catch the regression for "Lake Havasu Mountain Bike Club", but only because there's a longer-form query that exercises it; a future CANONICAL_EXTRAS entry whose *only* alias is 3 chars would be silently dropped).

2. **`_MIN_QUERY_LENGTH = 3` as a module-level constant (line 637) is the right shape**, and `test_min_query_length_constant_is_three` (line 141) prevents drift. Future tweak (e.g., `2` to admit `"BJ"` for "Bridge & Joist") would require an intentional test edit — good.

3. **`_normalize_for_match` returns `""` for the floor-blocked case (line 653), relying on every caller's existing `if not norm: return …` guard.** Elegant — no change to caller bodies — but makes the floor *invisible* in caller code. A reader skimming `match_entity_with_ambiguity` (line 714) sees only `norm = _normalize_for_match(query)` and has to follow into the helper to know the floor exists. A one-line caller-side comment ("# returns "" for sub-3-char input — see Backlog #50") would help future maintainers. Stylistic, not a coverage concern.

4. **The file has `_MIN_QUERY_LENGTH = 3` (numeric) and the test pins it at 3 — but the helper docstring (line 641) says "carries at least :data:`_MIN_QUERY_LENGTH` chars of content."** Both are consistent. No concern; flagging only because it's the kind of thing where a constant-rename refactor (`_MIN_QUERY_LENGTH` → `_MIN_QUERY_CHARS`) would silently break the cross-reference. Use `:data:` references defensively.

### Verdict: APPROVED

The lane delivers thorough boundary coverage at every direct entry point (`extract_catalog_entities_from_text`, `match_entity` via delegation, `find_near_match`, `match_entity_with_rows`) plus a helper-level pin and a constant pin. Gaps are mostly second-order: delegation is *assumed* rather than tested for `match_entity_with_ambiguity` and `query_has_ambiguous_entities`; index-side floor non-application is implicit; `find_near_match` test matrix is asymmetric vs. siblings. No actual bug. The single most useful follow-up is direct floor tests on `match_entity_with_ambiguity` + `query_has_ambiguous_entities` — pin the delegation contract explicitly.

---

## Cross-ticket observations

Three patterns surfaced across all three lanes:

1. **No integration tests at the chat-route boundary.** All three lanes ship unit-level coverage but nothing exercises the full HTTP path (`POST /api/chat → unified_router → matcher/classifier → response`). #51 is the most striking case (the bug *is* a chat-route boundary issue) but #50 and #55 also lack end-to-end tests. `tests/test_chat_route_audience_forwarding.py` is the only `test_chat_route_*` file in the tree and it covers a single Phase-1 lane. This is a systematic gap, not a per-ticket gap — recommend treating it as a Phase 2 testing-infrastructure ticket rather than three separate follow-ups.

2. **Test fixtures and prod constants drift independently.** #55's `_OPERATOR_VOCAB` test fixture is hand-maintained; #50's `_MIN_QUERY_LENGTH` test pin is a magic-number assertion; #51's smoke catalog references "Backlog #51 close-out" by string. None of these are wrong, but together they suggest the project would benefit from a "fixture-imports-from-prod" lock-step convention so future migrations can't desync.

3. **Documentation-anchored ships (like #51) have no automated regression net.** The doc fix is correct but the architectural finding underneath it (Starlette refuses mislabeled bytes) has no test. Future doc-only ships should default-include a "permanent regression test in `tests/`" question on the checklist — answered "no, here's why" or "yes, here it is", but answered explicitly. Avoids the silent-mojibake-on-future-middleware-change failure mode.

---

## Recommended follow-ups

Concrete BACKLOG entries the operator could file (text below is the BACKLOG entry I'd add — **not filed by this audit**, per the read-only constraint). Ranked by risk.

1. **HIGH — file as new `#56`: chat-route UTF-8 regression test for accented query bodies.** `Add tests/test_chat_route_utf8.py mirroring CC's #51 TestClient matrix: (a) accented query body + Content-Type "application/json; charset=utf-8" → 200; (b) same body + Content-Type "application/json; charset=latin-1" → 400; (c) Win-1252 bytes labeled UTF-8 (mojibake input) → 200 with no match (matcher's job, not Starlette's); (d) ASCII baseline → 200. Pins the architectural assumption that Starlette refuses mislabeled bytes, so a future middleware that decodes-with-errors-replace can't silently regress accented queries to mojibake. Closes the test gap from #51's doc-only ship.`

2. **MEDIUM — file as new `#57`: lock-step symmetry for `_OPERATOR_VOCAB_METHODS` ↔ test fixture.** `In tests/test_confidence_tier.py, replace test_KNOWN_METHODS_covers_full_operator_vocab with a bidirectional assertion: tuple(sorted(ct._OPERATOR_VOCAB_METHODS)) == tuple(sorted(_OPERATOR_VOCAB)). Also parametrize test_low_no_verification_record over _OPERATOR_VOCAB so the no-last_verified_at branch is exercised for every operator-vocab method. Closes the "test fixture drifts from prod" risk surfaced by #55's audit.`

3. **MEDIUM — file as new `#58`: direct floor coverage for delegating entry points.** `In tests/test_entity_matcher.py::MinimumQueryLengthFloorEntryPointTests, add direct floor assertions on match_entity_with_ambiguity and query_has_ambiguous_entities. Currently both inherit the floor via delegation only — a refactor that re-introduces a direct normalize() call would silently bypass the floor. Pins the delegation contract.`

4. **LOW — file as new `#59`: 90-day MEDIUM boundary coverage for confidence-tier classifier.** `Parametrize the MEDIUM-band tests in tests/test_confidence_tier.py over (manual, owner_confirmed, npi_registry) + _OPERATOR_VOCAB at age=90 (MEDIUM expected) and age=91 (LOW expected). Currently every MEDIUM test picks age=60; the inclusive 90-day cutoff has no boundary coverage. A future _MEDIUM_TRUSTED_DAYS tweak would land off-by-one with no test signal.`

5. **LOW — file as new `#60`: index-side floor non-application invariant.** `In tests/test_entity_matcher.py, add a direct assertion that _needles_for_canonical("Lake Havasu Mountain Bike Club") contains "mtb" (3-char alias). Pins the design intent: the floor is a query-side gate, never an index-side filter. Prevents a future "consistency-fix" pass from collapsing _needles_for_canonical's normalize() calls to _normalize_for_match() and silently dropping 3-char curated aliases.`

6. **LOW — file as new `#61`: clarify smoke-catalog Class E3 scope post-#51.** `Edit docs/maintainability/backlog_46_smoke_check_queries.md Class E3 to disambiguate that the test now exercises the matcher-side accent-folding path — the wire-level concern is precondition-met by the "; charset=utf-8" clause documented at line 9–11. Currently the catalog says "Match OR safely None (accent handling)" without specifying which layer.`
