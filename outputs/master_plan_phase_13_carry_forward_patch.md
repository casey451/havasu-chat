# Master Plan §4 Phase 13 — Phase 5 Carry-Forward Patch (V1.5 backlog consolidation)

> **What this is:** the pre-positioned patch closing triage §8 #4 — appends a "Phase 5 carry-forward" sub-section to `docs/maintainability/master_build_plan.md` §4 Phase 13 that cross-references the 39 V1.5-defer items consolidated in `outputs/v1_5_carry_inventory_triage.md`. Single docs edit; low-risk.
>
> **Author:** Cowork primary, 2026-05-20 post-`99eb12c`.
>
> **Operator-decide first:** triage §8 #4 framed two options:
>   - **Option A (this patch):** master plan §4 Phase 13 IS the canonical V1.5 backlog home; append the Phase 5 carry-forward sub-section there. Cross-references stay in one doc.
>   - **Option B (alternative):** a separate `docs/maintainability/v1_5_backlog.md` becomes the canonical V1.5 home; master plan §4 Phase 13 stays focused on the original 11 strategic items.
>
> The patch in §2 below assumes Option A. If you pick Option B, the patch content is still valid — it just goes in a different file. §4 covers the Option B variant.

---

## §1 Why this matters

Current state of `master_build_plan.md` §4 Phase 13:

- 11 strategic V1.5 items (peer recommendations, UGC district layer, SMS alerts, accessibility profiles, Provider.category backfill, owner video, bookings, itinerary builder, real-time prices, white-label, native reviews).
- NO reference to the 39 V1.5-defer carries from Phase 5.0–5.11 close-outs.

Triage doc consolidated those 39 carries into 4 categories (§2 verifier surfaces, §4 dual-place_id / dual-category, §5 specific-entity reviews, §6 cross-phase). Without a cross-reference in the master plan, future operators reading §4 Phase 13 would see only the 11 strategic items and miss the 39 operational carries.

**Closure value:** ledger reads cleanly. When you (or future-you, or a future agent) asks "what's the full V1.5 picture", §4 Phase 13 surfaces both the strategic items AND the carry-forward inventory in one place.

---

## §2 The patch — Option A (append to master plan §4 Phase 13)

### Anchor location

After the existing 11-item bullet list (which ends at line 526 `- Native review system (still deferred unless review-war dynamics in Havasu prove otherwise)`). Before the `---` separator at line 528.

### Content to insert

```markdown

**Phase 5 carry-forward (added 2026-05-20):** Beyond the 11 strategic items above, the Phase 5.0–5.11 multi-phase data-population lane accumulated 39 operational V1.5-defer carries consolidated in `outputs/v1_5_carry_inventory_triage.md`. Categorized:

- **Layer-4 verifier surfaces (~35–60h V1.5 eng; 13 items):** AZ MVD Dealer Locator + AZCC towing (5.5 carry), AZ TPT + BBB (5.6), AZ State Parks + NPS + LHC Parks & Rec shared (5.7+5.9), AZDHS childcare-license + franchise gym chain APIs (5.9), AZDOR transient-lodging + AZRE vacation-rental license + LHC Tourism Board (5.10), national pet franchise locators (5.11). All deferred via "Option C" at Phase 5.x kickoff — V1 ships without verifier surfaces; trust-signal upgrade post-launch. Recommended priority order: AZDHS childcare → AZDOR+AZRE lodging → AZ MVD+AZCC dealers → AZ TPT+BBB retail → AZ State Parks+NPS+LHC Parks&Rec → franchise gyms → pet franchise locators.
- **Dual-place_id / dual-category consolidations (11 items):** HEAT Bar ↔ Heat Hotel + Havasu Dunes ↔ GetAways (5.10), 3 Beautiful Beards + 3 PetSmart franchise multi-place_id consolidations (5.11), 3 cat-8 pet-retail DUAL ADD candidates (5.11), 26 cat-5 HWC dual-cat with cat-12 reviews (5.9), 5 cat-7 outdoor dual-cat soft-edges (5.7), and 4 per-entity recategorizations. All KEEP-as-V1; per-entity V1.5 operator review.
- **Specific-entity reviews (13 items):** Sara Park trail-pair navigation-alias merge (5.7), Lake Havasu Museum of History place_id unification (5.8), 8 single-entity Layer 5 manual recoveries (5.7+5.8+5.9), 5 waterfront-suggestive RV/campground candidates (5.10), 29 lake_recreation-domain ambig records cat-3 NEW creates IF 5.2 lane re-opens (5.10), pet mobile-services / dog-walkers / cat-boarding manual recovery (5.11), Havasu Suites + Xanadu + Queens Bay Resort identity reviews (5.10), off-island heat list venues (5.0).
- **Cross-phase carries (1 item):** 86 of 265 HWC providers remain `verified=False` (5.4 carry-over through 5.11) — operator-driven DBA→NPI follow-up surface.

See `outputs/v1_5_carry_inventory_triage.md` §1–§9 for the full per-carry table (source close-out, recommended disposition, effort estimate, operator-decide flags).

**Phase 5 carry-forward V1.5 effort ballpark:** ~50–80h total eng, dominated by the Layer-4 verifier bundle at ~35–60h. Per-entity reviews are operator hours (not eng); roughly ~10–15h operator across the dual-place_id consolidations + specific-entity reviews.

```

