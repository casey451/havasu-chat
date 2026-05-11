# Pre-Pivot Doc Banner Audit

**Status:** audit-only; no banners added.
**Source pivot:** `docs/STRATEGY_PIVOT_2026-05-12.md` (LOCKED 2026-05-13 §8.1–§8.4)
**Author:** Cowork sub-agent (read-only audit, 2026-05-13 evening)
**Audience:** Cowork primary + Casey, for a prioritized banner-application pass.

This memo classifies every `docs/**.md` file (excluding the two top-level architectural docs that already received banners in `a6e9f6c`) against the 2026-05-12 strategic pivot. Classification is sample-based: title + first ~20 lines + headings unless deeper read was needed to disambiguate. Per pivot §8.7 LOCKED, substantive rewrites are deferred past Day 90 — this audit is the prep for a banners-only pass.

---

## §1 Summary

**Total docs audited:** ~85 markdown files under `docs/` (excluding `docs/PROJECT.md` and `HAVA_CONCIERGE_HANDOFF.md`, which already carry the `a6e9f6c` banner; counting `docs/components/*.md` as a single aggregate because they are uniformly technical reference).

Component-doc tree treated as a single aggregate bucket (B): the ~70 files under `docs/components/` are uniformly per-module technical specs (purpose, public surface, internal structure) with no product-strategy content. Spot-checked: `unified_router.md`, `models.md`, `river_scene.md`, `tier2_handler.md`. None describe monetization, sponsor packaging, or user-facing product framing. Treating them collectively rather than enumerating each.

- **A — Needs banner:** **13 docs**
- **B — Doesn't need banner:** **~50 docs** (including the components tree treated as one bucket)
- **C — Already pivot-aware:** **13 docs**
- **D — Unclear / operator review:** **3 docs**

---

## §2 Docs that need a banner (priority-ordered)

Ordered by leverage — docs most likely to be opened by a new agent or operator session come first.

### `docs/START_HERE.md`
**Why it needs a banner:** This is the literal entry point for new Claude sessions, named in `docs/STATE.md` line 1 as a first-read. Frames Hava as a "conversational concierge for Lake Havasu City" with chat-first tagline "The AI local of Lake Havasu." Lists `havasu-knowledge-base.md` as authoritative without flagging it as pre-pivot. Reader could finish this file with zero awareness of the pivot.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> havasu-chat has pivoted from chat-first concierge to structured local directory with chat as one of three front doors (browse + search + ask). The orientation flow, doc pointers, and voice constraints below remain accurate, but the product framing ("conversational concierge", "AI local") and the assumption that chat is the only front door are PRE-PIVOT. For current strategic direction, read `docs/STRATEGY_PIVOT_2026-05-12.md` first; for which open work is now top-of-queue, see pivot §6 rather than the doc pointers below.
>
> Substantive rewrite deferred past Day 90 per pivot §8.7 LOCKED status block.

### `docs/CLAUDE_SESSION_BRIEFING.md`
**Why it needs a banner:** Sibling entry point to `START_HERE.md`, also named in `docs/STATE.md`. Opens with "Conversational AI concierge for Lake Havasu City." Lists `HAVA_CONCIERGE_HANDOFF.md` and `docs/persona-brief.md` as authoritative without pivot context. Fresh Claude sessions land here.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> The product is pivoting from chat-first concierge to structured local directory with browse + search + chat as three equal front doors. Roles, gates, voice constraints, and process discipline in this briefing remain accurate. The "conversational AI concierge" framing and chat-only-front-door assumption are PRE-PIVOT. Read `docs/STRATEGY_PIVOT_2026-05-12.md` end-to-end before drafting work; backlog priorities are now overridden by pivot §6. Substantive rewrite deferred past Day 90 per pivot §8.7.

### `docs/CURSOR_ORIENTATION.md`
**Why it needs a banner:** Entry point for new Cursor sessions. Stack description and commit discipline survive the pivot, but the framing ("Hava repo") inherits the chat-first identity from sibling docs. Cursor sessions executing post-pivot work (directory schema, category pages, account-lite) need to know that the existing architectural context is partial.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> Process rules, commit discipline, and repo coordinates below remain accurate under the pivot. The product framing inherited from `docs/START_HERE.md` and `HAVA_CONCIERGE_HANDOFF.md` is PRE-PIVOT — havasu-chat is now a structured local directory with chat as one of three front doors. If the phase prompt references category pages, structured Provider profile pages, account-lite, or sponsor packaging, read `docs/STRATEGY_PIVOT_2026-05-12.md` first. Substantive rewrite deferred past Day 90 per pivot §8.7.

