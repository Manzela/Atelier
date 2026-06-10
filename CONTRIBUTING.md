# Contributing to Atelier

Thank you for your interest in contributing. This document covers everything you need to know to make your first contribution successful.

## Quick start

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/atelier.git
cd atelier

# 2. One-time bootstrap
./init.sh

# 3. Install pre-commit hooks
pre-commit install

# 4. Verify environment
./atelier-deploy/scripts/verify-prereqs.sh

# 5. Run the test suite
cd atelier-core && pytest tests/unit/ -v
```

## Development environment

### Required

- **Python** 3.11+ (`pyenv install 3.11.9` recommended; see `.python-version`)
- **Node** 20.11+ (`nvm install` from `.nvmrc`)
- **Docker** 24+ (for local sandboxes + integration tests)
- **`gcloud` CLI** authenticated to a sandbox GCP project (for Vertex AI calls)
- **`gh` CLI** authenticated (for repo operations)
- **`pre-commit`** (`pip install pre-commit`)
- **`commitlint`** (`npm install -g @commitlint/cli @commitlint/config-conventional`)

### Optional but recommended

- **`bun`** (faster Node runtime; for the dashboard)
- **`age` + `sops`** (secrets management in dev; production uses Cloud KMS)
- **`tmux`** (long-running sessions)

## Branching model — worktree-per-phase

Per the project branching model, Atelier uses git worktrees with one branch per sprint phase:

```
atelier/                                    ← branch: main (accepted-only)
├── .worktrees/                             ← gitignored
│   ├── phase1-foundation/                  ← branch: phase/1
│   ├── phase2-10x-mechanisms/              ← branch: phase/2
│   └── phase3-production-polish/           ← branch: phase/3
```

**Branching rules**:

- `main` holds **only accepted-and-tagged** work (`phase1-accepted`, `phase2-accepted`, `phase3-accepted`, `v1.0.0`+)
- All sprint work happens in `.worktrees/phaseN-<name>/` on branch `phase/N`
- Acceptance: `git merge --no-ff phase/N + git tag phaseN-accepted`
- Hotfixes: branch from `main` as `hotfix/<short-desc>`, merge back to `main` + cherry-pick to active phase branch

**Day-to-day**:

```bash
# Create a feature branch off the active phase worktree
cd .worktrees/phaseN-<name>
git checkout -b feat/my-feature

# Work, commit, push
git push -u origin feat/my-feature

# Open PR against the active phase branch (not main)
gh pr create --base phase/N --title "feat(scope): description"
```

## Commit messages — Conventional Commits 1.0.0

Strictly enforced via `commitlint` pre-commit hook.

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `security`, `build`, `ci`, `revert`

**Scopes** (project-specific):
`intake`, `campaign`, `dag`, `judge`, `gate`, `flywheel`, `adk`, `tools`, `render`, `memory`, `eval`, `deploy`, `dashboard`, `action`, `figma`, `chrome`, `tests`, `docs`, `runbook`, `adr`

**Examples**:

```
feat(intake): add visual options for register-selection question

Implements the 4-thumbnail visual picker for "what visual feel?" question.
Activates only when feature flag intake.visual_options_enabled is true.

Refs: #42
```

```
fix(judge): handle Gemini 3 Flash 429 with exponential backoff

