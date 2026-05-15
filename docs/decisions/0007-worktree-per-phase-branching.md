# 0007. Worktree-per-phase branching

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

The 21-day Atelier sprint runs three sequential phases (Foundation / 10× Mechanisms / Production Polish), each with a defined acceptance gate. We need a branching strategy that:

- Keeps `main` always shippable (only accepted-and-tagged work)
- Allows each phase its own working tree (multiple phases active concurrently if needed)
- Enables hotfixes to accepted phases without disrupting active phase development
- Provides a clean acceptance boundary (visible tag per phase gate)
- Preserves the sprint plan even if a phase is rejected and reworked

Three options:

1. **Trunk-based development** — all work on `main` directly
2. **GitFlow** (long-running `develop` + feature branches + release branches)
3. **Git worktrees with one branch per phase** (per AutonomousAgent ADR 0007 lineage)

## Decision

We will use **git worktrees with one long-running branch per phase**, all rooted at the same git repo, checked out under `.worktrees/`:

```
github.com/Manzela/atelier/                     ← branch: main (accepted-only)
├── .worktrees/                                 ← gitignored
│   ├── phase1-foundation/                      ← branch: phase/1
│   ├── phase2-10x-mechanisms/                  ← branch: phase/2 (created when phase/1 accepted)
│   └── phase3-production-polish/               ← branch: phase/3 (created when phase/2 accepted)
```

**Branching rules:**

- `main` holds **only accepted-and-tagged** work (`phase1-accepted`, `phase2-accepted`, `phase3-accepted`, `v1.0.0`+)
- All sprint work happens in `.worktrees/phaseN-<name>/` on branch `phase/N`
- Acceptance gate passes →

  ```bash
  git checkout main
  git merge --no-ff phase/N -m "Merge phase/N: <gate description>"
  git tag -a phaseN-accepted -m "Phase N accepted on $(date -u +%Y-%m-%d). All gate criteria passed."
  git push origin main --tags
  ```

- Hotfixes: branch from `main` as `hotfix/<short-desc>`, merge back to `main` + cherry-pick to active phase branch
- Within a phase, feature branches off the phase branch are allowed (`feat/intake-visual-options` off `phase/2`)

**Worktree creation:**

```bash
git branch phase/N main                                # create branch from main
git worktree add .worktrees/phaseN-<name> phase/N      # create worktree
cd .worktrees/phaseN-<name>
git submodule update --init --recursive                # if any submodules; not used currently
```

## Consequences

### Positive

- `main` is always shippable (only accepted work merged); CI on `main` reflects production state
- Multiple phases can have working trees simultaneously (e.g., Phase 1 hotfix while Phase 2 develops)
- Each worktree is a normal directory; no `git stash` dance to switch contexts
- IDE / test / build environments per worktree don't interfere with each other (separate `node_modules/`, separate `.venv/`)
- Disk overhead is small (worktrees share the `.git/objects` store)
- Visible acceptance tags create a public record of phase gates (judges can verify)
- Pattern matches AutonomousAgent ADR 0007 lineage (proven on the user's prior project)

### Negative

- More cognitive overhead than single-checkout flow (especially for new contributors)
- `.worktrees/` must be gitignored (don't commit the worktrees themselves) — already handled in `.gitignore`
- Some tools (older IDEs, some npm scripts) don't understand worktrees (rare in 2026)
- Pre-commit hooks installed per worktree — must `pre-commit install` after each `git worktree add`

### Neutral

- This pattern is common in large monorepos and multi-version maintenance
- GitHub PRs target the phase branch (`phase/N`), not `main` — slightly different from typical OSS workflow but documented in CONTRIBUTING.md

## Alternatives considered

### Option A: Trunk-based development (all work on `main`)

- Pros: Simplest mental model; always integrated
- Cons: Phase failures contaminate `main`; no clean acceptance boundary; can't have two phases active simultaneously
- Why rejected: We explicitly want phase isolation per the iterative-phase build model; rejected and reverted phases would corrupt `main`

### Option B: GitFlow (long-running `develop` + feature/release branches)

- Pros: Explicit release process; mature pattern
- Cons: `develop` adds another long-running branch to maintain; release branches don't map to "phase acceptance" cleanly; over-engineered for a 21-day sprint
- Why rejected: GitFlow is designed for longer release cycles than our 7-day phases

### Option C: Multiple full clones (one repo per phase)

- Pros: Total isolation
- Cons: Disk overhead; remote pulls in N places; sub-state diverges; merging back to main is error-prone
- Why rejected: Worktrees give the same isolation more efficiently with shared `.git/objects`

## References

- [AutonomousAgent ADR 0007](file:///Users/danielmanzela/RX-Research%20Project/AutonomousAgent/docs/decisions/0007-worktree-per-phase-branching.md) — direct lineage
- [git-worktree docs](https://git-scm.com/docs/git-worktree)
- [PRD §28 Worktree-per-phase branching](../superpowers/specs/2026-05-14-atelier-prd.md)
- [`docs/conventions/branching.md`](../conventions/branching.md) — operational guide
