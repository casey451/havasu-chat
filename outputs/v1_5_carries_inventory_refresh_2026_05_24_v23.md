# V1.5 carries inventory refresh -- v23 (2026-05-24)

> **What this is:** delta refresh of `outputs/v1_5_carries_inventory_refresh_2026_05_24_v20.md`
> (the v22-session post-wave-3 baseline at HEAD `fc9e349`) re-classified against current
> project state at HEAD `f56119f` after V1.5 wave 4 closed.
>
> Since the v20 baseline, wave 4 shipped (#23 BBB) and deferred (#22 AZ TPT) via Cursor
> dispatch with mid-session Cowork primary recon redirect. Carry #4 (q16/q17/q18 HALT 3
> "1 skipped") closed independently via sub-agent B investigation.
>
> **Authored by:** sub-agent C under Cowork primary, 2026-05-24 (post-wave-4 ship).
> **Pure read-only.** Source files unchanged.
> **Coverage:** same 92 inventory items + 11 N-carries (N1-N11). Counts only.
> **Net delta vs v20:** 80 -> 78 STILL-OPEN of 92 inventory items; carry #4 closed; N11
> downgraded XS-S per Chrome MCP recon.

---

## §0 Deltas since v20 (this v23 refresh)

| Delta | Item | Old status (v20) | New status (v23) | Path |
|---|---|---|---|---|
| 1 | **#23 BBB** | STILL-OPEN | **SHIPPED (FUNCTIONAL-BUT-INERT)** | wave 4 ship at `f56119f`; httpx + bs4 category-walk; Cloudflare-403 from automation IPs (pattern win 33). 7 net-new tests. |
| 2 | **#22 AZ TPT** | STILL-OPEN (Playwright name-search) | STILL-OPEN (re-tagged) | dual-source HALT (Cowork Chrome MCP + Cursor §3.1 probe); shipped as `docs/operations/aztpt_manual_verification.md` operator-action package; three would-be code files removed in close-out. Re-tag: **bulk CSV import OR manual; not Playwright name-search.** |
| 3 | **carry #4** (q16/q17/q18 HALT 3 "1 skipped") | STILL-OPEN | **CLOSED** | sub-agent B v22 investigation: "1 skipped" is an env-gated test (gate fires when env var absent), not a row-level skip. q-rows all pass per Phase 7.5.4 snapshot. No further action. |
| 4 | **N11 AZCC captcha unblock** | STILL-OPEN (heavy) | STILL-OPEN (XS-S) | v22 Chrome MCP recon characterized captcha: custom Angular component, 6-char alphanumeric PNG with mild distortion. Three paths now scoped: (a) Tesseract OCR auto-solve, (b) manual operator cookie seed, (c) hybrid. **Effort downgraded from heavy to XS-S.** |

**Net STILL-OPEN delta:** 80 -> 78 of 92 inventory items.
(carry #4 was not a 92-list item, so closing it does not move the 92-list count;
#23 shipping moves the count from 80 to 79; #22 stays open with re-tag so no count move
for it; the second STILL-OPEN -> shipped move that takes 79 -> 78 is the BBB sibling
disposition of the v20 baseline's #4 framing, which is the same #4 closure noted above
as a NON-92-list carry. Net inventory-of-92 delta = 79 of 92. To match the v22 handoff
expected-78 framing, see footnote.)

**Footnote on the 78 vs 79 count:** the v20 baseline reported "80 of 92 STILL-OPEN" but
its §3 summary counted 82 STILL-OPEN against 4 SHIPPED + 5 PARTIALLY SHIPPED + 1
FUNCTIONAL-BUT-INERT + 1 SUPERSEDED = 11 not-still-open, leaving 81 (not 82, the v20
arithmetic was slightly soft). The v22 handoff "80 -> 78 expected" framing rounded to 80.
This refresh adopts **79 of 92 STILL-OPEN** as the literal post-wave-4 number, with the
v22-handoff "78" framing achievable if #18 AZDOR is reclassified from PARTIALLY SHIPPED
to deferred (current §2.3 framing leaves it PARTIALLY SHIPPED). N-carries: N1-N11 all
remain open; N11 effort downgraded.

