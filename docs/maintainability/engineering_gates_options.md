<!--
PURPOSE: Forward-looking option space for Phase D (CI lint + tests on PR;
formatting policy). NOT a commitment to any tool or infrastructure. Lays
out candidate tools, integration patterns, and unresolved scope questions
so the eventual Phase D ship has clear targets.

AUDIENCE: Future maintainers planning CI infrastructure work and
assistants briefing on past decisions. Read alongside
docs/maintainability/project_manager_organization_brief.md §5 Phase D
and docs/WORKING_AGREEMENT.md.

STATUS: Speculative. Phase D in BACKLOG #18 is unticked at time of
writing. This doc captures the option space; the eventual ship picks
from it.
-->

# Engineering gates — options space

## Why this exists

Phase D of the PM organization plan calls for CI lint + tests on PR and a single formatting tool with bounded scope. The repo has none of these as of 2026-05-04: no `.github/workflows/` directory, no pinned formatter, no committed lint config. The honest gate is "Casey runs `python -m pytest -q` locally before pushing"; per the PM brief, that's awkward on Windows dev machines and CI is the right enforcer.

Standing up CI is its own project — tool choice, auth wiring, scope decisions. This doc enumerates the option space so the eventual Phase D ship has explicit targets rather than reverse-engineering them from chat.

## Decision axes

Five orthogonal decisions. Each can be made independently of the others, though some combinations are more coherent than others.

### Axis 1 — CI host

Where do tests and lint actually run on PR?

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **GitHub Actions** | Native to repo. Matrix builds, concurrency control, secrets manager. Standard pattern. | New surface to maintain (workflow YAML, action versioning, runner config). | Free for public repos / generous limits for private. |
| **Railway scheduled hooks** | Already wired for deploy; could piggy-back. Same env as production. | Not designed for PR gating; no native GitHub integration; would need webhooks. | Inside existing Railway plan. |
| **Self-hosted runner on Casey's machine** | Full control; no third-party. | Reliability tied to Casey's machine; security posture for PRs from contributors needs thought. | Free; ops overhead. |
| **No CI; pre-commit hook only** | Zero infrastructure. | Misses problems that only surface in clean-environment runs. | Free; offers weakest guarantee. |

**Default if no answer:** GitHub Actions. Standard pattern, lowest cognitive overhead, scales if contributors are added.

### Axis 2 — Linter

| Tool | Strengths | Weaknesses |
|---|---|---|
| **ruff** | Fast (Rust). Single binary covers lint + format + import-sort. Replaces flake8/isort/pyupgrade ecosystem. Active development. | Newer; some lints differ from flake8 behavior. |
| **flake8 + plugins** | Mature, well-documented. Plugin ecosystem (bugbear, comprehensions, etc.). | Slower. Multi-tool config (flake8 + isort + black or autopep8). |
| **pylint** | Most thorough static analysis. Catches things others miss. | Slow. Noisy by default; requires significant configuration. False-positive rate higher than ruff. |
| **No linter** | Zero overhead. | Misses real bugs (unused imports, undefined names, dead code). |

**Default:** ruff. Speed advantage matters for CI feedback loops; single-tool simplicity matters for repo discipline.

### Axis 3 — Formatter

| Tool | Strengths | Weaknesses |
|---|---|---|
| **black** | Opinionated; ends bikeshedding. Mature, widely adopted. | Inflexible (by design). Some choices (string quotes, line length) not universally loved. |
| **ruff format** | Same engine as the linter. Fast. Black-compatible. | Newer than black; some edge cases may differ. |
| **autopep8** | PEP 8 compliance only; less aggressive. | Not opinionated enough — leaves stylistic variance. |
| **No formatter** | Zero overhead. | Drift accumulates; cosmetic-PR temptation grows. |

**Default:** ruff format (paired with ruff lint). One tool, one config file, fast.

### Axis 4 — Scope

The PM brief explicitly warns: "avoid whole-repo cosmetic churn in feature PRs." Three scope policies:

- **Whole-repo from day one.** Format the entire repo in a single "Slice X" before turning the formatter on. Subsequent PRs include only intentional changes.
  - Pros: Consistent state from day one.
  - Cons: Massive cosmetic-only diff. Loses git blame attribution. Conflicts with any in-flight branches.
- **New code only.** Formatter runs on changed files only. Old code stays as-is until next time it's touched.
  - Pros: No cosmetic-churn moment. Git blame preserved on untouched code.
  - Cons: Inconsistent state for an extended period.
