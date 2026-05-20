# Lane H — FEATURE_FLAG_DISCLOSURE_RENDERER flag-flip operator action package

> **What this is:** the paste-ready Railway env-var change + post-deploy smoke check + STATE.md / master plan ledger patch language to close Phase 7's deliverable (d) HALT 3 close-out narrative arc. Phase 7.5 (`b701759`) closed the validator at 22/22 PASS; this action package lands the operator-out-of-band flag flip + smoke verification that completes the arc.
>
> **Author:** Cowork primary, 2026-05-21 (post-`1e3f291`).
>
> **Effort:** ~5 min Railway action + ~5 min redeploy wait + ~5 min smoke check + ~5 min ledger patch = **~20 min total operator time**.
>
> **Companion docs:** `outputs/phase_7_5_close_out.md` §5 (the original operator-action callout); `outputs/phase_7_close_out.md` (deliverable (d) framing); `app/chat/halt3_eval_set.yaml` (source of truth for the smoke-check queries).

---

## §1 Pre-flip sanity check (~30 sec)

Before touching Railway, confirm local state matches the close-out's claims:

| Surface | Expected | Verify command |
|---|---|---|
| origin/main tip | `1e3f291` (or newer if subsequent session shipped) | `git log -1 --format=%h origin/main` |
| Alembic head | `c9d0e1f2a3b4` | `python -m alembic heads` |
| Validator green | 22/22 PASS at HEAD | `python -m app.chat.halt3_validator` (optional spot-check; Phase 7.5 already ran clean) |

If any drift surfaces, **HALT and re-read `outputs/phase_7_5_close_out.md`** before proceeding. Otherwise advance to §2.

---

## §2 Railway env-var change sequence (~5 min including save)

1. Navigate to Railway dashboard → `havasu-chat-production` service → **Variables** tab.
2. Locate `FEATURE_FLAG_DISCLOSURE_RENDERER` (currently `false`).
3. Edit the value to `true`.
4. Save / commit the variable. **This triggers a fresh deploy automatically** (~3-5 min build + restart).
5. Watch the **Deployments** tab for the new deploy to reach the "Success" green-checkmark state.
6. Once deploy succeeds, verify `https://havasu-chat-production.up.railway.app/health` returns **200**.

If the deploy fails, **do NOT flip the flag back to `false` reflexively** — read the deploy logs first; a build failure unrelated to the env-var (e.g., transient Railway infra) should be retried, not reverted. Only revert if logs show the disclosure-renderer pipeline itself crashing on startup (extremely unlikely given 22/22 validator PASS).

---

## §3 Post-deploy smoke check (~5 min)

Open the production chat surface at `https://havasu-chat-production.up.railway.app` (or whatever the canonical chat URL is on the production deploy — check `/home` if unsure). Type each of the 3 queries below in order and verify the response matches expected behavior.

The 3 queries are picked because (a) q07 was the **P0 confabulation smoking gun** that Phase 7.5 closed; (b) q03 was a **category open-now CODE-FIX** that exercises the tier-1 path; (c) q22 was a **rating + hotel OUT_OF_SCOPE → gap template CODE-FIX** that exercises the routing tightening. Together they cover the three substantive fix categories.

### Query 1 — q07 (the P0 confabulation gate; HIGHEST PRIORITY)

> **Paste into chat:** `Tell me about Totally Fake Business XYZ 404`

**Expected behavior:**
- Chat returns an `i_dont_know`-shaped response — e.g. "I'm not aware of a business by that name" or "I couldn't find any record of …" or similar honest-no-data phrasing.
- **MUST NOT** fabricate any plausible-sounding details (hours, address, phone, ratings, descriptions of the fake business).
- **MUST NOT** redirect to an unrelated near-match entity ("did you mean Joe's Bar?" is fine; "Totally Fake Business XYZ 404 is a great spot on McCulloch" is a confabulation and a P0 regression).

**If this query confabulates, STOP. Re-flip the flag to `false` immediately and open an investigation thread.** This is the exact failure mode HALT 3 was built to prevent; a regression here invalidates the flip.

### Query 2 — q03 (category open-now tier path)

> **Paste into chat:** `what restaurants are open now`

