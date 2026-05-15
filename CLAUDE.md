# CLAUDE.md — Sprint Invariants (auto-loaded)

> **NEW CONVERSATION? READ THIS FIRST**: [`docs/superpowers/specs/SESSION-COMPLETE-2026-05-14-atelier-pre-sprint-bootstrap.md`](docs/superpowers/specs/SESSION-COMPLETE-2026-05-14-atelier-pre-sprint-bootstrap.md) — the canonical handoff from the brainstorm + scaffold session. Survives context loss. Read it on every new conversation, then run the 90-second restoration ritual below, then pick the next unblocked feature from `features.json`.

> This file is automatically loaded into every Claude Code session in this repository. It encodes the non-negotiable discipline of the Atelier sprint per PRD §11 Strategy v2. Read it at session start; respect it throughout.

## Identity

- Project: **Atelier** — autonomous design agent for the Google for Startups AI Agents Challenge 2026
- Repo: `github.com/Manzela/atelier`
- Sprint window: **2026-05-15 → 2026-06-04** (3 weeks)
- Submission target: **2026-06-03 noon** (2 days early)
- Build budget: **$5K Claude Opus 4.7 MAX capacity** via Vertex AI

## Spec-anchored development

The PRD at [`docs/superpowers/specs/2026-05-14-atelier-prd.md`](docs/superpowers/specs/2026-05-14-atelier-prd.md) is the **canonical source of truth**. ADRs accumulate in [`docs/decisions/`](docs/decisions/). [`DECISIONS.md`](DECISIONS.md) at repo root is auto-injected into every subagent dispatch — re-litigation of locked decisions is prevented at the prompt level. [`REJECTED.md`](REJECTED.md) records failed approaches with rationale; future sessions don't re-attempt dead ends.

Mid-sprint changes to the PRD require an explicit ADR commit, not silent drift.

## Session restoration ritual (90 seconds, every new session)

```bash
cd "$(git rev-parse --show-toplevel)"
cat docs/sprint/STATUS.md
cat docs/sprint/BLOCKERS.md
tail -50 docs/sprint/CHECKPOINTS.md
tail -20 docs/sprint/REJECTED.md
tail -7 docs/sprint/COST_LEDGER.md
cat features.json | jq '.[] | select(.passes == false) | .id' | head -10
tail -50 claude-progress.txt
git log --oneline -20
git status
git worktree list
gh run list --limit 5
```

If the previous session ended mid-feature, CHECKPOINTS.md ends with a `RESUME-HERE:` marker pointing to the exact file, line, and intent.

## Non-negotiable invariants

```xml
<no_unverified_apis>
Before importing any non-stdlib library, verify the API exists:
- ADK / Vertex AI / Gemini: query context7 with the library ID
- Other Python: `python -c "import LIB; print(LIB.__version__)"` first
- npm: `npm view PKG version` first
- Google Cloud SDKs: cite official docs URL in a comment
If verification fails, do NOT write the import. Report the gap.
</no_unverified_apis>

<compile_then_commit>
No Python file commits without:
1. `mypy --strict path/to/file.py` exit 0
2. `python -c "import module.path"` exit 0
3. `pytest -x --no-header tests/path/test_file.py` exit 0
No TypeScript without `tsc --noEmit` exit 0.
No Markdown without `markdownlint` exit 0.
</compile_then_commit>

<no_speculation>
Never speculate about code you have not opened. If a file is referenced,
you MUST Read it before answering. Give grounded, hallucination-free
answers. If you don't know, say "I need to verify" and verify.
</no_speculation>

<eval_delta_required>
No commit ships without an eval-delta check. Code change:
`pytest tests/eval/ --baseline=HEAD~1` must show no regression.
Doc change: `markdownlint` + `markdown-link-check` must pass.
</eval_delta_required>

<no_test_driven_slop>
Write general-purpose solutions. No helper scripts to game tests.
No hard-coded values to pass tests. If a test is wrong, fix the test
(justified in commit message), not the code under test.
</no_test_driven_slop>

<no_silent_error_suppression>
Bare `except:`, `except Exception: pass`, and silent `try` blocks
are forbidden. Every caught exception must be logged with structured
context AND either re-raised, returned as a structured error, OR
have an explicit comment justifying the swallow.
</no_silent_error_suppression>

<json_state_files>
features.json, COST_LEDGER (json variant), and any other
agent-edited state file uses JSON not Markdown. Per Anthropic
2025 finding: Claude is less likely to silently rewrite JSON.
</json_state_files>

<no_destructive_git>
Forbidden without explicit human approval:
- git push --force / --force-with-lease
- git reset --hard
- git checkout -- .
- git clean -fd
- rm -rf any path under git control
- git branch -D for unmerged branches
Document the reason in the commit message if approved.
</no_destructive_git>

<lockfile_only_installs>
No ad-hoc `pip install LIB` or `npm install PKG`.
All deps via `pip install -r requirements.lock` or `npm ci`.
New dep: add to requirements.in or package.json, regenerate lock,
commit lock + verify Snyk scan, then install.
Defends against slopsquatting (LiteLLM Mar 2026 incident).
</lockfile_only_installs>

<wrap_dont_fork>
Atelier consumes upstream code via lockfile-pinned dependencies and
wraps it. Modifications to upstream packages (agent-dag-pipeline,
google-adk, hermes-agent) are out of scope. To fix upstream behavior:
file the issue upstream, submit PR upstream, pin our dep to the new
upstream version. Per ADR 0001.
</wrap_dont_fork>

<conventional_commits_required>
Every commit follows Conventional Commits 1.0.0:
  <type>(<scope>): <subject>
  <body>
  <footer>
Enforced by commitlint pre-commit hook.
</conventional_commits_required>

<wrap_phase_work_in_worktrees>
Per ADR 0007, all sprint work happens in .worktrees/phaseN-<name>/
on branch phase/N. Never commit directly to main except for merging
accepted phase branches and hotfixes.
</wrap_phase_work_in_worktrees>
```

