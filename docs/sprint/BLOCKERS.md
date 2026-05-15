# Sprint Blockers

> Live blockers + escalations. Auto-injected into every Claude Code session. Empty = green light.

---

## Active blockers

### 2026-05-15 11:30 UTC — Vite 5→6 security PRs failing CI

**Severity**: P2 (blocks feature)
**Blocked**: F-001 dashboard scaffold (D1)
**Owner**: Claude
**Description**: Dependabot PRs #21 (esbuild + vite + vitest grouped) and #22 (vite 5.4.21 → 6.4.2) address moderate-severity vite path-traversal advisory but fail pre-commit CI. PR #21 supersedes #22. Vite is a dev-only dep (atelier-dashboard), so prod is not exposed today.
**Attempted resolutions**: Investigated CI failure on PR #21: `pre-commit FAILURE` — likely lockfile change conflicts with prettier formatting expectations on package-lock.json.
**Next step**: D1 morning, before scaffolding dashboard: rebase PR #21 onto main, run `pre-commit run --all-files` locally, force-push to dependabot branch, merge.
**Status**: open

---

## Recently resolved

_(populated as blockers resolve)_

---

## Format

```markdown
## YYYY-MM-DD HH:MM UTC — <short title>

**Severity**: P0 (blocks sprint) | P1 (blocks phase) | P2 (blocks feature) | P3 (nice-to-have)
**Blocked**: <feature ID(s) or task>
**Owner**: <Daniel | Claude | external>
**Description**: <what's stuck>
**Attempted resolutions**: <what we tried>
**Next step**: <concrete action + ETA>
**Status**: open | resolved | escalated
```
