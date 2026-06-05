# Chat routing fix — branch handoff (2026-06-04)

> **RESOLVED — merged & deployed.** Shipped as **PR #145** (web-staged commits),
> merged to main and live on prod the same day; post-deploy battery confirmed
> Tier-1/2 zero-token routing. The `.bundle` file referenced below has been
> deleted (superseded). Your local `fix/chat-routing-zero-token` branch is also
> superseded — safe to delete. The `.git/config` incident below was confirmed
> mount-side only; the Windows-side repo was verified intact. This doc is kept
> for history; the only OPEN item is the prod data audit (see
> `EAT_CATEGORY_POLLUTION_AUDIT_2026-06-04.md`).

Branch `fix/chat-routing-zero-token` (5 commits on top of `origin/main` @ a7b0cb5c,
PR #139) is delivered as **`fix-chat-routing-zero-token.bundle`** in the repo root.
Built and tested in an isolated Linux clone — full suite **9,433 passed / 0 failed**,
`ruff check .` clean.

## Integrate (run on your machine)

```
git fetch fix-chat-routing-zero-token.bundle fix/chat-routing-zero-token:fix/chat-routing-zero-token
git push -u origin fix/chat-routing-zero-token
# then open the PR on GitHub; merging stays your call
del fix-chat-routing-zero-token.bundle
```

## ⚠ .git incident (read first)

A `git worktree add` from the sandbox corrupted `.git/config` through the mount
(blocked lock-file unlink mid-write). I restored it from `.git/config.bak.1780506223`
(June 3 backup, truncated tail line removed) at ~23:14. The mount's view then
desynced, so verify on your side:

1. `git status` — if it errors on config, restore: the correct content is the June 3
   backup **minus its dangling last line** (`[branch "i`). Core sections (origin
   remote, main tracking, user) are all in the first 20 lines.
2. Delete `.git/config.lock` if present (sandbox couldn't unlink it).
3. Branch-tracking entries created June 3→4 were lost (harmless; `push -u` re-adds).

No other `.git` state was touched from the sandbox after the restore.

## What the branch fixes (the "use almost no API" goal)

1. **ef903609 — entity matcher lead-ins** (the big one). "whats the / what is the /
   tell me about / can you tell me / hey," lead-ins defeated entity isolation, so
   natural phrasings of factual lookups missed Tier 1 and burned ~4k tokens each.
   Now stripped iteratively before matching. `whats the phone number for Mudshark
   Brewery` → Tier 1, 0 tokens.
2. **ab26258b — about-shape guard**. "tell me about X" can never be claimed by a
   category intent again (the "Here's what's good to eat." bug).
3. **ab09d2f5 — rent/hire/book/charter** are listing shapes: "where can i rent a
   boat" now returns a zero-token category listing, not one provider's address.
4. **113d7dc5 — 5,604-phrase bank** (was 480) generated deterministically from
   templates × the resolver's own dicts (`scripts/generate_intent_phrases.py`,
   zero API). 100% validated routing; committed as the CI regression gate. The
   validation run surfaced and fixed 8 resolver gaps (plurals, "what is on",
   who's-open shapes, symptom-before-service, boat mechanic → boat_repair,
   food bank, "what should we do this weekend").
5. **7dd1e890 — recommendation-shaped LOCATION/COST turns** ("where should we
   stay") now reach the intent layer instead of tier 3; week-strip grammar fix.

## Verified effect (local battery, seeded catalog, NO API keys)

15/17 diagnosis-battery queries answer deterministically (0 tokens, <50ms route);
16/17 effective on prod (gas needs the prod gas cache). The only true API case
left is open-ended synthesis ("tell me about X" prose), which stays semantically
cached.

## Follow-ups needing you (not in this branch)

- **Prod data audit**: "Restaurants" listings include providers with category
  Service/Bakery — bad `subcategory` backfill rows on prod (needs prod DB read,
  gated by your approval).
- **`USE_LLM_ROUTER` on Railway**: if enabled, it adds an OpenAI call to every
  non-Tier-1 ask just for routing. With this branch the deterministic paths cover
  far more — recommend turning it OFF and watching tier mix in chat_logs.
- Confirm `USE_INTENT_LAYER=1` stays on (it's doing the heavy lifting now).
- Optional next slice: deterministic business-card answer for "tell me about X"
  (kills the last common API case); L3 fuzzy exemplars from the new bank.
