# Pre-launch checklist

Items that must be addressed before Havasu Chat is released to
broader public. Updated across Phase 8 sub-phases as launch
blockers surface. Owner works through this list before flipping
from soft-launch to public launch.

## Companion docs

- **Operational runbook** — `docs/runbook.md` (production operations, admin UI, copy-paste SQL, emergency triage, env vars). The checklist below is **gate** work before wider public release; the runbook is the **day-in/day-out** reference (Phase 8.4).

## Open

- [ ] **Configure Sentry alert rules.** Before public launch, set
      up alerts in the Sentry UI for: error rate spikes on
      exception events, regression detection on resolved issues, and
      a recurring review of **Tier 3** graceful fallback rate
      (manual SQL for now; see `docs/runbook.md` **§4** “Useful
      queries — copy-paste SQL”). This is Sentry dashboard work,
      not application code. (Added Phase 8.4)

- [ ] **Replace privacy page contact email.** `docs/privacy.md`
      currently lists `caseylsolomon@gmail.com` as the contact
      address. Swap for a dedicated Havasu Chat inbox once set
      up. Remove the HTML TODO comment at the same time.
      (Added Phase 8.7)

- [ ] **Revisit retention policy.** Privacy page commits to a
      post-launch review. Target: 6 months after public launch,
      or sooner if user concerns surface. Decide on TTL for
      `chat_logs` and related tables.
      (Added Phase 8.7)

- [ ] **Lawyer review of Terms of Service.** Before public
      launch, have a lawyer review `docs/tos.md` for
      enforceability, liability limits, IP clauses, and
      jurisdiction-specific language. Draft uses placeholder
      for governing law; lawyer fills. (Added Phase 8.5)

- [ ] **Lawyer review of privacy page.** Even though the 8.7
      draft was solid, have a lawyer review `docs/privacy.md`
      alongside the ToS. Pair review is standard practice for
      public launch. (Added Phase 8.5)

- [ ] **Replace governing-law placeholder in ToS §9.** After
      lawyer review, fill in the jurisdiction and venue for
      `docs/tos.md` section 9, and remove the HTML TODO
      comment. (Added Phase 8.5)

- [ ] **Consistency check: ToS and privacy alignment.** After
      any lawyer changes, confirm `docs/tos.md` and
      `docs/privacy.md` agree on contact email, data
      descriptions, and subprocessor list. Mismatches between
      the two pages are a common launch-day issue. (Added Phase
      8.5)

- [ ] **Phase 8.9 event ranking complete** (recurring vs. one-time classification, retrieval preference, evergreen fallback)

- [ ] **River Scene event pull operational,** events ingested, operator-reviewed

- [ ] **`havasu-enrichment` Day 1 setup complete** (Google Cloud project, Anthropic key, enrichment repo, venv, Drive folder, budget alerts configured)

- [ ] **Batch 1 executed** (25-provider validation set), quality report reviewed

- [ ] **Batches 2–N executed** (remaining ~4,549 providers)

- [ ] **Operator review queue drained** to acceptable threshold (threshold defined during 8.11.3 scoping)

- [ ] **All ~4,574 providers ingested** into chat app Postgres catalog

- [ ] **Voice regression v2 passes** against expanded catalog with revised acceptance criteria

- [ ] **Tier 3 retrieval verified** against new narrative surface area

## Completed

(items move here when resolved, with resolution note)