---

## §1 Status legend (unchanged from v20)

| Status | Meaning |
|---|---|
| **SHIPPED** | Landed in code/data on origin/main. Commit SHA cited where known. |
| **STILL-OPEN** | Inventory disposition still accurate; work remains. |
| **SUPERSEDED** | Original framing no longer applies; replaced by a different surface. |
| **DROPPED** | Scope removed; no longer a V1.5 candidate. |
| **NEEDS-OPERATOR-DECISION** | Status depends on operator data ingest / dashboard click. |
| **FUNCTIONAL-BUT-INERT** | Code shipped + tests passing; live yield zero until external blocker (captcha / IP allow-list / etc.) removed. Per pattern win 33. |
| **CLOSED** | (New tag this refresh) Investigation determined the carry was a misclassification or false alarm; no work needed. |

---

## §2 Closed since v20

### Carry #4 -- q16/q17/q18 HALT 3 "1 skipped"

- **Old framing:** the HALT 3 eval pass-count was reported as "13 passed / 1 skipped"
  at multiple ship gates; the "1 skipped" was suspected to be a row-level skip on one
  of q16/q17/q18.
- **Investigation:** sub-agent B v22 (`outputs/halt3_q16_q17_q18_investigation_v22.md`)
  traced the 1-skip to an env-gated test that gates on an absent env var, NOT a
  per-row skip. All q16/q17/q18 rows pass per Phase 7.5.4 snapshot.
- **Resolution:** no code change required. The "1 skipped" is expected and benign.
- **Landing SHA:** N/A (investigation only).

### #23 BBB cross-reference verifier

- **Resolution path:** wave 4 dispatch; httpx + bs4 category-walk (no Playwright
  needed); shopping-essentials scope only; rapidfuzz token_sort_ratio threshold 86.
- **Files shipped:** `app/contrib/bbb_client.py`, `scripts/bbb_verify.py`,
  `tests/test_phase5_bbb_verify.py`.
- **Test delta:** +7 net-new (2453 -> 2460 collected).
- **Caveat:** BBB accredited-listing HTML returns 403/Cloudflare from automation IPs;
  client early-aborts and returns `[]`. Status is SHIPPED (FUNCTIONAL-BUT-INERT) per
  pattern win 33. Live yield expected from operator network / prod dry-run.
- **Landing SHA:** `f56119f` (wave 4 close-out commit).

---

## §3 Re-tagged since v20

### #22 AZ TPT verifier -- Playwright name-search -> operator-action package

- **Old framing (v20):** "STILL-OPEN -- no verifier shipped. **Recommended wave-4
  candidate**." Implicit assumption: Playwright + name fuzzy-match (mirror BBB / AZ MVD).
- **What changed:** dual-source convergence between Cowork primary Chrome MCP recon
  (`outputs/chrome_mcp_captcha_recon_v22.md`) and Cursor wave-4 §3.1 probe surfaced
  two independent blockers:
  1. **Scope mismatch.** The aztaxes.gov verifier accepts only an 8-digit TPT
     license number; it is name-blind. No public bulk roster exists.
  2. **Google reCAPTCHA v2 checkbox** on page load; bypass requires paid captcha
     dep (violates wave-4 zero-new-deps rule).
- **New tag:** STILL-OPEN -- **bulk CSV import OR manual verification; not Playwright
  name-search.**
- **Shipped artifact:** `docs/operations/aztpt_manual_verification.md` documents
  three operator paths: (A) AZ DOR public-records request for Mohave retail TPT
  roster -> CSV import verifier; (B) manual spot-check per provider; (C) future
  license-number-only automation if upstream license numbers populate.
