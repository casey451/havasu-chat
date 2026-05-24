# AZCC captcha unblock -- design doc (v23)

**Authored:** 2026-05-24 (v23 session, sub-agent A).
**Predecessor:** `outputs/chrome_mcp_captcha_recon_v22.md` (v22 parallel-lane recon).
**Status:** scope-only design doc; no code shipped this session.

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
| Image size          | ~9.3 KB                                                                |
| Image dimensions    | 200x80 px                                                              |
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

**Expected success rate:** 50-70% per attempt on mild-distortion 6-char captchas (Tesseract baseline for clean-ish synthetic captchas). With a 3-attempt retry loop using the refresh button, effective success approaches 90-95%.

**Risk + mitigation:** AZCC could rate-limit refresh requests (mitigation: cap retries at 3, fall through to `skipped_no_match`). AZCC could detect repeated OCR-style guesses and tighten distortion (mitigation: low-volume verifier, batch sizes are dozens per pass per `scripts.azcc_towing_verify`, not thousands -- detection risk is low). Tesseract may produce confident-wrong answers (mitigation: rely on the portal's own validation -- a wrong solve just yields another captcha modal, which the retry loop handles).

---

### Path (b) -- Manual operator cookie-seed

**Deps added:** none.

**Code changes:** new env var `AZCC_SESSION_COOKIE` (operator-set, sourced from `.env` via existing `app.bootstrap_env.ensure_dotenv_loaded`). The client gains a branch: if the env var is set, pass it into the Playwright `BrowserContext` via `context.add_cookies(...)` before navigating, and the form-submit XHR rides the existing session. Estimate +20 LOC in `azcc_towing_client.py`. Add a one-shot operator helper `scripts/azcc_seed_cookie.py` (~40 LOC) that opens a headed Playwright browser, waits for the operator to solve the captcha manually, dumps the resulting session cookies to stdout in `KEY=VALUE` form for paste-into-`.env`.

**Docker/Railway changes:** none for runtime. Operator runs the seed script on their local machine.

**Effort estimate:** XS (45 min including seed helper).

**Expected success rate:** 100% per pass while the cookie is fresh. Drops to 0% once the session expires (estimated 30 min per v22 recon; needs empirical confirmation). The verifier is a periodic batch job (not real-time), so a long pass could outrun a single cookie.

**Risk + mitigation:** cookie staleness mid-pass forces a re-seed (mitigation: chunk batch sizes to fit under TTL, or detect captcha re-appearance mid-pass and fall through to `skipped_no_match` for the remainder). Operator burden is recurring -- every pass needs a fresh manual solve (mitigation: combine with path (a) so manual solve is only a fallback). Cookie in plaintext env var is a mild secret-hygiene concern but matches the existing `.env` pattern for other creds.

---

### Path (c) -- Hybrid (Tesseract first, manual cookie fallback, soft-fail terminal)

**Deps added:** same as path (a).

**Code changes:** combines (a) and (b). At captcha-detection time the client first checks for `AZCC_SESSION_COOKIE` and uses it as a session prime (skips the captcha modal entirely if the cookie is still good). On captcha modal appearance, it runs the Tesseract solver with 3 refresh-retries. If all OCR attempts fail and no cookie is available, fall through to today's `skipped_no_match` behavior. Estimate +50 LOC in `azcc_towing_client.py`, +70 LOC new solver module, +40 LOC seed helper.

**Docker/Railway changes:** same as path (a) -- Tesseract binary install.

**Effort estimate:** S-M (2-3 hours).

**Expected success rate:** 95%+ when cookie is fresh OR Tesseract succeeds; soft-fail when both fail. Strictly dominates (a) and (b) individually.

**Risk + mitigation:** code-path complexity grows (mitigation: keep the solver and cookie-seed code in separate small modules; the client only orchestrates). Two new failure modes to test (mitigation: see section 5).

---

## Section 3 -- Recommendation

**Concur with v22 recon: ship path (c) hybrid.** The marginal effort over path (a) alone is small (an env-var branch and a seed helper script), and the operational upside is large -- when Tesseract degrades (e.g. AZCC tightens distortion), the manual cookie path keeps the verifier hot without any code change. When the operator forgets to seed, Tesseract carries the load. The only scenario that yields zero matches is both-paths-failed, which is no worse than today's terminal soft-fail. Path (b) alone is rejected because it puts a recurring manual burden on Casey for every pass and risks mid-pass cookie expiry; path (a) alone is rejected because it leaves no fallback when AZCC adapts the captcha. The hybrid is the only path that preserves graceful degradation in both directions.

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
        for attempt in 1..3:
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
        # all OCR attempts exhausted
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

1. **Session cookie TTL.** v22 recon estimated ~30 min but did not measure. Before shipping path (c), should we run a one-shot empirical probe (solve manually, then poll the API at 5/15/30/60 min) to size the operator re-seed cadence? Without this, the cookie branch may quietly stop working mid-pass.
2. **Cookie scope.** Is the AZCC session cookie HttpOnly / Secure / SameSite=Strict? If Strict, the cookie may not survive cross-domain redirects in Playwright contexts. v22 recon did not capture `Set-Cookie` headers (the relevant XHR fired before `read_network_requests` was armed).
3. **Tesseract version pin.** Tesseract 5.x vs 4.x have materially different accuracy on noisy captchas. Do we pin `tesseract-ocr >= 5` in the Dockerfile, accept whatever Railway Nixpacks ships, or vendor a specific version?
4. **Railway deploy-tier impact.** Adding a ~30 MB binary to the image pushes build time and cold-start. Acceptable? Or should the AZCC verifier move to a separate worker image so the main API stays lean?
5. **Refresh rate-limit empirics.** Does AZCC throttle the captcha-refresh endpoint? If yes, the 3-retry loop in path (a)/(c) may itself trip a rate limiter. Worth a probe before shipping.
6. **Captcha image dimensions sanity-check.** v22 recon reported 200x80 px from DOM attributes. The base64 payload at ~9.3 KB is on the high side for a 200x80 PNG -- worth decoding one to confirm the rendered size matches, since Tesseract preprocessing depends on knowing the true pixel grid.

---

*End of design doc. No code changes shipped; this is a scope-only artifact for Casey to review before authorizing a code-ship wave.*
