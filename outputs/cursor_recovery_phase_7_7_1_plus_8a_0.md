# Cursor recovery dispatch — Phase 7.7.1 + Phase 8a.0 (IDE-corruption replay)

> **What this is:** A mechanical recovery + fix. The IDE-buffer-corruption pattern has now hit the working tree three times this session. Two small uncommitted patches have been clobbered by it. Your job: reset the working tree to the committed state, re-apply two small patches, **commit IMMEDIATELY after each patch**, and verify.
>
> **Origin/main tip at dispatch:** `d2e3867` (`fix(tests): conftest pollution ...`). Verify at boot.
>
> **Time-box:** ~30-45 min. Bail if you hit anything you don't recognize — don't improvise.

---

## §0 Prereq verification + clean state setup

**Step 0.1 — Verify Cursor IDE windows are truly closed.**

The corruption mechanism is multi-window IDE editor-buffer collision: stale buffers from an earlier Cursor window autosave over fresh writes when focus changes. Before starting, in your terminal:

```powershell
# Windows: kill any stray Cursor processes outside this current session
Get-Process -Name "Cursor" -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime
```

If the list shows MORE than the current session's Cursor process(es), ALERT THE OPERATOR and HALT. Do not proceed until Casey confirms the stray processes are killed.

**Step 0.2 — Verify origin/main tip + clean reset.**

```powershell
cd C:\Users\casey\projects\havasu-chat
git log --oneline -3
# Expected: d2e3867 (fix tests conftest), 2ed4838 (docs phase8a), 8a905c6 (feat phase8a)
git status --short
```

If git status shows ANY M (modified) entries on tracked files — those are corruption replays from the IDE buffer collision. Hard-reset them:

```powershell
git restore .
git status --short
```

After `git restore .`, ONLY untracked entries should remain (??). No M, no D, no AD. If M lines persist after `git restore .`, ALERT THE OPERATOR — the IDE corruption is still actively writing files. HALT.

**Step 0.3 — Sanity-check file integrity.**

```powershell
# Line counts should match HEAD exactly:
foreach ($f in @("app\chat\tier2_handler.py", "app\conditions\airnow.py", "app\conditions\nws.py", "app\conditions\usgs.py", "tests\conftest.py")) {
  $wt = (Get-Content $f | Measure-Object -Line).Lines
  $head = (git show "HEAD:$f" | Measure-Object -Line).Lines
  Write-Host "$f`: wt=$wt HEAD=$head"
}
```

If any `wt` ≠ `HEAD`, files are still corrupted. HALT.

---

## §1 Patch A — Phase 7.7.1 (q10/q12 disclosure widening)

**Problem.** The Phase 7.7 honest-empty template fires when shortcut + open_now + zero rows. Template body opens "I have ... but I don't have current hours data", which matches the validator's `_I_DONT_KNOW_RE`. q10 + q12 in `halt3_eval_set.yaml` pin `expected_disclosure_path: cited` (singular string), but they legitimately route through the honest-empty template → classify as `i_dont_know`. Need to widen the pin to a list-or-scalar that accepts both paths.

**The validator code at HEAD does NOT yet support a list-form `expected_disclosure_path` field.** The widening requires both YAML edits AND validator code changes.

### §1.1 Validator code changes — `app/chat/halt3_validator.py`

Apply these in this order:

**1.1.a — Add type alias** (after line 20):

Find:
```python
DisclosurePath = Literal["cited", "uncited", "i_dont_know"]
ExpectedTier = Literal["tier1", "tier2", "tier3", "gap_template", "chat"]
ExpectedTierField = ExpectedTier | list[ExpectedTier]
```

Insert a new line so it becomes:
```python
DisclosurePath = Literal["cited", "uncited", "i_dont_know"]
DisclosurePathField = DisclosurePath | list[DisclosurePath]
ExpectedTier = Literal["tier1", "tier2", "tier3", "gap_template", "chat"]
ExpectedTierField = ExpectedTier | list[ExpectedTier]
```

**1.1.b — Update `EvalQuerySpec.expected_disclosure_path` annotation:**

Find:
```python
    expected_tier: ExpectedTierField
    expected_disclosure_path: DisclosurePath
    expected_confabulation_rate: float
```

Replace `DisclosurePath` with `DisclosurePathField`:
```python
    expected_tier: ExpectedTierField
    expected_disclosure_path: DisclosurePathField
    expected_confabulation_rate: float