### `docs/CURSOR_NEW_CHAT_PLAN.md`
**Why it needs a banner:** Mode A/B playbook for Cursor sessions; references the full doc stack (STATE, BACKLOG, HANDOFF, persona). Doesn't itself contain pivot-incompatible product strategy, but the doc-stack pointers all predate the pivot, and a Cursor session bootstrapping through this playbook will land in pre-pivot framing without knowing it.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> The Mode A / Mode B doc-stack read order below is unchanged in shape, but several docs it points at (`START_HERE.md`, `CLAUDE_SESSION_BRIEFING.md`, `persona-brief.md`, `HAVA_CONCIERGE_HANDOFF.md`, `docs/PROJECT.md`) describe a pre-pivot chat-first product. The current strategic direction is a structured local directory with chat as one of three front doors — read `docs/STRATEGY_PIVOT_2026-05-12.md` before any non-trivial work. Pivot §6 supersedes backlog priorities.

### `docs/persona-brief.md`
**Why it needs a banner:** Locked-and-authoritative voice spec. Frames Hava as "the AI local of Lake Havasu" with chat-first delivery patterns (AI-acknowledgment in-chat, follow-up questions, small talk). Voice rules survive the pivot, but the doc's positioning (tagline, "in-chat" delivery surface) is chat-first. Likely to be quoted in phase prompts.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> Hava's voice, persona, blocklist, and delivery patterns below remain canonical and are not changing with the pivot. The product framing surrounding the voice spec (tagline "the AI local of Lake Havasu", chat as the only delivery surface) is PRE-PIVOT — Hava will continue to speak in this voice on the chat front door, but the directory and browse front doors will surface mostly structured/factual content with the persona reduced to landscape-level framing. For current product direction, read `docs/STRATEGY_PIVOT_2026-05-12.md`. Substantive rewrite deferred past Day 90 per pivot §8.7.

### `docs/havasu-development-plan.md`
**Why it needs a banner:** Explicit pre-pivot strategic plan. "Today's scope is dated events. The longer-term vision is a trusted 'friend in town who knows everything'." Lays out a phased plan that does not contemplate browse/search/category-pages/account-lite/map. Last updated 2026-05-03. Carries an "Active working document" label.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> This development plan is PRE-PIVOT and describes the chat-first / dated-events scope that has been superseded. The current product direction is a structured local directory with chat as one of three front doors (browse + search + ask). The "Forward Plan" phases below are no longer authoritative for prioritization — see `docs/STRATEGY_PIVOT_2026-05-12.md` §6 (three-bucket re-prioritization) and §5 (90-day shape) instead. Working principles in §3 remain useful. Substantive rewrite deferred past Day 90 per pivot §8.7.

### `docs/havasu-knowledge-base.md`
**Why it needs a banner:** Explicitly states "Havasu Chat is an events app, not a directory" — a direct contradiction of the pivot. Already carries a "Historical document" banner about H1 code removal, but does not flag the strategic pivot. Defines core decision framework (Events / NO_MATCH / Venue redirect) that is incompatible with directory framing. Reader needs both flags.

**Suggested banner (in addition to the existing historical-document banner):**
> **2026-05-12 Strategic Pivot Notice (in addition to the H1 historical banner below)**
>
> The product-decision framework in §1 ("Havasu Chat is an events app, not a directory") is DIRECTLY CONTRADICTED by the 2026-05-12 strategic pivot — the product is now a structured local directory with chat as one of three front doors. Specific phrasing recommendations (response categories A/B/C, venue redirects, geographic scope) are PRE-PIVOT and should not drive new decisions. For current direction, read `docs/STRATEGY_PIVOT_2026-05-12.md`. Substantive rewrite deferred past Day 90 per pivot §8.7.