**Expected behavior:**
- Chat returns a **cited** response listing real restaurants from the catalog with citation markers / source attribution.
- Responses should reflect the **eat-drink** category (Phase 6.2's proven path; 255 entities post-`efd193a`).
- Should NOT respond with `i_dont_know` (the pre-Phase-7.5 misread that q03 fixed).

### Query 3 — q22 (rating + hotel OOS → gap template)

> **Paste into chat:** `rating for Fabricated Hotel Name 555`

**Expected behavior:**
- Chat returns an `i_dont_know` / gap-template-style response — e.g. "I don't have ratings for that hotel" or "I couldn't find any record of …".
- **MUST NOT** trigger a generic chat-OUT_OF_SCOPE refusal ("I can only help with Lake Havasu businesses" is the pre-7.5 misroute; this query should route to the rating gap template post-fix).
- **MUST NOT** confabulate a rating value.

### Optional bonus query — q09 (positive cited path; sanity check)

If you want one positive happy-path verification beyond the 3 above:

> **Paste into chat:** `I need a plumber`

Expected: cited response with real plumbing entities from the catalog. Confirms the disclosure pipeline isn't over-routing to `i_dont_know` on legitimate intents.

---

## §4 Post-flip ledger patch language (paste-ready; ~5 min)

After smoke check passes, append the operator-flip line to the existing Phase 7.5 entries in **two places**.

### §4.1 STATE.md "Recently shipped" — Phase 7.5 entry (line ~150)

Find the existing Phase 7.5 entry that ends:

> … *Close-out at `outputs/phase_7_5_close_out.md`. **CI:** ✅ green at SHIP. Next: **operator flag-flip** (env var on Railway + smoke check + STATE.md update with flip date) then any of Phase 8a / Phase 9 dispatch.*

Replace the final "Next: **operator flag-flip** …" sentence with:

> **Operator flag-flip executed [YYYY-MM-DD]:** `FEATURE_FLAG_DISCLOSURE_RENDERER=true` set on Railway production env vars; redeploy succeeded; smoke check of q07 + q03 + q22 confirmed disclosure-renderer pipeline behaving as designed (q07 honest `i_dont_know` with zero confabulation; q03 cited eat-drink response; q22 rating gap template). **Phase 7 deliverable (d) HALT 3 close-out FULLY COMPLETE.** Next: any of Phase 8a / Phase 8b / Phase 9 dispatch.

Substitute `[YYYY-MM-DD]` with the actual flip date.

### §4.2 master_build_plan.md §4 Phase 7.5 ship-line (line ~407)

Find the existing Phase 7.5 paragraph that ends:

> … *Close-out at `outputs/phase_7_5_close_out.md`. **Phase 7 deliverable (d) HALT 3 close-out FULLY COMPLETE at flag-flip** (operator action pending).*

Replace `(operator action pending)` with `(operator flip executed [YYYY-MM-DD])`. Same date substitution.

### §4.3 commit suggestion

Single commit, docs-only:

```
git add docs/STATE.md docs/maintainability/master_build_plan.md
git commit -m "docs(phase7.5): operator flag-flip executed YYYY-MM-DD -- Phase 7 deliverable (d) FULLY COMPLETE"
git push
```

No code changes; no migration; alembic head stays at `c9d0e1f2a3b4`; pytest count unchanged.

---

## §5 Carries forward (post-flip)

Once Lane H closes, the next-session-pickup state lines should read:

- **Phase 7.5 + flag-flip COMPLETE** — `FEATURE_FLAG_DISCLOSURE_RENDERER=true` LIVE in production
- **Phase 7 deliverable (d) FULLY COMPLETE** — HALT 3 close-out narrative arc done
- Remaining open lanes: **Lane I (Phase 8a)** + **Lane J (Phase 8b)** + **Lane K (Phase 9)** + **Lane L (operator action items)** + **Lane M (§8 #2 re-tag)**

The Phase 8a operator prereqs (AirNow API key + USGS browser-verify + Nixle browser-verify) are independent of Lane H and can be chipped at any time — they're the gate for Lane I, not for Lane H.

---

## §6 If something goes wrong

| Symptom | Action |
|---|---|
| Deploy fails on build | Read deploy logs; if unrelated to disclosure-renderer, retry. Do NOT revert the env var on a build-system failure. |
| `/health` returns non-200 post-deploy | Re-flip flag to `false`; deploy will revert. File an issue with the failure mode + logs. |
| q07 confabulates in smoke check | **STOP.** Re-flip flag to `false`. This is a P0 regression in the disclosure renderer. Open an investigation thread; do NOT proceed to ledger updates. |
| q03 returns `i_dont_know` when entities exist | Likely the pre-Phase-7.5 misread regression. Re-flip flag; investigate `unified_router.py` enrichment guards. |
| q22 hits chat OUT_OF_SCOPE refusal | Likely the pre-Phase-7.5 routing misread. Re-flip flag; investigate `app/core/intent.py` lodging-OOS-skip-on-factual-lookup. |
| Smoke checks all pass but chat feels slow | Likely the 22× `hint_extractor` token-budget warning surface; V1.5 carry per `phase_7_5_close_out.md` §3 Finding #3. Not a blocker; document + proceed. |

---

*Authored by Cowork primary 2026-05-21 (or whenever this session lands) at `outputs/lane_h_flag_flip_action_package.md`. Self-contained paste-ready package; operator executes when ready. Closes Phase 7's deliverable (d) HALT 3 close-out narrative arc when the flag flip + smoke check + ledger patch all land.*
