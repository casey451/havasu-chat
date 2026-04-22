# Phase 6.4.1 Cursor prompt — draft review (2026-04-21)

## Review

- **Strength:** Clear STOP / `proceed` gate, scope fence, acceptance checklist, completion workflow through prod smoke. Pre-flight checks 2–4 and precedence trace will save a bad implementation pass.
- **Contradiction (fixed in saved prompt file):** “Design decisions” originally said **user-named wins** if both fire; **In scope §5** and **acceptance criteria** say **recommended (post-handler) wins**. Those cannot both be true. The copy in `docs/phase-6-4-1-cursor-prompt.md` aligns **Design → recommended wins (written last)** so the whole doc matches §5 and test **7e**.
- **Pre-flight 1:** `grep` is awkward on Windows; the saved prompt adds a one-line note (`findstr` or manual scan).
- **Test 7e wording:** “User-named entity on query (`what time does Altitude open`)" is a bit odd—usually that query already targets Altitude. The *intent* is “response body mentions a *different* catalog entity so recommended overwrites”; worth keeping the scenario concrete in implementation (e.g. user asks for Altitude, Tier 3 body still spotlights another venue—or whatever the router actually does).
- **708 + N:** Baseline may drift; “current `main` count + new tests” is slightly safer wording for a long-lived doc, optional.
- **Latency / “efficient”:** Pre-flight could note whether matching runs over full catalog aliases per response (fine for MVP if N is modest); only worth a STOP if numbers look bad.

## Saved copy

The full implementation prompt lives in **`docs/phase-6-4-1-cursor-prompt.md`** (with the precedence bullet corrected and the Windows note on pre-flight check 1). Whether that file is committed to `main` is a separate owner decision.

## Timing

Paste from `docs/phase-6-4-1-cursor-prompt.md` into a new Cursor chat whenever you start Phase 6.4.1; no dependency on the chat where this review was written.
