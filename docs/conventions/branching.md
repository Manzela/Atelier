# Branching & Worktree Convention

This project uses **git worktrees with one branch per sprint phase**. See [ADR 0007](../decisions/0007-worktree-per-phase-branching.md) for the rationale.

## Branches

| Branch                | Purpose                               | Lifecycle                                                                     |
| --------------------- | ------------------------------------- | ----------------------------------------------------------------------------- |
| `main`                | Accepted-and-tagged work only         | Permanent; `--no-ff` merge per phase + tag `phaseN-accepted`                  |
| `phase/1`             | Phase 1 Foundation development        | Created Day 1; merged to `main` at `phase1-accepted`; deletable after merge   |
| `phase/2`             | Phase 2 10× Mechanisms development    | Created when `phase1-accepted` is tagged                                      |
| `phase/3`             | Phase 3 Production Polish development | Created when `phase2-accepted` is tagged                                      |
| `feat/<short-desc>`   | Feature branch off active phase       | Branched from `phase/N`; merged back to `phase/N` via PR                      |
| `fix/<short-desc>`    | Bug-fix branch off active phase       | Same as `feat/`                                                               |
| `hotfix/<short-desc>` | Urgent fix to accepted code           | Branched from `main`; merged to `main` + cherry-picked to active phase branch |

## Worktree layout

```
github.com/Manzela/atelier/                     ← branch: main
├── .worktrees/                                 ← gitignored
│   ├── phase1-foundation/                      ← branch: phase/1
│   ├── phase2-10x-mechanisms/                  ← branch: phase/2
│   └── phase3-production-polish/               ← branch: phase/3
```

## Creating a phase worktree

```bash
# From the main worktree:
git branch phase/N main                                    # create branch from main
git worktree add .worktrees/phaseN-<short-name> phase/N    # create worktree
cd .worktrees/phaseN-<short-name>
pre-commit install                                         # per-worktree hook
pre-commit install --hook-type commit-msg                  # commitlint
```

## Working in a phase

```bash
cd .worktrees/phaseN-<short-name>

# Create a feature branch off the active phase
git checkout -b feat/intake-visual-options

# Normal workflow
git add atelier-core/src/atelier/intake/visual_options.py
git commit -m "feat(intake): add visual options for register-selection question"
git push -u origin feat/intake-visual-options

# Open PR against phase/N (NOT main)
gh pr create --base phase/N --title "feat(intake): add visual options"
```

## Phase acceptance → merge to main

When the phase passes its acceptance protocol:

```bash
# From the main worktree:
cd "$(git rev-parse --show-toplevel)"
git checkout main
git pull
git merge --no-ff phase/N -m "Merge phase/N: <one-line gate description>"
git tag -a phaseN-accepted -m "Phase N accepted on $(date -u +%Y-%m-%d). All gate criteria passed."
git push origin main --tags
```

After merging, leave the phase worktree in place if you might still need it; otherwise clean up:

```bash
git worktree remove .worktrees/phaseN-<short-name>
git branch -d phase/N
```

## Hotfixes

```bash
# From main worktree:
git checkout main
git checkout -b hotfix/short-desc
# fix, test, commit
git checkout main
git merge --no-ff hotfix/short-desc -m "hotfix: <description>"
git push

# Cherry-pick to active phase branch:
cd .worktrees/phaseN-<short-name>
git cherry-pick <hotfix-sha>
git push
```

## Don'ts

- ❌ Don't commit directly to `main` (except for merging accepted phase branches and hotfixes)
- ❌ Don't delete `.git/` from a worktree (it's a pointer file; use `git worktree remove`)
- ❌ Don't rebase a phase branch after others have based work on it (we're solo, but this still bites)
- ❌ Don't `force-push` to `main` (CLAUDE.md invariant + branch protection)
- ❌ Don't open PRs against `main` mid-phase (target the phase branch)
- ❌ Don't squash-merge phase branches (use `--no-ff` to preserve PR history)

## Branch protection on `main`

Configured at repo settings (set on D1):

- Require PR for all changes
- Require ≥ 1 approval (even solo, for discipline)
- Require status checks to pass before merging: `CI Success`
- Require branches to be up-to-date before merging
- Require linear history (no merge commits except `--no-ff` accepted-phase merges via local CLI by maintainer)
- Restrict pushes that create files larger than 100 MB
- Do not allow force pushes
- Do not allow deletions
