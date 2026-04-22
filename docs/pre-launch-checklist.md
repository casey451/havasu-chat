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

## Completed

(items move here when resolved, with resolution note)