## Failure-handling trichotomy

Every operation in Atelier maps to exactly one mode:

- **Fail-loud** (alert + halt): security failures, budget breach, data corruption
- **Fail-soft** (degrade + log + acknowledge): tool errors, transient unavailability
- **Self-heal** (retry silently with bounded backoff): transient 429/503, container restarts

User-facing rule: **agent always acknowledges degradation.** Trust > apparent capability. Hard cap: 3 self-heal retries per operation, then escalate to fail-soft.

## Subagent dispatch defaults

When dispatching subagents:

| Tier                           | Model        | Budget                           |
| ------------------------------ | ------------ | -------------------------------- |
| Orchestrator (main session)    | Opus 4.7 MAX | —                                |
| Planner subagent               | Opus 4.7 MAX | 10 tool calls, 5K output tokens  |
| Implementer subagent (routine) | Sonnet 4.6   | 50 tool calls, 30K output tokens |
| Implementer subagent (novel)   | Opus 4.7 MAX | 50 tool calls, 30K output tokens |
| Reviewer subagent              | Opus 4.7 MAX | 30 tool calls, 5K output tokens  |
| Evaluator subagent             | Sonnet 4.6   | 40 tool calls                    |
| Lint/grep/format               | Haiku 4.5    | 20 tool calls                    |

Every subagent dispatch carries the cached PRD/architecture/DECISIONS prefix (~33K tokens, 1h TTL breakpoint). Subagents return ≤500 word distilled summaries with a mandatory `gaps.md` section.

## Anti-premature-completion

Reviewer subagent must emit a strict **"DONE"** token (Ralph Loop pattern) before any merge. No DONE = back to Fixer. Three "REJECTED" cycles in a row = explicit non-convergence response surfaced to user.

## Eval-driven development

Six eval surfaces with explicit cadences:

| Surface                             | Cadence                        |
| ----------------------------------- | ------------------------------ |
| Smoke tests                         | Every commit (pre-commit + CI) |
| Integration suite                   | Every PR (CI gate)             |
| WebGen-Bench full (484 tasks)       | Nightly + on-tag               |
| Calibration golden set (100 tasks)  | Weekly Mon 03:17 UTC           |
| Adversarial set (50 tasks held-out) | Pre-release                    |
| Designer-in-residence sessions      | Weekly                         |

Results published to `bench.atelier.dev` + `calibration.atelier.dev`.

## Daily checkpoint ritual (end of each session)

1. Update `docs/sprint/CHECKPOINTS.md` with what shipped today
2. Run full test suite (must pass)
3. Run eval suite delta (must not regress)
4. Commit + push to phase branch (NOT main)
5. Note any new blockers in `docs/sprint/BLOCKERS.md`
6. Note tomorrow's first task in `docs/sprint/STATUS.md`
7. Update `docs/sprint/COST_LEDGER.md` (verify cache-hit-rate ≥85%)
8. Append session summary to `claude-progress.txt`

## Hard rules that don't bend

- No `--no-verify` ever
- No `force-push` without explicit human approval + commit-message rationale
- No silent `except` blocks
- No mocking what should be integration-tested
- No "we'll fix it later" without GitHub Issue + deadline
- No undocumented commits
- No new dependencies without ADR + lockfile-pinned add
- No spec changes without ADR + checkpoint commit
- No claiming "done" without verification-before-completion + Reviewer "DONE" token + eval-delta clean
- No skipping the daily CHECKPOINTS.md update

---

**This file is the discipline. Every shortcut here costs us the sprint. Read it, internalize it, follow it.**