### `docs/sponsor_outreach/cold_email_templates.md`
**Why it needs a banner:** Sells the pre-pivot tier structure ($59 Standard / $179 Featured / $399 Premier) drawn from `ask-hava-detailed-plan.docx`. The pivot replaces this with Verified Presence ($79) / Category Visibility ($349) / Seasonal Takeover ($1,500–$5,000). Operator could send the wrong-tier pitch by accident.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> The tier structure quoted below (Free / Standard $59 / Featured $179 / Premier $399) is the PRE-PIVOT sponsor packaging from `ask-hava-detailed-plan.docx`. Post-pivot packaging is Verified Presence ($79/mo) / Category Visibility ($349/mo) / Seasonal Takeover ($1,500–$5,000) — see `docs/STRATEGY_PIVOT_2026-05-12.md` §7 and `docs/sponsor_outreach/verified_presence_pitch.md` for the current pitch artifacts. Tone guidance and the "no marketing-speak" framing below remain useful. Do NOT cold-email the $59 Standard / $179 Featured / $399 Premier tiers as of 2026-05-13.

### `docs/sponsor_outreach/cold_email_variants_2026-05-09.md`
**Why it needs a banner:** Category-specific variants all pitch "$59/mo Spotlight slot" with the 30-day money-back guarantee. Pre-pivot pricing and packaging. Plumber / HVAC / pool / etc. variants will still be useful copy-source for the post-pivot Verified Presence pitch in Home Services category, but the headline package is wrong.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> These variants pitch the PRE-PIVOT $59/mo Spotlight slot. Post-pivot, the Home Services categories (plumbers, HVAC, pool service) are pitched as Verified Presence at $79/mo — see `docs/sponsor_outreach/verified_presence_pitch.md` for the current cold-pitch script. The category-specific framing and seasonal hooks below are still useful copy-source for adapting the Verified Presence pitch per category. Do NOT send these variants as-written.

### `docs/sponsor_outreach/reply_handlers.md`
**Why it needs a banner:** YES / NO / questions / follow-up email templates all reference "Spotlight placement" and the $59/mo / 30-day money-back deal. The conversational logic survives, but every concrete deal reference is wrong post-pivot.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> The reply templates below assume the PRE-PIVOT Spotlight ($59/mo) deal. Post-pivot pitch is Verified Presence at $79/mo — see `docs/sponsor_outreach/verified_presence_pitch.md` and the new `verified_presence_followup_emails.md` companion. The structural templates here (YES handler / questions handler / follow-up cadence) translate to Verified Presence with a price and package-name swap, but every "Spotlight" reference and "$59/mo" reference must be updated before use.

### `docs/sponsor_outreach/post_launch_comms.md`
**Why it needs a banner:** Launch email / day-25 check-in / month-1 retention emails all reference "Spotlight placement" and home-page Spotlight section. Post-pivot the unit is a directory listing inside a category page, not a chat-result "Spotlight."

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> Post-launch sponsor touch emails below reference the PRE-PIVOT "Spotlight" placement format. Post-pivot the deliverable is a Verified Presence directory listing inside the Home Services (or eventually Eat & Drink) category page, with optional chat-handoff attribution. See `docs/STRATEGY_PIVOT_2026-05-12.md` §4 (Phase 1 build sequence) and `docs/sponsor_outreach/verified_presence_pitch.md`. Email cadence and structural framing translate; "Spotlight" / "home page Spotlight section" references do not.

### `docs/sponsor_outreach/sponsor_quick_reference.md`
**Why it needs a banner:** The "what you have" card given to sponsors. Promises "Home page Spotlight placement" + "Placement in chat results" at "$59/month". This is the post-sale artifact a paying sponsor reads — wrong-tier delivery here is a customer-experience problem, not just an internal-doc problem.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> This quick-reference card describes the PRE-PIVOT $59/mo Spotlight deliverable. Post-pivot, Verified Presence ($79/mo) provides a verified category-page listing + chat-handoff visibility; full deliverable spec in `docs/STRATEGY_PIVOT_2026-05-12.md` §7 and the Verified Presence pitch in `docs/sponsor_outreach/verified_presence_pitch.md`. Do NOT hand this card to a Verified Presence sponsor as-written.

### `docs/sponsor_outreach/enrichment_sprint_runbook.md`
**Why it needs a banner:** Operator workflow for the "50 verified businesses" enrichment sprint with Spotlight as the activation target. Pivot doc §6 explicitly says to **pause the sprint as-scoped** and redirect operator effort to feeding the directory shape (richer structured fields, new taxonomy mapping). The runbook as-written points the operator at pre-pivot work.