```

**1.1.c — Add `_coerce_disclosure_path` helper** (after `_coerce_expected_tier`):

Find:
```python
def _coerce_expected_tier(raw_val: object) -> ExpectedTierField:
    if isinstance(raw_val, list):
        return [str(x) for x in raw_val]  # type: ignore[list-item, return-value]
    return str(raw_val) if raw_val is not None else "any"  # type: ignore[return-value]
```

Add this AFTER that function:
```python


def _coerce_disclosure_path(raw_val: object) -> DisclosurePathField:
    """Phase 7.7.1: accept either a scalar path or a list-or-allowlist of paths
    (mirrors _coerce_expected_tier). The list form supports rows like q10/q12
    where the Phase 7.7 honest-empty template legitimately shifts the
    classification between `cited` (tier-2 listing) and `i_dont_know`
    (honest-empty template body matches _I_DONT_KNOW_RE)."""
    if isinstance(raw_val, list):
        return [str(x) for x in raw_val]  # type: ignore[list-item, return-value]
    return str(raw_val) if raw_val is not None else "uncited"  # type: ignore[return-value]
```

**1.1.d — Update `load_eval_set` to use the coercer:**

Find:
```python
                expected_disclosure_path=str(row["expected_disclosure_path"]),  # type: ignore[arg-type]
```

Replace with:
```python
                expected_disclosure_path=_coerce_disclosure_path(row["expected_disclosure_path"]),
```

**1.1.e — Add `_disclosure_matches` + `_expected_includes_cited` helpers** (after `_tier_matches`):

Find the end of `_tier_matches` function — it ends with `return actual == _norm(expected)`. Add these two functions after it:

```python


def _disclosure_matches(expected: DisclosurePathField, actual: str) -> bool:
    """Phase 7.7.1: match an actual disclosure path against an expected path or
    allowlist of paths (mirrors _tier_matches). The list form supports rows
    like q10/q12 where the Phase 7.7 honest-empty template legitimately shifts
    the classification between `cited` and `i_dont_know`."""
    if isinstance(expected, list):
        if not expected:
            return False
        return actual in expected
    return actual == expected


def _expected_includes_cited(expected: DisclosurePathField) -> bool:
    """True when the spec's expected disclosure path accepts `cited`.
    Phase 7.7.1: needed for the cited-coverage metric when expected is a list."""
    if isinstance(expected, list):
        return "cited" in expected
    return expected == "cited"
```

**1.1.f — Update the comparison call site:**

Find:
```python
        if disc != spec.expected_disclosure_path:
            failures.append(
                f"disclosure expected {spec.expected_disclosure_path}, got {disc}"
            )
```

Replace with:
```python
        if not _disclosure_matches(spec.expected_disclosure_path, disc):
            failures.append(
                f"disclosure expected {spec.expected_disclosure_path}, got {disc}"
            )
```

**1.1.g — Update the cited filter:**

Find:
```python
    cited = [r for r in results if r.spec.expected_disclosure_path == "cited"]
    cited_ok = sum(1 for r in cited if r.disclosure_path == "cited")
    cited_cov = (cited_ok / len(cited)) if cited else 1.0
```

Replace with:
```python
    # Phase 7.7.1: include list-form expected paths that contain "cited" as
    # a candidate; a row with expected=[cited, i_dont_know] counts toward
    # cited coverage if its actual is "cited" (the canonical cited-tier path).
    cited = [r for r in results if _expected_includes_cited(r.spec.expected_disclosure_path)]
    cited_ok = sum(1 for r in cited if r.disclosure_path == "cited")
    cited_cov = (cited_ok / len(cited)) if cited else 1.0
```

### §1.2 YAML widening — `app/chat/halt3_eval_set.yaml`

**q10 widening.** Find:
```yaml
- id: q10
  query: "where can I take my dog for breakfast?"
  expected_tier: [tier2, gap_template]
  expected_disclosure_path: cited
  expected_confabulation_rate: 0.0
  notes: "Cross-entity multi-domain; tier-2 listing is primary dev path (gap on other runs)."