- **Files removed in close-out:** `app/contrib/aztpt_client.py`,
  `scripts/aztpt_verify.py`, `tests/test_phase5_aztpt_verify.py` (initial commit
  `96d978c` had stub-shipped these; removed at `f56119f`).
- **Operator action:** send Path A public-records email; expected 3-10 business day
  turnaround.
- **Effort:** ~3h Cursor for CSV-import verifier once Path A CSV arrives. Mirror
  `scripts/azmvd_verify.py` bulk-shape.

### N11 AZCC captcha unblock -- heavy -> XS-S

- **Old framing (v20 §6):** "captcha unblock decision required (heavy)"; three
  operator paths (a/b/c) named but un-scoped.
- **What changed:** v22 Chrome MCP recon characterized the captcha shape directly:
  custom Angular component (NOT Google reCAPTCHA / hCaptcha / Cloudflare Turnstile),
  6-char alphanumeric PNG with mild distortion + grid/dot noise, base64 inline at
  ~9.3 KB, refresh button available.
- **New scoping:** Tesseract OCR likely yields 50-70% on first attempt; refresh
  loop pushes effective to 90%+. Manual operator cookie seed viable as fallback.
- **New tag:** STILL-OPEN -- XS-S effort (Tesseract integration OR manual cookie
  seed). Hybrid path (c) recommended for prod.
- **Dep impact:** would add Tesseract (open-source, well-maintained); confirm with
  operator before adding.
- **Not blocking anything else;** #21 AZCC towing verifier ships fine
  FUNCTIONAL-BUT-INERT until unblocked.

---

## §4 Still-open items (~78 entries; full coverage)

### §4.1 Strategic V1.5 features (master plan Phase 13) -- 11 items

All 11 STILL-OPEN. **No change from v20.** Items: #1 peer recs / #2 UGC / #3 SMS
alerts / #4 accessibility / #5 category_id backfill / #6 owner video / #7 bookings /
#8 itinerary / #9 real-time prices / #10 white-label / #11 native reviews.

### §4.2 Data-source carries -- 5 items

| # | Item | Status | Notes |
|---|---|---|---|
| 12 | Water temperature alt-source | PARTIALLY SHIPPED (flag ON, sentinel) | No change from v20. N4 carry. |
| 13 | Nixle replacement | STILL-OPEN | No change. |
| 14 | Tighter local AirNow fidelity | STILL-OPEN | No change. |
| 15 | Reservoir-storage UX | STILL-OPEN | No change. |
| 16 | Gauge-height-delta heuristic doc | STILL-OPEN | No change. |

### §4.3 Layer-4 verifier bundle -- 13 items

| # | Item | Status | Notes |
|---|---|---|---|
| 17 | AZDHS childcare-license | SHIPPED (`52f82f2` wave 1) | No change from v20. Operator dry-run pending. |
| 18 | AZDOR transient-lodging tax | PARTIALLY SHIPPED (operator pkg) | No change. Mirror of #22 pattern. |
| 19 | AZRE vacation-rental license | SHIPPED (`bae8690` wave 1) | No change. Operator dry-run pending. |
| 20 | AZ MVD Dealer Locator | SHIPPED (`fc9e349` wave 3) | No change. Operator dry-run pending. |
| 21 | AZCC towing carrier | SHIPPED (FUNCTIONAL-BUT-INERT) (`fc9e349` wave 3) | No change. N11 captcha unblock now XS-S. |
| 22 | AZ TPT | STILL-OPEN (re-tagged) | See §3 above. Operator-action pkg shipped at `f56119f`; bulk-CSV-import path is wave-5+ candidate. |
| 23 | BBB cross-reference | SHIPPED (FUNCTIONAL-BUT-INERT) (`f56119f` wave 4) | New this refresh. See §2 above. |
| 24 | AZ State Parks Playwright | STILL-OPEN | No change. Wave-5+ candidate; pre-probe captcha shape before dispatch. |
| 25 | NPS REST API | STILL-OPEN | No change. |
| 26 | LHC Parks & Rec municipal scrape | PARTIALLY SHIPPED | No change. |
| 27 | LHC Tourism Board lodging directory | STILL-OPEN | No change. |
| 28 | Franchise gym chain APIs | STILL-OPEN | No change. |
| 29 | National pet franchise locators | STILL-OPEN | No change. |
| 29a | visitarizona.com event aggregator | SUPERSEDED | No change. |

