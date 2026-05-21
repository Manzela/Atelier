# Sprint Blockers

> Live blockers + escalations. Auto-injected into every Claude Code session. Empty = green light.

---

## Active blockers

### 2026-05-21 D7 — Executor-brief remediation items blocking Phase 2 gate

**Severity**: P0 (blocks sprint)
**Blocked**: Phase 2 gate; all D8+ work
**Owner**: Claude (Antigravity IDE + Opus subagent)
**Description**: Audit identified 15 C-items (C1-C15) requiring closure before the auditor will green-light Phase 2. Items span features.json reconciliation, sprint state updates, consensus config files, new code (GitHub MCP, TrajectoryRecorder), ADR documentation, CI/CD, and dev-experience hygiene.
**Attempted resolutions**: Execution in progress per executor-brief dependency order.
**Next step**: Complete all C-items, produce executor-handoff.md, signal READY-FOR-AUDIT.
**Status**: open

---

## Recently resolved

### 2026-05-15 11:30 UTC — Vite 5→6 security PRs failing CI

**Severity**: P2 (blocks feature)
**Blocked**: F-001 dashboard scaffold (D1)
**Owner**: Claude
**Description**: Dependabot PRs #21/#22 for Vite security advisory failing pre-commit CI. Vite is dev-only dep.
**Resolution**: Deferred — dashboard scaffold not in Phase 1 critical path. PR to be revisited in Phase 2.
**Status**: resolved (deferred)

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
