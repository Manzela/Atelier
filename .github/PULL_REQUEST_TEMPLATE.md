# Pull Request

## Summary

<!-- 1-3 sentences. What does this PR do and why? -->

## Type of change

<!-- Check all that apply -->

- [ ] `feat` — New user-facing capability
- [ ] `fix` — Bug fix
- [ ] `docs` — Documentation only
- [ ] `chore` — Maintenance (deps, config, repo housekeeping)
- [ ] `refactor` — Internal restructuring, no behavior change
- [ ] `test` — Adding or fixing tests
- [ ] `perf` — Performance improvement
- [ ] `security` — Security fix or hardening
- [ ] `build` — Build system / Docker / packaging
- [ ] `ci` — CI/CD config

## Scope

<!-- Which subsystem(s) does this affect? -->

- [ ] `intake` (PIP)
- [ ] `campaign` (Campaign Orchestrator + RLRD)
- [ ] `dag` (8-node atomic DAG)
- [ ] `judge` (consensus + per-axis rubrics + DEMAS-D)
- [ ] `gate` (deterministic gates: Lighthouse, axe, etc.)
- [ ] `flywheel` (3-tier DPO + Hebbian mutator + LoRA training)
- [ ] `adk` (ADK integration wrappers)
- [ ] `tools` (MCP wrappers, integrations)
- [ ] `render` (A2UI renderers)
- [ ] `memory` (Memory Bank + cross-session)
- [ ] `eval` (eval suite, benchmarks, golden sets)
- [ ] `deploy` (infra, Docker, CI)
- [ ] `dashboard` (live observability UI)
- [ ] `action` (GitHub Marketplace)
- [ ] `figma` / `chrome` (extensions)
- [ ] `tests`
- [ ] `docs` / `runbook` / `adr`

## Related

<!-- Issue / ADR / Spec section -->

- Closes #
- Refs ADR:
- PRD section:

## Acceptance criteria

<!-- Specific, falsifiable. Each box must be ✅ before merge. -->

- [ ] Tests added / updated
- [ ] Pre-commit passes (`pre-commit run --all-files`)
- [ ] mypy strict passes
- [ ] Eval delta clean (no regression on `pytest tests/eval/ --baseline=HEAD~1`)
- [ ] Docs updated where behavior changed
- [ ] No new dependency without ADR + lockfile-pinned add
- [ ] No `--no-verify`, no `force-push`, no silent `except` blocks
- [ ] Conventional Commits format on all commits in this PR
- [ ] PR targets `phase/N` branch (NOT `main`) per ADR 0007

## Test plan

<!-- How was this tested? Bulleted markdown checklist. -->

- [ ]
- [ ]

## Screenshots / Recordings

<!-- For UI changes, attach before/after screenshots or a short Loom. -->

## Risk assessment

<!-- What could go wrong? Maps to PRD §6.4 trichotomy: fail-loud / fail-soft / self-heal. -->

**Failure mode**:
**Blast radius**:
**Mitigation**:

## Reviewer notes

<!-- Anything the reviewer should pay extra attention to? Surprising decisions? -->

## Checklist

- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] My code follows the project's [code style](../docs/conventions/code-style.md)
- [ ] My commits follow [Conventional Commits](../docs/conventions/commit-messages.md)
- [ ] I have read the ADR(s) referenced above (or filed a new one if this is an architectural change)
- [ ] I have not modified upstream packages (per ADR 0001 wrap-don't-fork)
- [ ] I have not committed secrets, large binaries, or `.env` files
- [ ] I have updated `CHANGELOG.md` `[Unreleased]` section if this is user-facing