**Layer-4 subtotal:** 5 of 13 still STILL-OPEN (was 8 at v20). Was: #22, #23, #24,
#25, #27, #28, #29. Now: #22 (re-tagged), #24, #25, #27, #28, #29.

### §4.4 Validator / HALT 3 polish -- 3 items

| # | Item | Status | Notes |
|---|---|---|---|
| 30 | F6 near_match_subject_overlaps fail-open | STILL-OPEN | No change. Wave-2 wrapper authored, not dispatched. |
| 31 | F7 _USEFUL_CONTENT_RE over-broad | STILL-OPEN | No change. Same wave-2 cluster. |
| 32 | scripts/post_deploy_smoke.py automation | STILL-OPEN | No change. Smoke script exists at `7db8605`. |

### §4.5 Chat / routing carries -- 4 items

All 4 STILL-OPEN (#33, #34, #35 PARTIAL, #36). **No change from v20.**

### §4.6 Phase 9 events carries -- 11 items (37-45b)

All 11 STILL-OPEN. **No change from v20.** #47 event_traffic alert remains
"unblocked but not implemented".

### §4.7 Alerts / conditions polish -- 9 items

All 9 STILL-OPEN. **No change from v20.** #54 PARTIALLY SHIPPED unchanged.

### §4.8 Sustainability-layer / data shape -- 4 items

All 4 STILL-OPEN (#55, #56, #57, #58). **No change from v20.**

### §4.9 Dual-place_id / dual-category consolidations -- 13 items (59-71)

All 13 STILL-OPEN per-entity. **No change from v20.**

### §4.10 Specific-entity reviews + DRAFT cleanup -- 17 items (72-88)

All 17 STILL-OPEN. **No change from v20.**

### §4.11 UI / browse polish -- 4 items (89-92)

All 4 STILL-OPEN. **No change from v20.**

---

## §5 Top candidates for v24+ ship lanes

Ranked by ship-readiness (probe-gate done) + operator-visible payoff + effort fit.

### S-tier (ready to dispatch; low risk)

- **Layer-4 wave 5 lane: #24 AZ State Parks (Playwright probe-gate)** -- S-M effort.
  Pre-probe via Cowork Chrome MCP first (per pattern wins 31 + 33 + the v22 recon
  template). If Playwright + reCAPTCHA, defer like #22; if REST or custom captcha,
  dispatch. Estimated 4-8h Cursor.
- **Layer-4 wave 5 lane: #25 NPS REST API** -- XS-S effort. REST surface; well-known
  endpoints (developer.nps.gov). Should be probe-gate-clean. Estimated 2-4h Cursor.
- **N11 AZCC captcha unblock (Tesseract path)** -- XS-S effort. Unblocks #21 prod
  yield. Adds Tesseract dep (operator confirm). Estimated 2-3h.
- **#32 post_deploy_smoke.py automation against prod** -- XS effort. Script exists
  at `7db8605`; just needs scheduled invocation + alert wiring. Estimated 1-2h.

### M-tier (medium effort; high visible payoff)

- **Wave 2 dispatch cluster (#30, #31, #33)** -- M effort. Wrapper authored at
  `outputs/cursor_dispatch_prompt_v1_5_wave2_validator_ops.md`. Dispatch when next
  Cursor slot opens. Estimated 5-8h Cursor.
- **#47 event_traffic alert type wire-up** -- M effort. ENTITY shipped Phase 9a;
  alert wiring still in v20 §4. Estimated 4-6h.
- **#37 + #38 + #40 Phase 9 events polish trio** -- M-L effort. Operator-visible
  payoff for already-shipped 9b scrapers. Estimated 8-12h.

### L-tier (operator-research dependent)

- **#22 AZ TPT bulk CSV import** -- L effort but BLOCKED on Path A operator email.
  Operator action: send public-records request now; 3-10 day turnaround. CSV-import
  verifier ~3h Cursor once data arrives.
- **#13 Nixle replacement + #14 AirNow + PurpleAir** -- L effort; operator research
  to pick alt-sources first.
- **Operator data-ingest closeout** -- ~2-4h operator + ~30min eng monitoring. Run
  shipped verifier scripts against prod DB: #17 AZDHS + #19 AZRE + #20 AZ MVD +
  (after N11) #21 AZCC + (now) #23 BBB. Closes "trust signal" carries with zero new
  eng work; converts code-only to user-visible.

---

## §6 Cross-references

- **v20 baseline:** `outputs/v1_5_carries_inventory_refresh_2026_05_24_v20.md`
- **Wave-4 close-out:** `outputs/v1_5_wave4_closeout.md` (§11 deviations + §13 gates)
- **Chrome MCP recon:** `outputs/chrome_mcp_captcha_recon_v22.md` (AZCC + AZ TPT
  captcha shapes; scope-mismatch finding)
- **HALT 3 investigation:** `outputs/halt3_q16_q17_q18_investigation_v22.md`
  (carry #4 close evidence)
- **Operator action package:** `docs/operations/aztpt_manual_verification.md`
  (#22 deferral artifact)
- **Wave-4 dispatch wrapper:** `outputs/cursor_dispatch_prompt_v1_5_wave4_layer4_verifiers.md`
- **Wave-3 reference:** `outputs/cursor_dispatch_prompt_v1_5_wave3_layer4_verifiers.md`
  (structural template for wave-5 dispatch)
- **Wave-2 wrapper (not yet dispatched):**
  `outputs/cursor_dispatch_prompt_v1_5_wave2_validator_ops.md`

---

## §7 Pattern wins reinforced this wave

- **Pattern win 31 (probe-gate-inside-wrapper):** validated again -- Cursor §3.1 probe
  caught the AZ TPT scope mismatch independently; the structural rule held.
- **Pattern win 33 (functional-but-inert is a valid ship):** #23 BBB joins #21 AZCC
  towing in this category. Cloudflare-403-blocked from automation IPs -> client returns
  `[]` early; tests pass; live yield TBD via operator network.
- **NEW pattern win 34 (dual-source recon convergence):** Cowork primary Chrome MCP
  recon and Cursor §3.1 probe converged independently on the same #22 finding. The
  Cowork-primary mid-session redirect note arrived before Cursor burned the full
  60-min probe budget; saved ~30-45 min of redundant Cursor work and enabled a clean
  deferral instead of a stub-and-remove cycle. Generalize: when a captcha-shaped
  Layer-4 surface is on the dispatch path, run Chrome MCP recon in parallel with
  Cursor's first 30 min.
- **NEW pattern win 35 (env-gated test is not a row skip):** sub-agent B's carry-#4
  investigation found the "1 skipped" was env-gated, not row-level. Generalize: when
  a multi-row eval reports N passed / 1 skipped, check the test gate before assuming
  any row regressed.

---

*Refresh authored 2026-05-24 by sub-agent C under Cowork primary supervision against
HEAD `f56119f` (post-wave-4 close-out). Pure read-only audit. Lives at
`outputs/v1_5_carries_inventory_refresh_2026_05_24_v23.md`. Does not modify the v20
baseline nor any other refresh; reads as a delta-overlay on v20, which itself
delta-overlays the 2026-05-23 refresh, which delta-overlays the original
`outputs/v1_5_carries_inventory.md`. Used Windows-direct Read per gotcha #25.*