**Suggested banner:**
> **2026-05-12 Strategic Pivot Notice**
>
> Per `docs/STRATEGY_PIVOT_2026-05-12.md` §6, the 50-business enrichment sprint described below is PAUSED AS-SCOPED. Operator effort is being redirected to feed the new directory shape (richer structured fields, new 12-category taxonomy locked 2026-05-13 §8.1, Home Services as V1). The research-and-touch workflow below remains useful; the Spotlight-activation step and tier references are PRE-PIVOT and should be replaced with the Verified Presence pitch artifacts in `docs/sponsor_outreach/verified_presence_*.md`. Do NOT continue activating businesses at the $59/mo Spotlight tier.

---

## §3 Docs that don't need a banner

Bulleted; one-line rationale each.

- `docs/POST_SHIP_CHECKLIST.md` — closing-discipline runbook, pivot-agnostic process doc.
- `docs/WORKING_AGREEMENT.md` — roles, gates, commit discipline; pivot-agnostic.
- `docs/runbook.md` — operational guide (deploys, emergency triage, SQL); references chat surface but is operational not strategic.
- `docs/pre-launch-checklist.md` — operational launch-gate items (Sentry, lawyer review, retention TTL); pivot-agnostic checklist shape.
- `docs/privacy.md` — user-facing legal page; current language ("chat messages", "session ID") survives pivot since chat remains a front door. Future rewrite when account-lite ships.
- `docs/tos.md` — user-facing legal page; "chat experience, access to a catalog of activities, events, and programs, ways to explore what is happening (including browsing and calendar-style views)" already mentions browse, so the pivot does not contradict it. Future rewrite when account-lite ships.
- `docs/query-test-battery.md` — 120-query regression contract; tier-routing validation tool, pivot-agnostic (chat front door still validated).
- `docs/known-issues.md` — bug tracker with H1-deletion historical banner already; no product strategy.
- `docs/search-pipeline-for-claude.md` — already carries an explicit "Historical document" banner; chat-pipeline snapshot, no product strategy.
- `docs/confabulation-eval-runbook.md` — harness operations; pivot-agnostic.
- `docs/components/*.md` (~70 files) — per-module technical reference; uniformly no product strategy. Spot-checked `unified_router.md`, `models.md`, `river_scene.md`, `tier2_handler.md`.
- `docs/maintainability/dispatch_protocol.md` — 12-rule working-agreement reference; pivot-agnostic.
- `docs/maintainability/dispatch_channels.md` — channel-pick playbook; pivot-agnostic.
- `docs/maintainability/project_index.md` — repo map; describes code shape, not product strategy.
- `docs/maintainability/project_manager_organization_brief.md` — PM organization phases; references Hava framing but content is "how we stay organized" not product strategy.
- `docs/maintainability/h1_router_decision.md` — H1 deletion decision; technical retrospective.
- `docs/maintainability/h2_consolidation_decision.md` — H2 LLM-call consolidation; technical retrospective.
- `docs/maintainability/non_river_scene_cleanup.md` — RS-only cleanup retrospective; technical retrospective.
- `docs/maintainability/chat_behavior_followup_plan.md` — deferred chat-tier issues; chat-surface concern, technical.
- `docs/maintainability/findings_app_chat.md` — pre-H2 maintainability findings; technical retrospective.
- `docs/maintainability/end_to_end_creation.md` — catalog-write paths reference; technical.
- `docs/maintainability/http_api.md` — HTTP surface reference; technical.
- `docs/maintainability/railway_layout.md` — Railway deployment reference; operational.
- `docs/maintainability/ci_query_battery.md` — battery how-to-run; operational.
- `docs/maintainability/provider_ingestion_lane_options.md` — speculative ingestion-lane option space; technical (also explicitly pivot-friendly territory since directory ingestion is now needed).
- `docs/maintainability/engineering_gates_options.md` — CI options space; technical.
- `docs/maintainability/intent_module_disposition_decision.md` — `intent.py` module decision; technical.
- `docs/maintainability/schema_time_harmonization_decision.md` — Time-type schema decision; technical.
- `docs/maintainability/static_html_extraction_decision.md` — UI extraction decision; technical.
- `docs/maintainability/river_scene_backfill_documentation_index.md` — index for RS backfill stream; navigational.
- `docs/maintainability/river_scene_backfill_prod_dryrun_runbook.md` — dry-run runbook; operational.
- `docs/maintainability/river_scene_dryrun_quick_reference.md` — dry-run cheat sheet; operational.
- `docs/maintainability/river_scene_event_output_decision.md` — RS event-output decision retrospective; technical.
- `docs/maintainability/river_scene_sentinel_id_retention.md` — sentinel-id note; operational.
- `docs/maintainability/halt3_definition.md` — HALT 3 framework; per pivot §6 chat-eval gating remains relevant but deprioritized — the framework itself is technical and survives. Banner is optional; pivot §6 already lowers its priority.
- `docs/maintainability/halt3_closeout.md` — HALT 3 close-out artifact template; technical/operational; pivot defers but doesn't invalidate.
- `docs/maintainability/post_enrichment_smoke_catalog.md` — flag-flip validation catalog; technical/operational; pivot defers (chat-surface monetization deprioritized) but framework stands.
- `docs/maintainability/backlog_46_smoke_check_queries.md` — manual smoke queries for entity-matcher fix; technical.
- `docs/maintainability/llm_mock_pattern.md` — test-mock pattern; technical.
- `docs/maintainability/disclosure_renderer_spec.md` — deterministic disclosure renderer keystone spec; pivot §3 explicitly says this code is REUSED on category cards. Spec stands.
- `docs/maintainability/confidence_tier_integration_spec.md` — CT formatter integration; pivot §3 explicitly says CT classifier is REUSED as merchant data-quality score. Spec stands.
- `docs/maintainability/ui_data_correctness_spec.md` — homepage data-correctness sprint (RESOLVED); retrospective.
- `docs/maintainability/2026-05-10_absorption_forensics.md` — forensic memo; technical retrospective.
- `docs/maintainability/phase1_deploy_runbook.md` — flag-flip operator runbook; operational. (Chat-surface flag-flip work is deprioritized per pivot §6, but runbook itself is operational.)
- `docs/maintainability/phase2_5_rate_limiter_design.md` — rate-limiter design; pivot §6 explicitly marks this **load-bearing under either vision (KEEP) and more urgent**. Design is forward-compatible.
- `docs/maintainability/phase2_first_week_dispatch.md` — has "SHIPPED" status banner; retrospective at this point.
- `docs/sponsor_outreach/verified_presence_pitch.md` — post-pivot artifact (already references pivot doc in §0 operator note).
- `docs/sponsor_outreach/verified_presence_objection_faq.md` — post-pivot (companion to pitch doc).
- `docs/sponsor_outreach/verified_presence_leavebehind.md` — post-pivot.
- `docs/sponsor_outreach/verified_presence_followup_emails.md` — post-pivot.
- `docs/sponsor_outreach/verified_presence_referral_script.md` — post-pivot.
- `docs/sponsor_outreach/lake_havasu_seasonality.md` — operator seasonality reference; pivot-agnostic (categories listed map cleanly onto the post-pivot 12-category taxonomy).
- `docs/SESSION_HANDOFF_2026-05-08.md` through `docs/SESSION_HANDOFF_2026-05-11.md` — historical session handoffs; pre-pivot in framing but historical records, not forward-looking guidance. Treating as B (operator may disagree — see §5).