Vertex AI was returning 429 during region failover; without backoff we
hammered the endpoint and degraded the consensus vote.
```

```
docs(adr): 0011 a2ui-flutter-renderer-strategy
```

## Pull request process

1. **Fork + branch off the active phase** (not `main`)
2. **Make your changes** — keep them focused (one feature or fix per PR)
3. **Add tests** — unit tests for logic, integration tests for cross-component interactions
4. **Update docs** — if you changed behavior, update the relevant docs/ entry
5. **Run pre-commit** — `pre-commit run --all-files`
6. **Run tests** — `pytest tests/ -v` in the affected subfolder
7. **Open PR** — fill out the PR template completely
8. **Wait for CI** — all checks must pass before review
9. **Address review comments** — push commits, don't rebase mid-review
10. **Maintainer merges** — `--no-ff` merge to preserve PR history

### What we look for in a PR

| Aspect            | Requirement                                                                    |
| ----------------- | ------------------------------------------------------------------------------ |
| **Tests**         | New code has tests. Bug fixes have a regression test. Coverage doesn't drop.   |
| **Docs**          | If you change behavior, you change docs. New public API → docstring + example. |
| **Types**         | All public functions have type hints. `mypy --strict` passes.                  |
| **Style**         | `ruff format` + `ruff check` pass. No silent `except:` or bare `pass`.         |
| **Commits**       | Conventional Commits format. One concept per commit. Body explains WHY.        |
| **Security**      | No secrets in code. Pre-commit `detect-secrets` passes.                        |
| **Performance**   | No regression > 10% on smoke benchmarks. New hot path → microbenchmark.        |
| **Compatibility** | No breaking change without an ADR + major version bump.                        |

## Testing

### Unit tests (fast, < 30s total)

```bash
cd atelier-core
pytest tests/unit/ -v
```

### Integration tests (medium, ~5 min)

```bash
cd atelier-core
docker compose -f tests/integration/docker-compose.test.yml up -d
pytest tests/integration/ -v
docker compose -f tests/integration/docker-compose.test.yml down
```

### Eval suite (slow, ~30 min for full WebGen-Bench)

```bash
cd atelier-eval
pytest tests/ -v                         # adapter unit tests
python -m atelier_eval.runner --suite webgen_bench --subset 50  # quick subset
python -m atelier_eval.runner --suite webgen_bench               # full suite
```

### Conformance / replay tests

```bash
adk conformance record --agent atelier-core/agent.py --eval-set tests/conformance/golden.jsonl
adk conformance test --mode=replay --agent atelier-core/agent.py
```

## Code style

Highlights:

- **Python**: ruff format + check (line length 100, target 3.11+)
- **TypeScript**: prettier + eslint (line length 100, strict mode)
- **Shell**: bash strict mode at top (`set -euo pipefail`); quote everything
- **YAML**: 2-space indent; never tabs
- **Comments**: default to none; only when WHY is non-obvious
- **TODO**: must include date or issue reference: `# TODO(2026-06): refactor`

## Filing an issue

Use the [bug report](.github/ISSUE_TEMPLATE/bug.yml), [feature request](.github/ISSUE_TEMPLATE/feature.yml), [eval failure](.github/ISSUE_TEMPLATE/eval-failure.yml), or [docs issue](.github/ISSUE_TEMPLATE/docs.yml) templates. Include:

- **What you observed** vs **what you expected**
- **Steps to reproduce** (minimal + complete)
- **Environment** (Python version, Node version, Atelier version, OS)
- **Logs** (sanitized — strip secrets)
- **Atelier session ID** if applicable (helps us trace in BigQuery)

## Proposing an Architecture Decision Record

For decisions that lock in tradeoffs, affect code that's hard to unwind, or that future-you would want to know the reasoning for:

1. Open an issue tagged `adr-proposal` describing the problem
2. After discussion, create a decision document following the project template
3. Fill in: Status (`Proposed`), Context, Decision, Consequences, Alternatives
4. Open a PR titled `docs(adr): <NNNN> <title>`
5. Maintainer reviews and accepts or rejects

## Recognition

All contributors are acknowledged in:

- The release notes (auto-generated from Conventional Commits)
- `docs/CONTRIBUTORS.md` (rebuilt periodically)
- The repository [contributors page](https://github.com/Manzela/Atelier/graphs/contributors)

## Questions?

- General questions → [GitHub Discussions](https://github.com/Manzela/atelier/discussions)
- Real-time chat → Discord (post-launch)
- GitHub → [open an issue](https://github.com/Manzela/Atelier/issues) or a [discussion](https://github.com/Manzela/Atelier/discussions)

We're happy you're here.