```

Replace with:
```yaml
- id: q10
  query: "where can I take my dog for breakfast?"
  expected_tier: [tier2, gap_template]
  expected_disclosure_path: [cited, i_dont_know]
  expected_confabulation_rate: 0.0
  notes: "Cross-entity multi-domain; tier-2 listing is primary dev path (gap on other runs). Phase 7.7 honest-empty template fires when open_now+category set + zero rows; template body 'I have ... but I don't have current hours data' matches _I_DONT_KNOW_RE → disclosure widened 2026-05-21 (Phase 7.7.1) to accept either cited or i_dont_know."
```

**q12 widening.** Find:
```yaml
- id: q12
  query: "indoor dining when it's hot"
  expected_tier: [tier2, gap_template]
  expected_disclosure_path: cited
  expected_confabulation_rate: 0.0
  notes: "Heat-bias path; tier-2 listing is primary dev path (gap on other runs)."
```

Replace with:
```yaml
- id: q12
  query: "indoor dining when it's hot"
  expected_tier: [tier2, gap_template]
  expected_disclosure_path: [cited, i_dont_know]
  expected_confabulation_rate: 0.0
  notes: "Heat-bias path; tier-2 listing is primary dev path (gap on other runs). Phase 7.7 honest-empty template fires on zero rows; classifies as i_dont_know via _I_DONT_KNOW_RE — widened 2026-05-21 (Phase 7.7.1)."
```

### §1.3 Verify + commit IMMEDIATELY

```powershell
python -m pytest tests/test_halt3_validator_hardening.py tests/test_phase7_halt3_validation.py -x --tb=short
python -m app.chat.halt3_validator
```

Expected: validator full eval shows 30/30 PASS with q10 + q12 either passing as `cited` OR `i_dont_know` (whichever fires that run). Hardening tests stay green (24 + 1 skipped, or current count + 0 new).

If validator shows `all_passed=True`, commit immediately:

```powershell
git add app/chat/halt3_validator.py app/chat/halt3_eval_set.yaml
git commit -m "feat(phase7.7.1): widen expected_disclosure_path to list-or-scalar -- q10/q12 accept both cited and i_dont_know paths (Phase 7.7 honest-empty template legitimately shifts classification when open_now+category+zero_rows); new DisclosurePathField type alias + _coerce_disclosure_path + _disclosure_matches helpers (mirror _tier_matches pattern); _expected_includes_cited helper for cited-coverage metric; validator 30/30 preserved"
git push
```

**DO NOT proceed to §2 until §1 is pushed.** The IDE corruption hazard means uncommitted changes are vulnerable.

---

## §2 Patch B — Phase 8a.0 (SourceLimiter signature mismatch hotfix)

**Problem.** Phase 8a's three fetchers (airnow / nws / usgs) call `_XXX_LIMITER.call_with_retry(_inner, client)` — passing `_inner` (a callable) plus `client` (an httpx.Client). But `SourceLimiter.call_with_retry` only accepts a single no-arg callable per its signature at `app/contrib/rate_limiter.py:113`:

```python
def call_with_retry(self, fn: Callable[[], httpx.Response]) -> httpx.Response:
```

The extra `client` arg causes `TypeError: SourceLimiter.call_with_retry() takes 2 positional arguments but 3 were given`. The outer `with_retry` envelope in `app/conditions/fetcher.py:67` swallows the TypeError as a "retryable exception" and exhausts retries, surfacing as `RuntimeError: fetch exhausted for <source>`.

Diagnostic confirmed: `railway run python -c "..."` with a direct API call to AirNow returned `200 OK` with real data (AQI 44 from Blythe, CA). The API works; the fetcher's wrapping is broken.

### §2.1 Fix — `app/conditions/airnow.py`

Find:
```python
    with httpx.Client() as client:
        response = _AIRNOW_LIMITER.call_with_retry(_inner, client)
```

Replace with:
```python
    with httpx.Client() as client:
        # SourceLimiter.call_with_retry takes a no-arg callable; close over
        # `client` via lambda (Phase 8a.0 hotfix 2026-05-21 — original signature
        # passed `client` as a second positional arg → TypeError swallowed by
        # outer with_retry as "exhausted").
        response = _AIRNOW_LIMITER.call_with_retry(lambda: _inner(client))
```

### §2.2 Fix — `app/conditions/nws.py`

Find:
```python
    with httpx.Client() as client:
        response = _NWS_LIMITER.call_with_retry(_inner, client)
    if response is None:
        raise RuntimeError(f"NWS request failed: {path}")