---

## §4 Docs already pivot-aware

Bulleted; these reference the pivot directly or are post-pivot artifacts.

- `docs/STRATEGY_PIVOT_2026-05-12.md` — the pivot doc itself.
- `docs/SESSION_HANDOFF_2026-05-12.md` — carries a pivot-warning banner at top.
- `docs/SESSION_HANDOFF_2026-05-13.md` — explicitly labeled "first bounded engineering session under the directory-first pivot."
- `docs/STATE.md` — recent commits reference pivot doc, schema lane, and Verified Presence work.
- `docs/BACKLOG.md` — newer ship-log entries reference the directory pivot V1 schema ship and pivot-related work.
- `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md` — explicitly notes "the 2026-05-12 strategic pivot reshaped this lane" in §1.
- `docs/maintainability/category_backfill_mapping_DRAFT.md` — explicitly maps to the 12 canonical Category slugs locked 2026-05-13.
- `docs/maintainability/phase2_lane_decomposition.md` — has a SUPERSEDED status banner at top (not pivot-driven, but the banner already signals the doc is non-authoritative).
- `docs/maintainability/phase2_midweek_coverage_audit.md` — read-only retrospective dated 2026-05-10; post-pivot in time but doesn't reference pivot. Audit-doc by nature; classified C because audit-docs don't drive forward decisions.
- `docs/sponsor_outreach/verified_presence_pitch.md` + 4 companion files (objection_faq / leavebehind / followup_emails / referral_script) — drafted 2026-05-13, post-pivot, references pivot doc in §0 operator note.