### Exact edit shape

The patch adds 1 paragraph + 4 bullets + 1 paragraph + 1 closing line = roughly 15 lines of net additions to `master_build_plan.md`. Bullet shape mirrors the existing 11-strategic-item list above.

---

## §3 Apply recipe — PowerShell-safe

```powershell
# 1. Open docs/maintainability/master_build_plan.md in your editor
#    Navigate to §4 Phase 13 (around line 512-526)
#    Position cursor at the end of line 526 (the "Native review system" bullet)
#    Insert a blank line, then paste the content block from §2 above

# 2. Save the file. Verify the diff:
git diff docs/maintainability/master_build_plan.md
# Expected: ~15 lines added under §4 Phase 13, ending before the `---` separator

# 3. Stage + commit (PowerShell-safe; no bash heredocs)
git add docs/maintainability/master_build_plan.md
git commit `
  -m "docs(master_plan): §4 Phase 13 -- append Phase 5 carry-forward sub-section (closes triage §8 #4)" `
  -m "Cross-references the 39 V1.5-defer items consolidated in outputs/v1_5_carry_inventory_triage.md as a Phase 5 carry-forward sub-section under §4 Phase 13. Categorized into 4 buckets: Layer-4 verifier surfaces (~35-60h eng; 13 items dominating effort), dual-place_id/dual-category consolidations (11 per-entity operator reviews), specific-entity reviews (13 mixed eng+operator), cross-phase carries (1 -- the 86 HWC verified=False follow-up). Ledger now reads cleanly: §4 Phase 13 surfaces both the 11 strategic items + the 39 operational carries in one place. Per triage §8 #4 recommendation (operator-decide: master plan §4 Phase 13 as canonical V1.5 home -- this is the Option A path)."

# 4. Push
git push origin main
```

**Expected commit shape:** 1 docs commit; 1 file changed; ~15 lines net added. Zero code touches; CI no-op-green.

---

## §4 If you prefer Option B (separate `docs/maintainability/v1_5_backlog.md`)

If you'd rather keep master plan §4 Phase 13 focused on the 11 strategic items + create a dedicated V1.5 backlog doc, the variant patch is:

1. **Create `docs/maintainability/v1_5_backlog.md`** with the content block from §2 above (modify the intro sentence to "This is the consolidated V1.5 backlog..." rather than "Phase 5 carry-forward").
2. **Append a 1-line cross-reference to master plan §4 Phase 13:**
   ```markdown

   See `docs/maintainability/v1_5_backlog.md` for the consolidated V1.5 backlog including the 39 Phase 5.0–5.11 carry-forward items + the 11 strategic items above + future V1.5 additions.
   ```
3. **Commit recipe:**
   ```powershell
   git add docs/maintainability/v1_5_backlog.md docs/maintainability/master_build_plan.md
   git commit `
     -m "docs(maintainability): canonical v1_5_backlog.md + master plan cross-ref (closes triage §8 #4 Option B)" `
     -m "Per triage §8 #4 Option B recommendation -- creates dedicated docs/maintainability/v1_5_backlog.md as the canonical V1.5 backlog home consolidating the 11 strategic items from master plan §4 Phase 13 + the 39 Phase 5 carry-forward items from outputs/v1_5_carry_inventory_triage.md. Single cross-reference added to master plan §4 Phase 13 pointing at the new canonical doc."
   ```

**Recommendation between A vs B:** **Option A** (this patch) for V1; **Option B** if the V1.5 backlog grows substantially post-Phase-7+. Option A keeps everything in one place at modest cost; Option B is the right shape once the V1.5 list crosses ~100 items + needs its own organization. Right now (~50 items total counting the 11 + 39), Option A reads cleanly.

---

## §5 Independence from current Cursor work

`docs/maintainability/master_build_plan.md` is NOT in the file scope of either Phase 6.4 (Lane D) or Phase 7 (Lane E) Cursor session. Both wrappers explicitly schedule master plan updates as POST-SHIP Cowork-primary tasks (see Lane D wrapper §"After Phase 6.4 ships" + Lane E wrapper §"After Phase 7 ships"). So applying this patch during Cursor's grind is gotcha #18 disjoint.

However: when Phase 6.4 ships, Cowork primary will also append a Phase 6.4 "Shipped (incremental)" entry under §4 Phase 6. Same for Phase 7 with a SHIPPED line under §4 Phase 7. **If you apply this Phase 13 patch BEFORE those ships, both edits live cleanly in the file** — the Phase 13 carry-forward is well below the Phase 6 / Phase 7 sections, no anchor collision. **If you apply this patch AFTER one or both ships, same outcome** — still disjoint.

So timing of this patch is operator-discretion: apply now, apply later, or skip in favor of Option B.

---

*Authored by Cowork primary at the post-`99eb12c` dispatch-pre-position session (2026-05-20). Lives at `outputs/master_plan_phase_13_carry_forward_patch.md`. Closes triage §8 #4 when applied (Option A or Option B). Independent of current Cursor work; apply at operator discretion.*
