# Claude Code dispatch — investigate red CI on `f0a46f8` (and back through `b71cf0e`)

> Drop-in artifact for the operator to paste into Claude Code terminal.
> Investigates why GitHub Actions has been showing red X marks on docs-only
> commits going back through Phase 5.2 SHIPPED (`b71cf0e`).
>
> Pytest collection is healthy locally (1855 tests collected in 4.12s
> — verified against `f0a46f8` HEAD on operator's Windows venv this
> session). The failure is therefore NOT a test-tree issue. Most likely
> root causes are workflow-file misconfiguration, missing CI env var, or
> ruff/mypy lint failure on a previously-tolerated style.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.3 session
> (2026-05-15) post-`7c994aa`.

---

## §1 Context for Claude Code

**The observation:** GitHub Actions runs on recent main commits are red.
Visible to operator on the Actions tab; multiple consecutive docs-only
commits get red X marks:

- `f0a46f8` chore(outputs): Phase 5.3 kickoff (docs-only)
- `b71cf0e` chore(outputs): Phase 5.2 SHIPPED (docs-only)
- `81cd70c` chore(outputs): Phase 5.2 session close-out (docs-only)
- `65b0824` fix(scripts): places_load resolver sustainability + ruff lint clean
- earlier — pattern continues

**What it can't be:** test-tree collection. Verified locally:

```
(.venv) PS C:\Users\casey\projects\havasu-chat> python -m pytest -q --collect-only 2>&1 | Select-Object -Last 3
tests/test_webtrac_parser.py::NonAvailableStateTests::test_unavailable_state
1855 tests collected in 4.12s
```

1855 matches the documented Phase 5.2 close-out baseline. No drift.

**Why it matters:** Phase 5.3 SHIPPED is imminent. Shipping on top of a
red main is acceptable in the short term but unhealthy for the lane.
Phase 5.4 (Health, Wellness & Care) dispatches next — better to clear
red main first.

## §2 Investigation steps

```bash
# 1. List recent workflow runs + their status
cd ~/projects/havasu-chat   # or wherever you've checked out the repo
gh run list --branch main --limit 12

# 2. Pull the first red run's logs to find the failing job
gh run view <run-id> --log-failed | head -200

# 3. Check workflow files for recent changes
git log --oneline --since="2 weeks ago" -- .github/workflows/

# 4. Run the workflows locally if reasonable
# (Look at what each workflow does — pytest, ruff, mypy, etc. — and run that
# command locally. If it passes locally and fails in CI, the issue is
# environmental: missing CI secret, action version mismatch, OS difference.)

# 5. Common candidates to check:
#    - .github/workflows/test.yml — is the python-version pinned to a version
#      no longer available?
#    - .github/workflows/lint.yml — has ruff been updated to a stricter rule
#      that flags pre-existing code?
#    - secrets — does CI need GOOGLE_PLACES_API_KEY or OPENAI_API_KEY that
#      isn't set in repo secrets?
#    - action versions — is anything on `actions/checkout@v3` or older that's
#      hit the GitHub deprecation cutoff?

# 6. If the failure is consistent across all recent runs (same job/step),
# the fix is likely a one-line workflow-file change. If failures are
# inconsistent, look for flakiness (sleep + retry, missing test isolation).
```

## §3 Expected output

A short diagnosis with:
- **Failing job name** (e.g., "test", "lint", "type-check")
- **Failing step** (e.g., "Run pytest", "Run ruff", "Install dependencies")
- **Root cause class** (env var missing / action deprecated / lint rule
  added / pytest config drift / etc.)
- **Recommended fix** (one-line diff against the workflow file or a one-line
  config tweak)

If the fix is small + obvious + safe, Claude Code can implement + commit
+ verify it ran green. If the fix is non-obvious or requires operator
input (e.g., adding a new repo secret), surface for operator decision.

## §4 Out of scope

- Do not change `pytest.ini`, `pyproject.toml`, or `requirements.txt`
  unless the diagnosis specifically points to them.
- Do not skip / xfail tests to make CI green.
- Do not add new linting exclusions to mask pre-existing code smells.

## §5 Reference

- `outputs/phase5_2_session_closeout.md` (Phase 5.2 commit chain; the
  red-CI window started somewhere in here)
- `outputs/phase5_3_home_property_services_kickoff.md` (Phase 5.3
  context)
- `.github/workflows/*.yml` (CI definitions)

---

*Drop-in dispatch artifact authored by Cowork primary, Phase 5 lane,
Phase 5.3 session (2026-05-15) post-`7c994aa`. Operator dispatches to
Claude Code at convenience. Not 5.3 gate-blocking but cleaner to ship
5.3 on green main.*
