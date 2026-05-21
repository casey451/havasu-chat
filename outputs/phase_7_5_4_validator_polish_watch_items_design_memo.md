# Phase 7.5.4 design memo — validator polish watch items (G4 list-promiscuity + template-echo scrub surface)

> **What this is:** scoping memo for Phase 7.5.4, the lowest-priority polish lane carved out after the Phase 7.5.2 ship (commit `64799d5`, 2026-05-20). Phase 7.5.2 closed the five Goodhart gaps G1-G5 plus the F3 mocked-router test gap. Two new watch items surfaced from that hardening — neither is a user-facing bug; both are validator-quality concerns that may erode the guardrail over time if left untouched. This memo scopes them; it does NOT author the dispatch wrapper.
>
> **Authored by:** Cowork primary via sub-agent, 2026-05-20, post-Phase-7.5.2-ship + post-7.6-dispatch.
>
> **Companion docs:**
> - `outputs/phase_7_5_prod_divergence_investigation.md` (post-mortem; G4 enumerated §4 lines 205-218, template-echo concern is novel — surfaced from the 7.5.2 wrapper's `_sanitize_typed_facts` addition)
> - `outputs/cursor_dispatch_prompt_phase_7_5_2.md` (validator hardening dispatch — SHIPPED `64799d5`; introduced the `_sanitize_typed_facts` scrubs that motivate watch item #2)
> - `outputs/phase_7_6_tier2_llm_parser_design_memo.md` (q03 LLM-parser fix scoping)
> - `outputs/phase_7_5_3_validator_polish_design_memo.md` (parallel polish lane for F1/F4/F5 — non-overlapping scope with 7.5.4)
>
> **Status:** design-only; no Cursor wrapper authored yet. Use this memo as input when authoring the Phase 7.5.4 dispatch wrapper.

---

## §1 Root cause hypothesis (per gap)

### Watch item #1 — G4 list-promiscuity (multi-tier `expected_tier` lists weaken the burn-down)

**Location:** `app/chat/halt3_validator.py:335-351` (`_tier_matches`), `app/chat/halt3_eval_set.yaml` rows q02, q10, q12, q14, q17, q19, q27, q30.

**Code (current):**
```python
def _tier_matches(expected: ExpectedTierField, actual: str) -> bool:
    mapping = {"tier1": "1", "tier2": "2", "tier3": "3"}
    def _norm(x: str) -> str:
        return mapping.get(x, x)
    if isinstance(expected, list):
        if not expected:
            return False
        return any(actual == _norm(e) for e in expected)
    if expected == "any":
        logging.warning(
            "halt3 eval set still contains expected_tier='any' — burn-down incomplete"
        )
        return True
    return actual == _norm(expected)
```

**Census of the 30-row eval set (q01-q30):**

| List length | Count | Entry IDs |
|---|---|---|
| 1-tier (string) | 22 | q01, q03-q09, q11, q13, q15, q16, q18, q20-q26, q28, q29 |
| 2-tier list | 6 | q10, q12, q14, q17, q19, q30 |
| 3-tier list | 2 | q02, q27 |
| 4+ tier list | 0 | — |

The operator's working memory referenced q02/q12/q19 as 3-tier entries; the YAML at HEAD actually shows q12 and q19 as 2-tier (`[tier2, gap_template]` and `[tier2, tier3]` respectively). Only **q02** (`[tier2, tier3, gap_template]`) and **q27** (`[tier1, tier2, gap_template]`) are genuinely 3-tier. Worth correcting in the wrapper.

**What's wrong:** the post-7.5.2 burn-down replaced `expected_tier: any` (no-op) with explicit lists, satisfying the letter of G4's fix. But for 8 rows (27% of the suite) the lists span 2-3 tiers — and a 3-tier list covering `[tier2, tier3, gap_template]` constrains routing only against the `chat` and `tier1` paths, which is functionally `any`-minus-two. The validator can still catch a chat-vs-tier or tier1-vs-tier regression on those rows, but it cannot catch a tier2-vs-tier3 routing regression (the most common Goodhart-vector for confabulation, per §3 of the post-mortem).

**Symptom this could produce:** a future regression that flips q02 from tier-2 cited-listing (the dev-DB happy path) to tier-3 LLM freeform (the prod q03 failure shape) passes `_tier_matches` trivially because `tier3` is in the allowlist. The validator's other guards (G1/G2/G3/G5) might still catch the resulting confab body, but the tier-routing signal is silently lost — exactly the failure mode the G4 burn-down was supposed to prevent.

**Why the lists exist:** dev-DB routing is genuinely flaky on these queries (the notes columns say so for q02/q10/q12/q14/q19). For q02 ("find me a barber"), the dev catalog has zero barber rows, so routing lands in tier-2-shortcut (empty result fallback), tier-3 LLM, or the gap template depending on the LLM-parser path that day. Forcing a single expected tier would produce flake in CI. The list is a pragmatic concession to fixture non-determinism, not a deliberate weakening of the validator.

**Confidence:** high that the gap exists as described. **Medium-low that it currently masks any specific bug** — none of the 8 list-bearing rows correspond to a known prod failure shape. This is genuinely a watch-item: the guardrail is weaker than it looks on the rows where dev fixtures are flakiest, but no production failure traces to it yet.

### Watch item #2 — template-echo scrub surface in `_sanitize_typed_facts`

**Location:** `app/chat/halt3_validator.py:49-50` (`_PLATFORM_URL_MARKERS`), `:109-127` (`_sanitize_typed_facts` + `_is_platform_url`), `:130-142` (`_typed_fact_probes` consumer).

**Code (current):**
```python
_PLATFORM_URL_MARKERS = ("golakehavasu.com", "/contribute")

def _is_platform_url(url: str) -> bool:
    low = (url or "").lower()
    return any(marker in low for marker in _PLATFORM_URL_MARKERS)

def _sanitize_typed_facts(text: str, facts: dict[str, list[str]]) -> dict[str, list[str]]:
    """Drop template-echo probes that are not business-confab signals."""
    out = {k: list(v) for k, v in facts.items()}
    if out.get("hours"):
        out["hours"] = [
            h for h in out["hours"]
            if not re.search(r"open\s+tomorrow", h, re.IGNORECASE)
        ]
    low = (text or "").lower()
    if out.get("rating") and (
        "rated above" in low or "stars in the catalog" in low or "rating for" in low
    ):
        out["rating"] = []
    return out
```

**Full inventory of the actual scrubs Cursor introduced in 7.5.2** (not just the four the operator's context mentioned):

1. **URL scrub** (`_is_platform_url`, called from `_typed_fact_probes` line 133): drops any URL whose lowercase form contains `golakehavasu.com` **or** `/contribute` as a substring.
2. **Hours scrub** (`_sanitize_typed_facts` lines 117-121): drops any hours probe whose text contains `open tomorrow` (case-insensitive, allows whitespace between words).
3. **Rating scrub — whole-text gate** (lines 123-126): wipes the **entire** `rating` list when the response text (lowercased) contains any of: `rated above`, `stars in the catalog`, or `rating for`.

**What's wrong, scrub-by-scrub:**

- **#1 URL scrub is overly loose.** It uses `marker in low` substring matching with no boundary anchoring. An attacker query that elicits `"check https://imaginarybusiness.com/contribute-please for the address"` would be scrubbed because `/contribute` is a substring of `/contribute-please`. The scrub also accepts `golakehavasu.com` as a substring of any URL — so `https://evil.example.com?ref=golakehavasu.com` would be scrubbed. Both are crafted shapes, not natural completions, but the scrub is loose enough that a determined adversary could exploit it.
- **#2 Hours scrub is moderately loose.** `open\s+tomorrow` matches anywhere inside the captured hours probe. The `_HOURS_RE` capture itself is wide — `\b(?:Mon|Tue|...|today|tomorrow)\w*[^.]*?\d{1,2}(?::\d{2})?\s*(?:am|pm|...)` can span ~80 chars of unbounded `[^.]*?`. A response like `"open tomorrow Mon 8am"` could be captured as one hours probe; the scrub wipes it. But a confab response like `"open tomorrow Mon 8am to 5pm at Imaginary Diner"` would have the hours probe scrubbed — and if the diner name is the only proper-noun signal, the response also lacks a catalog entity match, so the confab path collapses to `_has_novel_proper_nouns` in `_confabulation_rate`. That secondary guard catches the proper noun, but if a confab elicits hours with `"open tomorrow"` and a *cataloged* entity (e.g. `"Heat Hotel is open tomorrow at 9am-9pm"` when Heat Hotel actually has no hours field populated), the multi-entity / entity-supports-typed-facts logic at lines 206-222 catches the hours mismatch only if `_entity_has_hours` returns False for Heat Hotel — but the hours-probe was scrubbed before reaching `_entity_supports_typed_facts`. **That's the real concern.**
- **#3 Rating scrub is the loosest.** The gate `"rated above" in low or "stars in the catalog" in low or "rating for" in low` is a whole-text substring check, and triggers the scrub of the **entire** `rating` list (not just the offending value). A response of the shape `"What's the rating for Mudshark Brewery? It's 4.8 stars."` (where the user query was `"rating for Mudshark Brewery"`) would have its asserted `4.8 stars` rating scrubbed because the response echoes the user query phrase `rating for`. If Mudshark Brewery's actual `google_rating` is e.g. 4.5, the rating mismatch is silently dropped. **This is the highest-priority concern of the three.**

**Symptom this could produce:** an adversarial query crafted to elicit a response containing one of the scrub phrases will have its typed facts laundered through the scrub. The most plausible attack: a query echoing `"rating for X"` where X is a real catalog entity → the model emits `"the rating for X is N.N stars"` → `_RATING_RE` captures `N.N stars` → `_sanitize_typed_facts` sees `"rating for"` in the lowercased response → entire rating list wiped → confab rate falls to 0.0 even if N.N is fabricated. The 7.5.2 q25 row probes exactly this shape (`"what's the rating for Mudshark Brewery and Public House"`) but expects `cited` + 0.0 confab; if the model invents a rating, the scrub may mask it.

**Confidence:** high that the scrubs are loose as described — read directly from the source at lines 50, 117-126. **Medium-high that scrub #3 (rating, whole-text gate) is exploitable on q25-shape queries.** Medium that scrub #2 (hours) is exploitable on Heat-Hotel-style cataloged-entity-with-empty-hours-field queries. Low that scrub #1 (URL) is exploitable on natural completions. **All three are tighter problems than G4.** Worth closing rather than dropping.

---

## §2 Proposed fix (per gap)

### Watch item #1 fix — replace multi-tier lists with per-tier disclosure-path pinning

**Recommend Path A — accept the dev-flake reality, but pin the *disclosure path* and *confabulation rate* instead of pinning tier.** The validator already cares about disclosure-path + confab-rate as the load-bearing properties; tier is a routing-determinism property that is genuinely fixture-conditional. Demote tier to a soft signal on the 8 list-bearing rows by adding a `tier_strict: false` flag (default true) per row, and on flaky rows allow the list but emit a `logging.info` (not failure) when the actual tier is in the allowlist. Keep the list to document expected behavior; drop the gate.

**Touch points:**

- `app/chat/halt3_validator.py:54-60` (`EvalQuerySpec`) — add `tier_strict: bool = True` field.
- `app/chat/halt3_validator.py:88-106` (`load_eval_set`) — read optional `tier_strict` key (default True).
- `app/chat/halt3_validator.py:378-384` (`_run_one` failure construction) — when `spec.tier_strict is False` and `_tier_matches` returns True via list-membership, log an `info` line with the actual tier; do not fail.
- `app/chat/halt3_eval_set.yaml` — set `tier_strict: false` on the 8 list-bearing rows (q02, q10, q12, q14, q17, q19, q27, q30). Keep the lists for documentation purposes.

**Rejected alternative A: force routing determinism upstream.** Would require seeding dev fixtures to guarantee q02 (barber), q12 (heat-bias indoor dining), q19 (multi-domain pet store + dog park), q27 (barber w/ disclaimer echo) deterministically hit a single tier. That's a 50-200 LOC fixture surgery for each row plus a permanent maintenance tax — and the rows are diagnostic of the real-world flake, not a bug. Rejected.

**Rejected alternative B: tighten lists to 1-tier each.** Same problem as A — the dev fixture genuinely produces different tiers on different runs. A 1-tier pin would introduce CI flake.

**Rejected alternative C: replace tier matching with a per-tier `expected_disclosure_path` mapping.** Operator's prompt suggested this. Considered but rejected because the eval set's existing structure already pins `expected_disclosure_path` *globally* per row, not per-tier — and for the list-bearing rows, the disclosure-path is already correctly invariant across the allowed tiers (e.g. q02's `i_dont_know` holds whether tier-2 returns empty, tier-3 disclaims, or the gap template fires). The current structure already captures the load-bearing invariant. Adding per-tier disclosure-path maps would be over-engineered.

**Code sketch:**
```python
@dataclass(frozen=True)
class EvalQuerySpec:
    id: str
    query: str
    expected_tier: ExpectedTierField
    expected_disclosure_path: DisclosurePath
    expected_confabulation_rate: float
    notes: str = ""
    tier_strict: bool = True  # new

# in _run_one
tier_ok = _tier_matches(spec.expected_tier, resp.tier_used)
if not tier_ok:
    failures.append(f"tier expected {spec.expected_tier}, got {resp.tier_used}")
elif isinstance(spec.expected_tier, list) and not spec.tier_strict:
    logging.info(
        "halt3 q=%s tier=%s within allowlist %s (tier_strict=false)",
        spec.id, resp.tier_used, spec.expected_tier,
    )
```

### Watch item #2 fix — tighten scrubs to template-shape anchors, add anti-scrub probe

**Recommend Path A — tighten regexes + add a "scrub-suppressed but content present" check.** Two-pronged: (1) anchor each scrub on the actual template shape (sentence-level pattern, not substring), and (2) when a scrub fires, run a residual probe on the unscrubbed text — if a typed fact would otherwise have credited the response as a confab, refuse to credit the scrub.

**Touch points:**

- `app/chat/halt3_validator.py:49-50` (`_PLATFORM_URL_MARKERS`) — keep, but tighten `_is_platform_url` to require the marker as a domain or path segment, not arbitrary substring.
- `app/chat/halt3_validator.py:109-111` (`_is_platform_url`) — replace with a regex that anchors `golakehavasu.com` as a hostname (host or subdomain-of) and `/contribute` as a path component starting at a `/` boundary and followed by `/`, end-of-URL, or a query/fragment delimiter.
- `app/chat/halt3_validator.py:114-127` (`_sanitize_typed_facts`) — tighten the hours and rating scrubs:
  - Hours: replace `open\s+tomorrow` substring check with a sentence-level pattern that matches only the **gap-template phrasing** (e.g. `r"\bcan'?t\s+say\s+(?:if|whether)[^.]*open\s+tomorrow\b"` — anchored on the actual disclaimer template body).
  - Rating: replace the three-clause whole-text gate with sentence-level patterns that match only template disclaimers (e.g. `r"don'?t\s+have\s+(?:any|a|the)\s+rating\s+for\b"`, `r"no\s+\w+\s+rated\s+above\b"`, `r"\d\s+stars?\s+in\s+the\s+catalog\b"`). When matched, scrub only the rating value(s) *appearing in the same sentence as the match*, not the entire `rating` list.
- New helper `_scrub_audit(text, raw_facts, sanitized_facts, mentioned_entities, db) -> bool` returning True iff the scrub removed values that, had they been retained, would have caused `_entity_supports_typed_facts` to return False. If True, the scrub is *suspect* — escalate confab rate to 0.5 (soft-fail) instead of 0.0 (clean).

**Rejected alternative A: remove the scrubs entirely.** Would re-break the legitimate cases the scrubs were added to defend (q30's "rated above 4 stars" echo in the user query, q26's `/contribute` link in the gap template, q05/q06's "open tomorrow" disclaimer). Rejected.

**Rejected alternative B: hash-pin the exact template strings.** Would require importing the gap-template constants from `unified_router.py` into the validator, creating a coupling. Considered cleaner but heavier; the per-pattern sentence-level approach is lighter and self-documenting.

**Code sketch (rating scrub tightening):**
```python
_RATING_DISCLAIMER_PATTERNS = (
    re.compile(r"don'?t\s+have\s+(?:any|a|the)\s+rating\s+for\b", re.I),
    re.compile(r"no\s+\w+\s+rated\s+above\b", re.I),
    re.compile(r"\d\s+stars?\s+in\s+the\s+catalog\b", re.I),
    re.compile(r"\bno\s+rating\s+available\b", re.I),
)

def _sanitize_typed_facts(text: str, facts: dict[str, list[str]]) -> dict[str, list[str]]:
    out = {k: list(v) for k, v in facts.items()}
    if out.get("hours"):
        out["hours"] = [
            h for h in out["hours"]
            if not re.search(
                r"\bcan'?t\s+say[^.]*open\s+tomorrow\b", h, re.I
            )
        ]
    if out.get("rating"):
        # Per-sentence scrub: keep ratings outside disclaimer sentences.
        sentences = re.split(r"(?<=[.!?])\s+", text or "")
        kept: list[str] = []
        for r in out["rating"]:
            in_disclaimer = False
            for s in sentences:
                if r in s and any(p.search(s) for p in _RATING_DISCLAIMER_PATTERNS):
                    in_disclaimer = True
                    break
            if not in_disclaimer:
                kept.append(r)
        out["rating"] = kept
    return out
```

**Tests:** add to `tests/test_halt3_validator_hardening.py` (the 7.5.2 file):
- Positive (scrub still works): response containing template-shape `"I don't have a rating for that one — try the catalog."` does not flag a confab.
- Negative (tighter scrub catches confab): response containing `"the rating for Mudshark is 4.8 stars"` where catalog rating is 4.5 → confab rate 1.0 (rating value retained because the sentence does not match the disclaimer patterns).
- Positive (URL): platform-URL `https://golakehavasu.com/contribute` scrubbed.
- Negative (URL): adversarial `https://evil.example.com?ref=golakehavasu.com` retained as a confab signal.
- Negative (hours): response `"Heat Hotel is open tomorrow Mon 8am to 5pm"` with no catalog hours field → confab rate 1.0 (hours retained because no disclaimer phrasing).

---

## §3 Effort estimate

- **Watch item #1 (G4 list-promiscuity):** S, ~20-40 LOC + 2-3 tests + 8 YAML edits. Adding one optional field, one log line, one YAML key per affected row. **~30-45 min Cursor session.**
- **Watch item #2 (template-echo scrubs):** S-M, ~60-100 LOC + ~5-7 tests. Three scrub-pattern rewrites + one helper + per-sentence scrub logic + adversarial test cases. **~1-1.5 hour Cursor session.**

**Aggregate: S-M (~80-140 LOC + ~8-10 tests + 8 YAML edits, ~1.5-2.5 hour Cursor session).** Smaller than 7.5.3's aggregate M estimate (~150 LOC + ~15 tests, 2-3h). Genuinely the lowest-priority lane.

---

## §4 Sequencing

**File-scope check (gotcha #18):**

- **Phase 7.6 (in flight) touches:** `app/chat/tier2_business_shortcut.py`, `tests/test_tier2_business_shortcut.py`.
- **Phase 7.5.3 (queued) touches:** `app/chat/entity_intent.py`, `app/chat/unified_router.py`, `tests/test_gap_template_contribute_link.py`, `tests/test_phase38_gap_and_hours.py`, `tests/test_phase7_halt3_validation.py`.
- **Phase 8a (queued — conditions infrastructure) touches:** TBD per its own design memo; expected to introduce new conditions tables and tier-2/tier-3 condition-routing surfaces. Should not touch `halt3_validator.py` directly.
- **Phase 7.5.4 (this memo) touches:** `app/chat/halt3_validator.py`, `app/chat/halt3_eval_set.yaml`, `tests/test_halt3_validator_hardening.py` (the 7.5.2 file).

**Overlap findings:**

- **vs Phase 7.6:** zero overlap. Parallel-eligible.
- **vs Phase 7.5.3:** zero file overlap (7.5.3 touches `entity_intent.py` + `unified_router.py` + gap-template tests + `test_phase7_halt3_validation.py`; 7.5.4 touches `halt3_validator.py` + `halt3_eval_set.yaml` + `test_halt3_validator_hardening.py`). Parallel-eligible.
- **vs Phase 8a:** zero expected overlap. Parallel-eligible if 8a's dispatch authoring runs concurrently; otherwise serialize whichever lands first.

**Recommendation:** **Phase 7.5.4 is parallel-eligible with all three of 7.6, 7.5.3, and 8a.** Lowest-priority lane → dispatch only when a Cursor session would otherwise idle. **Serialize after 7.5.3 if both are dispatched** — 7.5.4's watch-item-#1 fix needs to be measured against the post-7.5.3 baseline (F5 about-gate changes don't touch the validator, but they affect tier routing on q07/q23-shape rows which the 7.5.4 G4 burn-down should observe).

Practical recipe: ship 7.6 → ship 7.5.3 → dispatch 7.5.4 (or batch 7.5.4 with the next non-urgent polish lane).

**Honest assessment of whether to lane this at all:** watch item #2 (template-echo) is genuinely worth closing because scrub #3 (rating) is the highest-confidence exploitable surface in the current validator and has a low-effort fix. Watch item #1 (G4 list-promiscuity) is **borderline drop-from-lane**: the 8 list-bearing rows don't correspond to any known prod failure, and the proposed `tier_strict: false` flag is essentially documentation of the existing flake rather than a behavioral tightening. If lane velocity is constrained, drop watch item #1 and run 7.5.4 as a single-issue lane on the template-echo scrubs only — would shrink the aggregate to ~60-100 LOC + ~5-7 tests, **~1 hour Cursor session**.

---

## §5 Risks

### Watch item #1 risks

- **Adding `tier_strict: false` legitimizes the flake rather than fixing it.** True but acknowledged — the alternative (fixture surgery) is higher cost than the watch-item warrants. Mitigation: emit the `logging.info` line in CI output so operators see when a row matched-via-allowlist vs. matched-on-the-pinned-tier, providing visibility into when the flake actually fires.
- **Future tightening regression.** If a later phase makes one of the 8 flaky rows deterministic (e.g. Phase 8a adds barber catalog rows so q02 becomes consistently tier-2), the `tier_strict: false` flag becomes stale. Mitigation: add a comment in the YAML pointing back to this memo's §1 census, so the flag is re-audited at every catalog change.

### Watch item #2 risks

- **Over-tightening breaks legitimate template scrubs.** The 7.5.2 wrapper added these scrubs specifically because q26 (`website for the library`), q30 (`rated above 4 stars`), and q05/q06 (gap-template hours phrasing) needed them. If the tightened regexes don't match the actual template strings emitted by `unified_router.py`, q26/q30/q05/q06 would regress from `passed=True` to `passed=False`. Mitigation: red-then-green by running the post-7.5.2 eval set before and after the change; require 30/30 PASS at start and 30/30 PASS at end.
- **Per-sentence scrub logic adds complexity.** The current scrub is ~15 LOC and obvious. The tightened version is ~40 LOC with per-sentence iteration — more surface for bugs. Mitigation: aggressive unit-test coverage of the sentence-splitting against responses that span 1, 2, and 3+ sentences with the disclaimer in each possible position.
- **Anti-scrub probe (`_scrub_audit`) is conservative.** Escalating to confab rate 0.5 (soft-fail) on scrub-suspect responses might re-introduce false positives — a legitimate gap-template response that happens to contain a real catalog rating mention (unlikely but possible) would trip the audit. Mitigation: gate `_scrub_audit` on whether the response actually has a non-template-shape phrasing — if every sentence containing a typed fact also matches a disclaimer pattern, the audit can skip.

**Aggregate worst case (any fix over-corrects):** the validator becomes too strict and flags legitimate gap-template responses as confab → CI fails → blocks merge. The blast radius is the local-CI gate, not production. Strict downgrade from the q07-class failures motivating the parent investigation. Recoverable in one revert commit.

---

## §6 Files referenced

- `app/chat/halt3_validator.py` lines 36-47 (typed-fact regexes — context only; not touched), 49-50 (`_PLATFORM_URL_MARKERS` — touched by #2), 53-60 (`EvalQuerySpec` — touched by #1), 88-106 (`load_eval_set` — touched by #1), 109-111 (`_is_platform_url` — touched by #2), 114-127 (`_sanitize_typed_facts` — touched by #2), 130-142 (`_typed_fact_probes` — context; consumer of the scrub), 335-351 (`_tier_matches` — touched by #1), 354-405 (`validate_eval_set` + `_run_one` — touched by #1 for the soft-log path).
- `app/chat/halt3_eval_set.yaml` rows q02 (line 10-15), q10 (61-66), q12 (74-79), q14 (87-92), q17 (107-112), q19 (120-125), q27 (174-179), q30 (195-200) — 8 list-bearing rows to receive `tier_strict: false`. Census of all 30 rows in §1 above.
- `tests/test_halt3_validator_hardening.py` — extend with #2 adversarial scrub tests (file created in Phase 7.5.2 dispatch; line ranges TBD post-ship).
- `outputs/phase_7_5_prod_divergence_investigation.md` §4 lines 205-218 (G4 — `expected_tier='any'` origin diagnosis; G4 post-7.5.2 state is the multi-tier list shape audited in this memo).
- `outputs/cursor_dispatch_prompt_phase_7_5_2.md` — wrapper that introduced `_sanitize_typed_facts` (the surface this memo audits). Specific line range TBD; the scrubs were added as part of the G2 typed-fact probe block.

---

## §7 Recommended next step

Hand this memo to a Cowork session OR to `cc` to author the actual Phase 7.5.4 dispatch wrapper. The wrapper should mirror Phase 7.5.1's structure (§0-§12), pin to a post-7.5.2 SHA (and post-7.5.3 SHA if 7.5.3 lands first), and explicitly disclaim the surfaces owned by other in-flight phases (`tier2_business_shortcut.py` → 7.6, `entity_intent.py` + `unified_router.py` → 7.5.3). The wrapper should also make the §4 honest-assessment recommendation explicit: if velocity is tight, the wrapper should ship watch item #2 only and defer watch item #1 to V1.5.

When authored, the wrapper lives at `outputs/cursor_dispatch_prompt_phase_7_5_4.md`.

---

*Authored by sub-agent under Cowork primary supervision, 2026-05-20 post-Phase-7.5.2-ship + post-7.6-dispatch. Saved to `outputs/phase_7_5_4_validator_polish_watch_items_design_memo.md`.*