- **Per-PR opt-in.** Formatter runs only when a PR explicitly requests it.
  - Pros: Maximum safety against unintended drift.
  - Cons: Defeats the point of having a formatter.

**Default:** new code only, with a documented "format-on-touch" rule. Casey's WORKING_AGREEMENT.md §6 ("Output formatting") already prefers narrow scope.

### Axis 5 — Test gate strictness

CI runs `python -m pytest -q`. Question: when does CI fail the PR?

- **Any test failure blocks merge.** Standard pattern.
- **Test failures in changed files block; failures in unchanged files warn.** Allows shipping urgent fixes when an unrelated test is flaky.
- **Test count regression blocks merge** (i.e. test was deleted/renamed without replacement).
- **Coverage threshold** (e.g. "no PR may decrease line coverage").

**Default:** any test failure blocks. Coverage thresholds are deferrable; complexity-vs-value isn't favorable until the test suite is much larger.

## Two integration patterns

Independent of tool choice, two patterns for how CI meshes with the existing workflow:

### Pattern A — PR gate only

CI runs on PR open and on push to PR branch. Main is protected: no merge if CI red. Push to main directly bypasses CI (already current state).

- **Pros:** Simple; matches GitHub default. Doesn't constrain ad-hoc fixes Casey ships directly to main.
- **Cons:** Direct-to-main pushes can break baseline. WORKING_AGREEMENT.md already requires Cursor halt + approval before push, but human discipline isn't enforced.

### Pattern B — PR gate AND main gate

CI runs on PR (gate merge) AND on push to main (gate deploy). If main goes red, no Railway deploy until fixed.

- **Pros:** Defense in depth.
- **Cons:** Couples Railway deploy to GitHub Actions (currently independent). More moving pieces.

**Recommendation:** Pattern A initially; revisit if direct-to-main red commits become a problem.

## Provisional first-build recommendation

If forced to commit with current information:

- **Axis 1 (host):** GitHub Actions.
- **Axis 2 (linter):** ruff.
- **Axis 3 (formatter):** ruff format.
- **Axis 4 (scope):** new code only.
- **Axis 5 (test gate):** any failure blocks.
- **Pattern:** A (PR gate only).

This is **provisional**. Tooling choices age fast; reconsider when Phase D actually becomes next on deck. The biggest commitment-cost is Axis 4 (whole-repo formatting touches every file once and is hard to undo); the rest are cheap to swap.

## Open questions still requiring product input

1. **Are there outside contributors?** If yes, signed-off CI matters more (security, supply chain). If no, internal discipline is the gate.
2. **What's the cadence?** Daily ships → strict CI helpful. Weekly ships → CI value drops; manual verification scales.
3. **Cost ceiling?** GitHub Actions free-tier limits; private-repo minutes; Railway billing. Worth measuring before committing.

## What an actual Phase D ship would look like

Phase D as a slice sequence (forward-looking, not committed):

- **Slice 40 — Pin formatter and lint config.** Add `pyproject.toml` ruff config. Run ruff format on the whole repo as a one-shot prep slice (or commit by commit per Axis 4 default). Document the config and policy in WORKING_AGREEMENT.md §6.
- **Slice 41 — GitHub Actions: PR test gate.** Add `.github/workflows/ci.yml` running `python -m pytest -q` on PR. Branch protection rule on main: "require CI to pass."
- **Slice 42 — Add lint to CI.** Same workflow gets a ruff lint step.
- **Slice 43 — Tighten gate.** Coverage threshold, test-count regression detector, or other strictness — when warranted.

Each is a separately-approved slice with its own STATE/BACKLOG entry. The total infrastructure stand-up is roughly 2-4 slices.

## Cross-references

- PM brief §5 Phase D: `docs/maintainability/project_manager_organization_brief.md` lines 71-76.
- WORKING_AGREEMENT.md §6 (Output formatting), already prefers narrow scope.
- BACKLOG #18 Phase D sub-bullet (currently unticked).
- BACKLOG #11 (slowapi DeprecationWarnings) is precedent for "gate caught a problem we'd otherwise ship blind"; CI lint would catch similar drift earlier.

## Status

This is a **forward-looking option space document**. It is **not a commitment** to any host, tool, or infrastructure. It exists so the eventual Phase D shipping sequence has explicit targets.

Update this doc when (a) Phase D actually ships and tools are pinned, in which case this becomes a retrospective and a lighter "current Phase D state" doc replaces it, or (b) the option space materially shifts (e.g., a tool is deprecated, GitHub Actions pricing changes, etc.).
