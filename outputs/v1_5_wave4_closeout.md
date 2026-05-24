# V1.5 wave 4 close-out — §11 deviations + §13 report

**Lane:** Layer-4 verifiers #22 AZ TPT + #23 BBB  
**Dispatch:** `outputs/cursor_dispatch_prompt_v1_5_wave4_layer4_verifiers.md`  
**Pin SHA at dispatch:** `e3e8a76`  
**Recon redirect:** Cowork primary `outputs/chrome_mcp_captcha_recon_v22.md` (2026-05-24)  
**Final lane outcome:** **#23 BBB shipped; #22 AZ TPT deferred** (operator-action package)

---

## §11 Deviations

### #22 AZ TPT — HALT (scope mismatch + reCAPTCHA v2)

| Field | Value |
|---|---|
| **Item** | #22 AZ TPT verifier |
| **Planned approach** | Name-based fuzzy match against AZTaxes TPT registry (mirror BBB / AZ MVD) |
| **Actual surface** | `https://www.aztaxes.gov/Home/LicenseVerification` — **8-digit license number only**; no business-name search; no bulk roster |
| **Captcha** | Google reCAPTCHA v2 checkbox on page load; Submit disabled until solved |
| **Decision** | **Do not ship** `app/contrib/aztpt_client.py`, `scripts/aztpt_verify.py`, or `tests/test_phase5_aztpt_verify.py`. Defer to v23 inventory carry. |
| **Risk** | Low — no false positives from an inert Playwright stub that could never match by name |
| **Operator escalation** | None required before BBB-only ship; Path A public-records request documented in `docs/operations/aztpt_manual_verification.md` |
| **Evidence** | `outputs/chrome_mcp_captcha_recon_v22.md` §2 (Chrome MCP DOM + reCAPTCHA); wave 4 §7 HALT ("no usable public verifier" for planned use case) |

**Note:** An initial commit (`96d978c`) included functional-but-inert AZ TPT files
before recon redirect landed. Follow-up removes those three files and adds the
operator-action doc above.

### #23 BBB — shipped as planned (with expected automation caveat)

| Field | Value |
|---|---|
| **Probe path** | httpx + BeautifulSoup category-walk (`/us/az/lake-havasu-city/categories` → `/category/<slug>/accredited`) |
| **Scope** | §3.0 (a) `shopping-essentials` only |
| **Attributes key** | `attributes["bbb"]` |
| **Match threshold** | 86 (`rapidfuzz.token_sort_ratio` + `utils.default_process`) |
| **Functional-but-inert caveat** | Accredited listing pages may return 403/Cloudflare from automation IPs; client early-aborts and returns `[]` (pattern win 33). Live yield expected from operator network / prod dry-run. |
| **Risk** | Low — tests mock fetch; prod may see `skipped_no_match` until IP allows BBB HTML |

### §3.2 dep-grep (mandatory)

| Dep | Present in stack |
|---|---|
| playwright | Yes (`app/contrib/az_roc_client.py`, `azcc_towing_client.py`) |
| bs4 | Yes |
| httpx | Yes |
| rapidfuzz | Yes |

**No new deps added.**

### §3.0 scope

Operator confirmed (a) narrow `shopping-essentials` — no escalation.

---

## §13 Close-out

| Gate | Result |
|---|---|
| **Pytest before** | 2453 collected (dispatch baseline) |
| **Pytest after (BBB-only ship)** | 2460 collected (+7 net-new BBB tests; AZ TPT tests removed) |
| **Ruff** | All checks passed |
| **Alembic** | Single head `a9b0c1d2e3f4` unchanged |
| **HALT 3 eval** | 13 passed / 1 skipped (baseline preserved) |
| **Prior-wave verifier regression** | Pass (azdhs, azre, azmvd, azcc_towing) |
| **Dep impact** | `requirements.txt` / `pyproject.toml` unchanged |
| **Files added (BBB ship)** | `app/contrib/bbb_client.py`, `scripts/bbb_verify.py`, `tests/test_phase5_bbb_verify.py` |
| **Files added (operator package)** | `docs/operations/aztpt_manual_verification.md` |
| **Files removed (#22 deferral)** | `app/contrib/aztpt_client.py`, `scripts/aztpt_verify.py`, `tests/test_phase5_aztpt_verify.py` |
| **Net LOC (BBB only)** | ~637 LOC across 3 code files + operator doc |
| **Functional-but-inert flag** | BBB may be inert from blocked automation IPs; #22 not shipped (deferred, not inert stub) |
| **New carries** | #22 remains open — re-tag: bulk CSV import OR manual verification; not Playwright name-search |

### Operator dry-run (post-ship)

```powershell
python -m scripts.bbb_verify --dry-run --limit 5
```

---

*Close-out authored 2026-05-24 after Cowork primary recon redirect.*