```

Replace with:
```python
    with httpx.Client() as client:
        # Phase 8a.0 hotfix 2026-05-21: SourceLimiter.call_with_retry takes a
        # no-arg callable; close over `client` via lambda.
        response = _NWS_LIMITER.call_with_retry(lambda: _inner(client))
    if response is None:
        raise RuntimeError(f"NWS request failed: {path}")
```

### §2.3 Fix — `app/conditions/usgs.py`

Find:
```python
            response = _USGS_LIMITER.call_with_retry(_inner, client)
            if response is None:
                continue
```

Replace with:
```python
            # Phase 8a.0 hotfix 2026-05-21: SourceLimiter.call_with_retry takes
            # a no-arg callable. USGS's `_inner` already defaults-closes over
            # `client` + `pcode`, so just drop the extra positional arg.
            response = _USGS_LIMITER.call_with_retry(_inner)
            if response is None:
                continue
```

### §2.4 Verify + commit IMMEDIATELY

```powershell
python -m pytest tests/test_phase8_fetcher_airnow.py tests/test_phase8_fetcher_nws.py tests/test_phase8_fetcher_usgs.py -x --tb=short
```

Expected: all Phase 8a fetcher unit tests pass (these use mocked httpx; they don't exercise the API).

Then commit:

```powershell
git add app/conditions/airnow.py app/conditions/nws.py app/conditions/usgs.py
git commit -m "fix(phase8a.0): SourceLimiter.call_with_retry signature mismatch -- all 3 fetchers passed client as a second positional arg but the method only accepts a no-arg callable; outer with_retry swallowed TypeError as exhausted so the bug masqueraded as 6 transient failures; fix wraps _inner in a lambda that closes over client (airnow/nws) or drops the extra arg (usgs, which already defaults-closes over client+code); diagnosed via railway run python with direct API probe showing 200 OK while fetcher wrapper failed"
git push
```

---

## §3 Post-push prod fetch + smoke

After Railway redeploys (~30-60s):

```powershell
railway run python -m scripts.fetch_external_conditions --all
```

Expected: NO "failed sources" line. All 6 sources should succeed (AirNow, NWS alerts/current/forecast/sunset, USGS).

Then smoke `/api/conditions`:

```powershell
$base = "https://havasu-chat-production.up.railway.app"
Invoke-RestMethod -Uri "$base/api/conditions" | ConvertTo-Json -Depth 5
```

Expected: payload now contains AQI + temperature + AZZ002 alerts + lake gauge + reservoir storage (not just `rendered_at_iso`). The `/home` conditions strip should populate within 60s (the JS poller's cadence).

---

## §4 Full pytest sanity check

After both commits land:

```powershell
python -m pytest -x --tb=short 2>&1 | Select-Object -Last 10
```

Expected: 2240+ passed, 0 failed. If any unexpected failure surfaces, paste the traceback to the operator and HALT.

---

## §5 Final report

Output a tight summary with:

1. §0 prereq state — was IDE clean? was git tree clean before reset?
2. §1 Phase 7.7.1 — commit SHA + line counts + pytest result + validator 30/30 result
3. §2 Phase 8a.0 — commit SHA + line counts + pytest result
4. §3 prod fetch result — sources that succeeded / failed
5. §3 prod smoke — keys in /api/conditions payload
6. §4 full suite count
7. Any surprises encountered (especially: did the IDE corruption re-emerge mid-session? if so, capture which file + when)

---

## §6 Hard rules

- **Commit IMMEDIATELY after each patch** (§1 push before §2 starts). Uncommitted changes are vulnerable to the IDE buffer corruption hazard.
- **Do NOT edit files outside the listed scope.** §1 = validator.py + halt3_eval_set.yaml. §2 = airnow.py + nws.py + usgs.py. Anything else → HALT and report.
- **Do NOT touch the migration `d8e9f0a1b2c3`** — it's already applied to dev DB; touching it can break alembic state.
- **Do NOT re-author the diagnostic** — the corruption diagnosis runs in a separate dispatch at `outputs/cursor_ide_buffer_corruption_diagnosis.md`. Stay scoped to recovery + fix.
- **Bail on the unexpected.** If `git restore` doesn't clean the tree, if pytest fails in unexpected places, if `railway run` returns weird errors — STOP and report. Don't improvise.

---

*Authored 2026-05-21 post-IDE-corruption-replay-#2. Saved to `outputs/cursor_recovery_phase_7_7_1_plus_8a_0.md`.*
