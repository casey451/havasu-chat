# AZCC captcha unblock -- design doc (v23)

**Authored:** 2026-05-24 (v23 session, sub-agent A).
**Predecessor:** `outputs/chrome_mcp_captcha_recon_v22.md` (v22 parallel-lane recon).
**Amended:** 2026-05-24 v25 -- Q3 answered empirically; see `outputs/azcc_derisk_findings_2026_05_24_v25.md`.
**Amended:** 2026-05-24 v26 -- Q5 + Q6 answered via Chrome MCP live probe; see `outputs/azcc_q5_q6_probe_v26.md` and Section 8 below. Path (c) shipped at commit `47d45e3` (CI #429 green).
**Status:** v26-amended; implementation shipped. Only Q1 (cookie TTL) and Q2 (cookie scope) remain open -- both operator-paced, neither blocking.

---

## Section 0 -- Context

The AZCC towing verifier (V1.5 Layer-4 bundle ticket #21, wave-3) currently soft-fails on the Arizona Corporation Commission public business search captcha. Per the wave-3 client at `app/contrib/azcc_towing_client.py` lines 125-131, when the portal renders the "User validation required to continue" modal the client returns `{"succeeded": False, "data": []}` and the verifier counts the row as `skipped_no_match`. Net effect from production: AZCC matches asymptote to ~0 from CI / Railway IPs. v22 Chrome MCP recon confirmed the captcha is a custom Angular image-captcha (not reCAPTCHA / hCaptcha / Cloudflare Turnstile), which is materially easier to defeat than the AZ TPT reCAPTCHA v2 surface. The goal of this doc is to compare three unblock paths, pick one, and outline integration + test work without writing code.

---

## Section 1 -- Captcha surface (per v22 recon, section 1)

| Property            | Value                                                                  |
|---------------------|------------------------------------------------------------------------|
| Type                | Custom Angular image-captcha (`class="captcha-image ng-star-inserted"`) |
| Vendor              | None -- AZCC in-house component                                        |
| Image format        | Base64-encoded PNG, inline `data:image/png;base64,...` URL             |
| Image size          | ~7.3 KB decoded PNG (~9.8 KB data URL) -- v26 measured                  |
| Image dimensions    | 200x80 px (v26 confirmed: `naturalWidth`/`naturalHeight`)               |
| Charset             | 6 alphanumeric chars (mixed case + digits)                             |
| Distortion          | Mild -- grid/dot noise overlay, light glyph warping                    |
| Refresh button      | Present -- operator/client can request a new challenge                 |
| Trigger             | On form submit only; not on page load                                  |
| Modal title         | "User validation required to continue"                                 |
| Input               | Single text field "Enter the text shown above" + "Verify" button       |
| Modal count         | Exactly one dialog at a time                                           |
| Session cookie TTL  | Estimated ~30 min after successful solve (v22 recon, unverified)       |

---

## Section 2 -- Three candidate paths

### Path (a) -- Tesseract OCR auto-solve

**Deps added:** `pytesseract` (Python wrapper, ~30 KB) and the Tesseract binary itself (system package, ~30 MB installed). Pillow is already pinned at 12.0.0 in `requirements.txt` so no new image-handling dep is needed.

**Code changes:** new module `app/contrib/_azcc_captcha_solver.py` (~60-80 lines) wrapping `pytesseract.image_to_string` with a preprocessing pipeline (greyscale, threshold, denoise via Pillow). The captcha-detection block in `azcc_towing_client.py:~125` grows from 6 lines to ~30 lines: locate the captcha img, extract the base64 data URL, decode -> Pillow Image, OCR, fill input, click Verify, observe success, retry on failure with refresh. Estimate +25 LOC in `azcc_towing_client.py`, +70 LOC new solver module.

**Docker/Railway changes:** Dockerfile needs `RUN apt-get install -y tesseract-ocr tesseract-ocr-eng`. Railway Nixpacks builder needs an `aptPkgs = ["tesseract-ocr"]` line in `nixpacks.toml` (or `nix.aptPkgs` in Railway settings). This is a non-trivial deploy-config change that warrants a dry-run on a Railway branch.

**Effort estimate:** S (1-2 hours including Docker tweak + tests).

**Expected success rate (v23 estimate, superseded by v25):** ~~50-70% per attempt~~. **v25 empirical floor:** Tesseract 4.1.1 (likely Nixpacks default) achieves **23-25% first-try exact-match** on synthetic 200x80 mixed-case 6-char captchas (`outputs/azcc_derisk_findings_2026_05_24_v25.md` Section B). At 25%/try, 3 attempts yield ~58% effective success; **9+ attempts** are needed for 90%+. Case-distinction and similar-glyph confusion dominate; preprocessing does not fix this.

**v25 recommendation:** path (a) is **fallback only, behind feature flag default-off** -- not a viable standalone primary. Do not ship Tesseract binary until flag enabled (defers Q4 image-size impact).

**Risk + mitigation:** AZCC could rate-limit refresh requests (mitigation: **cap Tesseract retries at 3 max** regardless of math; fall through to `skipped_no_match` or cookie re-seed). Q5 refresh rate-limit empirics are now **CRITICAL** -- a 9-retry loop is non-viable if AZCC throttles refresh. Tesseract may produce confident-wrong answers (mitigation: rely on portal validation; wrong solve yields another modal).

---

### Path (b) -- Manual operator cookie-seed

**Deps added:** none.

**Code changes:** new env var `AZCC_SESSION_COOKIE` (operator-set, sourced from `.env` via existing `app.bootstrap_env.ensure_dotenv_loaded`). The client gains a branch: if the env var is set, pass it into the Playwright `BrowserContext` via `context.add_cookies(...)` before navigating, and the form-submit XHR rides the existing session. Estimate +20 LOC in `azcc_towing_client.py`. Add a one-shot operator helper `scripts/azcc_seed_cookie.py` (~40 LOC) that opens a headed Playwright browser, waits for the operator to solve the captcha manually, dumps the resulting session cookies to stdout in `KEY=VALUE` form for paste-into-`.env`.

**Docker/Railway changes:** none for runtime. Operator runs the seed script on their local machine.

**Effort estimate:** XS (45 min including seed helper).

**Expected success rate:** 100% per pass while the cookie is fresh. Drops to 0% once the session expires (estimated 30 min per v22 recon; needs empirical confirmation). The verifier is a periodic batch job (not real-time), so a long pass could outrun a single cookie.

**Risk + mitigation:** cookie staleness mid-pass forces a re-seed (mitigation: chunk batch sizes to fit under TTL, or detect captcha re-appearance mid-pass and fall through to `skipped_no_match` for the remainder). Operator burden is recurring -- every pass needs a fresh manual solve (mitigation: combine with path (a) so manual solve is only a fallback). Cookie in plaintext env var is a mild secret-hygiene concern but matches the existing `.env` pattern for other creds.

---

### Path (c) -- Hybrid (cookie first, Tesseract fallback, soft-fail terminal)

**Deps added:** same as path (a), but Tesseract install is **deferred** until `AZCC_TESSERACT_ENABLED=1` (or equivalent feature flag).

**Code changes:** combines (a) and (b). At captcha-detection time the client **first** checks for `AZCC_SESSION_COOKIE` and uses it as a session prime (skips the captcha modal entirely if the cookie is still good). On captcha modal appearance, if feature flag enabled, run the Tesseract solver with **max 3 refresh-retries** (conservative cap pending Q5 empirics). If OCR exhausted, no cookie, or flag off, fall through to today's `skipped_no_match` behavior. Estimate +50 LOC in `azcc_towing_client.py`, +70 LOC new solver module (flag-gated), +40 LOC seed helper.

**Docker/Railway changes:** Tesseract binary install **only when feature flag path is enabled**; ship cookie infra first with zero image growth.

**Effort estimate:** S-M (3-4 hours) -- cookie infra is now load-bearing, not optional.

**Expected success rate:** ~100% while cookie is fresh (Q1 TTL still unverified); Tesseract fallback adds ~58% effective success over 3 tries at v25-measured 25%/try -- insufficient alone. Soft-fail when both fail.

**Risk + mitigation:** cookie staleness mid-pass is now the primary failure mode (mitigation: Q1 TTL probe, chunk batch sizes, detect re-modal mid-pass). Code-path complexity grows (mitigation: separate small modules; client orchestrates only). Two new failure modes to test (mitigation: see section 5).

---

## Section 3 -- Recommendation

**Ship path (c) hybrid with cookie-primary ordering (v25 revision).** v25 empirical probe (`outputs/azcc_derisk_findings_2026_05_24_v25.md`) shows Tesseract 4.1.1 at 23-25%/try -- 2-3x below the v23 50-70% estimate -- so OCR cannot carry the load alone. Cookie seeding is the primary unblock; Tesseract is a **feature-flag fallback default-off**.

The marginal effort over path (b) alone is modest (+flag-gated solver module, +3-retry cap). Operational upside: ship cookie path immediately without 30 MB Tesseract in the image; enable OCR later if cookie ops prove burdensome or v5 re-probe shows better accuracy.

Path (b) alone is rejected because mid-pass cookie expiry (Q1 unverified) risks silent zero-yield without OCR fallback. Path (a) alone is rejected because 23-25%/try requires 9+ retries for 90% success -- impractical without Q5 rate-limit clearance. Path (c) cookie-first preserves graceful degradation: fresh cookie -> full yield; stale cookie + flag off -> today's soft-fail; stale cookie + flag on -> modest OCR lift.

---

## Section 4 -- Integration sketch (pseudocode, no real code)

The captcha-detection block at `azcc_towing_client.py:~125` evolves roughly like this:

```
inside _fetch_public_search_payload:
    # NEW: if operator seeded a session cookie, prime the context before nav
    if env AZCC_SESSION_COOKIE present:
        context.add_cookies(parsed cookie list)

    # existing: navigate, fill name, click Business Search, wait

    if captured (XHR intercepted):
        return captured

    # NEW: captcha-modal branch (replaces today's lines 126-131)
    if page has text "User validation required":
        if env AZCC_TESSERACT_ENABLED:
            for attempt in 1..AZCC_TESSERACT_MAX_RETRIES (default 3):
                img_b64 = locate captcha img element, read src data-URL
                decoded = base64-decode and Pillow-open
                preprocessed = greyscale -> threshold -> denoise
                guess = pytesseract.image_to_string(preprocessed, alphanum-whitelist)
                if guess looks like 6 alphanumeric chars:
                    fill captcha input with guess
                    click Verify
                    wait briefly for XHR or new modal
                    if captured (XHR fired) -> return captured
                if modal still present -> click refresh, loop
        # OCR disabled, exhausted, or no cookie re-seed available
        log azcc_towing_client.captcha_unsolved
        return {"succeeded": False, "data": []}   # same soft-fail as today

    # existing: mat-table fallback parse
```

The function signature and return shape are unchanged so `scripts/azcc_towing_verify.py` and `_normalize_search_rows` need no edits.

---

## Section 5 -- Test plan

**New tests** in `tests/test_phase5_azcc_towing_verify.py` (or a sibling unit file for client-internals):

- `test_captcha_solver_decodes_base64_data_url` -- feed a known 6-char synthetic PNG (committed as a small test fixture), assert OCR returns the expected string. Use a real `pytesseract` call gated behind a `pytest.mark.skipif` if Tesseract binary not on PATH so CI without the binary skips rather than fails.
- `test_captcha_solver_retries_on_garbage_output` -- mock `pytesseract.image_to_string` to return non-6-char garbage twice then a valid string; assert the loop refreshes and eventually succeeds.
- `test_captcha_solver_soft_fails_after_three_attempts` -- mock OCR to always return garbage; assert client returns `{"succeeded": False, "data": []}` and emits the `captcha_unsolved` log.
- `test_session_cookie_primes_context` -- set `AZCC_SESSION_COOKIE` env, assert `context.add_cookies` is called with the parsed cookie list before `page.goto`.
- `test_cookie_path_bypasses_captcha_modal` -- with cookie set and Playwright mocked to capture an XHR without showing a modal, assert the client returns captured rows without invoking the OCR solver at all.

**Existing tests to update:**

- The existing `test_azcc_captcha_blocked` (or equivalent in the current wave-3 test file) needs renaming -- the soft-fail path is now the terminal branch only, not the unconditional behavior. Re-assert it under the "OCR exhausted + no cookie" scenario.
- Any test that monkeypatches `_fetch_public_search_payload` should still pass since the public function signature is unchanged.

**Mocking strategy:**

- Wrap the Playwright `sync_playwright` call in a thin shim so tests can substitute a fake page object exposing `.locator`, `.get_by_text`, `.on`, `.goto` etc. (this may already exist for wave-3 -- check before duplicating).
- Stub `pytesseract.image_to_string` directly for solver-loop tests; only the fixture-decode test hits the real binary.
- For the cookie path, mock `BrowserContext.add_cookies` and assert call args.

---

## Section 6 -- Open questions for operator

| # | Question | Status (post-v26) | Priority | Notes |
|---|----------|-------------------|----------|-------|
| 1 | **Session cookie TTL** | OPEN | **CRITICAL** | Cookie-primary path depends on this. Probe: solve manually, poll API at 5/15/30/60/120 min. ~2 hr elapsed, ~5 min active. Ready-to-run probe: `scripts/azcc_q1_q2_operator_probe.py` (captures Q1 + Q2 in single session). |
| 2 | **Cookie scope (HttpOnly/SameSite)** | OPEN | **HIGH** | Must survive Playwright contexts. Captured by `scripts/azcc_q1_q2_operator_probe.py` immediately on solve detect -- prints full attribute table to stdout and writes JSON report under `outputs/`. |
| 3 | **Tesseract version pin** | **ANSWERED (v25)** | -- | Accept Nixpacks default (likely 4.1.1). Empirical: **23-25%/try** on synthetic 200x80 mixed-case captchas. Pin v5 = MAYBE iff cookie path fails; vendor specific = NO. See `outputs/azcc_derisk_findings_2026_05_24_v25.md` Section B. |
| 4 | **Railway deploy-tier impact (~30 MB Tesseract)** | DOWNGRADED (v25) | -- | Defer -- Tesseract behind feature flag default-off; no image growth until enabled. |
| 5 | **Refresh rate-limit empirics** | **ANSWERED (v26)** | -- | No client-side throttle at sustained ~5 req/sec from residential IP. 30 parallel `fetch()` to `/api/Captcha/generate` all 200 OK in 6.1 s, zero throttle headers. 3-retry default safe; 5-retry hard cap safe. See `outputs/azcc_q5_q6_probe_v26.md` Section C. |
| 6 | **Captcha image dimensions sanity-check** | **ANSWERED (v26)** | -- | 200x80 px PNG confirmed via DOM (`naturalWidth`/`naturalHeight`); 9.8 KB data URL, 7.3 KB decoded. Tesseract pipeline operates on correct dimensions without resize. See `outputs/azcc_q5_q6_probe_v26.md` Section B. |

**v25 net:** Q3 closed; Q4/Q6 downgraded; Q1/Q2/Q5 sharpened. Ship can proceed with cookie-primary defaults; remaining questions are not scoping blockers.
**v26 net:** Q5 and Q6 closed via Chrome MCP probe (no throttle, 200x80 confirmed). Only Q1 and Q2 remain; both operator-paced and non-blocking. Operator probe script for Q1+Q2 (single run): `scripts/azcc_q1_q2_operator_probe.py` (v27 carry).

---

## Section 7 -- v25 amendment summary (2026-05-24)

Source: `outputs/azcc_derisk_findings_2026_05_24_v25.md` (Cowork sandbox probe, Tesseract 4.1.1 + pytesseract 0.3.13).

| Metric | v23 assumption | v25 measured |
|--------|----------------|--------------|
| Per-try OCR accuracy | 50-70% | **23-25%** (either raw or preprocessed) |
| 3-retry effective success | ~90-95% | **~54-58%** |
| Attempts for 90% success | 3 | **9+** |
| Primary unblock path | Tesseract | **Cookie seed** |
| Tesseract deploy | Required in image | **Feature flag, default-off** |

Probe scripts (Cowork sandbox canonical): `outputs/_v25_tesseract_probe.py`, `outputs/_v25_tesseract_probe_mild.py` (RNG_SEED=20260524, 100 samples each).

---

## Section 8 -- v26 amendment summary (2026-05-24)

Source: `outputs/azcc_q5_q6_probe_v26.md` (Cowork primary, Chrome MCP live probe against `https://arizonabusinesscenter.azcc.gov/businesssearch`).

| Question | v25 status | v26 measurement | Resolution |
|----------|------------|-----------------|------------|
| Q5 refresh rate-limit | OPEN, CRITICAL | 30 parallel `fetch()` to `/api/Captcha/generate` -> 30x 200 OK in 6.1 s; zero `Retry-After`, zero `X-RateLimit-*` headers; per-request 474-6110 ms (browser-side queueing, not server). 20 spaced Angular button-clicks at ~1/s also 21/21 200 OK. | **CLOSED.** 3-retry default safe by a wide margin; 5-retry hard cap also safe. Lifting to 9 would push effective OCR success to ~93% at +9 s tail latency. |
| Q6 image dimensions | OPEN, DOWNGRADED | DOM `naturalWidth`/`naturalHeight` = 200/80 px; `srcLength` 9790 chars; decoded PNG 7326 bytes; `className` `captcha-image ng-star-inserted`. | **CLOSED.** Matches v22 DOM recon. Tesseract preprocessing pipeline operates on correct dimensions without resize. |

Probe caveats: single residential IP (Railway egress could behave differently); no sustained-load testing beyond 30/burst; no `Set-Cookie` capture (Q2 still open, intentionally deferred to operator probe).

**Shipped implementation:** commit `47d45e3f48bfe9e0eafc24f8013829562d7de0fe` ("wave-3 AZCC: cookie-primary captcha unblock + Tesseract feature-flag fallback") on `main`; CI #429 green. Files touched per v26 cursor dispatch (`outputs/cursor_dispatch_azcc_captcha_unblock_2026_05_24_v26.md` Section 1-2).

Post-v26 status: 4 of 6 design-doc open questions are CLOSED (Q3, Q4, Q5, Q6); Q1 (cookie TTL) and Q2 (cookie scope HttpOnly/SameSite) remain OPEN and are operator-paced. Neither is implementation-blocking with the shipped `_parse_session_cookies()` pass-through + conservative 3-retry default. Operator probe script for Q1/Q2 is at `scripts/azcc_q1_q2_operator_probe.py` (v27 carry handoff).

---

*End of design doc. v26 amendment applied 2026-05-24; cookie-primary path SHIPPED at commit `47d45e3`. Only Q1 (cookie TTL) and Q2 (cookie scope) remain, both operator-paced and non-blocking.*
