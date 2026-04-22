# Phase 8.0.1.5 — Dispositions summary (2026-04-22)

Short Cursor handback after owner review. **Authoritative table + narrative:** `docs/phase-8-0-1-5-owner-dispositions-2026-04-22.md` (new, untracked until committed with the batch).

---

## Where the decisions live

Your walkthrough and locked calls are saved in **`docs/phase-8-0-1-5-owner-dispositions-2026-04-22.md`**.

---

## The four calls (as recorded)

1. **#4** → **KEEP** (owner override of Cursor’s default DELETE).
2. **#9** → **KEEP** (weak default; minimal-tree **DELETE** still allowed).
3. **#12** → **DELETE** (aligned with Cursor).
4. **Gitignore** → **ADD** both proposed lines — with a **conflict note** in the dispositions file: **KEEP #9**’s path matches `docs/phase-*-cursor-prompt-review-*.md`, so the execute step should either use **only** the `chat-export` rule, add **`!docs/phase-6-4-1-cursor-prompt-review-2026-04-21.md`**, or **rename** #9 so it isn’t ignored.

---

## Counts (for execute prompt)

- **7 DELETE**
- **11** inventory **KEEP**
- Plus **3** meta files (`phase-8-0-1-5-housekeeping-plan.md`, `phase-8-0-1-5-cursor-handback-2026-04-22.md`, `phase-8-0-1-5-owner-dispositions-2026-04-22.md`) → **14** doc paths to stage + **`.gitignore`**

---

## #17 (`t3-24`) note

Documented in **`docs/phase-8-0-1-5-owner-dispositions-2026-04-22.md`**: keep for **8.0.2**; candidate cleanup in **8.0.7** once explicit-rec bypass is shipped.

---

## Next step

Paste **`docs/phase-8-0-1-5-owner-dispositions-2026-04-22.md`** into the **8.0.1.5 execute** prompt as the single source of truth for `git add` / `rm` / `.gitignore` resolution (including the gitignore conflict options).