---

## §5 Docs needing operator review

Each item has an ambiguity worth a quick Casey/operator call.

### `docs/SESSION_HANDOFF_2026-05-08.md` through `docs/SESSION_HANDOFF_2026-05-11.md`
**Ambiguity:** These five session handoffs are pre-pivot in framing (chat-first, Phase 1 keystone work, sponsor outreach via Spotlight tiers). They are historical records of what shipped, not forward-looking guidance — a new agent reading them is looking back, not picking up the work-as-described. Banners are usually for docs that drive new decisions; these don't. But a fresh Cowork primary reading the 2026-05-09 handoff to understand "what was Lane 1" might not realize the sponsor-outreach surface that landed there is now pre-pivot.

**Operator question:** Banner the five pre-pivot session handoffs as a historical artifact (one line at top: "Pre-pivot session handoff; pivot landed 2026-05-12"), or leave them entirely alone as immutable records?

### `docs/maintainability/halt3_definition.md` + `docs/maintainability/halt3_closeout.md` + `docs/maintainability/post_enrichment_smoke_catalog.md`
**Ambiguity:** Pivot §6 deprioritizes HALT 3 close-out ("can defer 4–8 weeks past current expectation") and the post-enrichment smoke catalog ("resolve when HALT 3 close-out activates"). These docs are not invalidated — the framework still works — but a new agent landing on them might assume they're current top-of-queue work when they're now chat-surface concerns and lower-leverage.

**Operator question:** Add a lightweight banner pointing at pivot §6 deprioritization (one paragraph: "Pivot §6 deprioritizes this lane; HALT 3 close-out can defer 4–8 weeks past current expectation"), or treat as B and rely on the pivot doc to carry the priority signal?

### `docs/maintainability/phase1_deploy_runbook.md`
**Ambiguity:** The runbook is operational (deploy + flag-flip walkthrough), so classified B. But `FEATURE_FLAG_DISCLOSURE_RENDERER` flip remains HOLD'd per STATE.md, and pivot §6 implicitly deprioritizes that flip (chat-surface monetization deprioritized). A new agent looking to flip the flag using this runbook would not learn from the runbook that the flip is no longer the headline priority.

**Operator question:** Banner with a pivot-priority note ("The DISCLOSURE_RENDERER flag-flip described below is deprioritized per pivot §6 — the renderer code is REUSED on category card sponsor slots in the new architecture rather than chat-surface placement"), or leave as B?

---

## §6 Recommended next steps

Priority order for the banner-application pass. Per pivot §8.7 LOCKED, **banners only — no substantive rewrites until past Day 90.**

1. **Onboarding entry points (highest leverage, every new session reads these):**
   - `docs/START_HERE.md`
   - `docs/CLAUDE_SESSION_BRIEFING.md`
   - `docs/CURSOR_ORIENTATION.md`
   - `docs/CURSOR_NEW_CHAT_PLAN.md`

2. **Sponsor outreach pre-pivot pitch surface (operator-action-blocking — banners prevent wrong-tier outreach):**
   - `docs/sponsor_outreach/enrichment_sprint_runbook.md` (pivot explicitly pauses this sprint)
   - `docs/sponsor_outreach/cold_email_templates.md`
   - `docs/sponsor_outreach/cold_email_variants_2026-05-09.md`
   - `docs/sponsor_outreach/sponsor_quick_reference.md`
   - `docs/sponsor_outreach/reply_handlers.md`
   - `docs/sponsor_outreach/post_launch_comms.md`

3. **Strategic / product-positioning docs:**
   - `docs/havasu-development-plan.md`
   - `docs/havasu-knowledge-base.md`
   - `docs/persona-brief.md`

4. **Operator review pass (after banners above land):** decide §5 items.

Estimated effort: ~13 mechanical banner edits, each ~5 lines. One sitting, single commit `docs: pre-pivot banner pass per pivot §8.7`. No code changes, no test changes.

After the banner pass: this audit doc itself can be linked from `docs/STRATEGY_PIVOT_2026-05-12.md` §10 (Reference docs) and from a future "post-pivot doc rewrite plan" once Day 90 approaches.
