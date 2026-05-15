# Sprint Checkpoints

> Per Strategy v2 daily checkpoint ritual. Append-only. Each checkpoint records: what shipped, what's next, blockers, test status, cost burn, and a `RESUME-HERE` marker if the session ended mid-feature.

---

## 2026-05-14 22:30 UTC — Checkpoint 0 (Pre-Sprint Bootstrap)

**Session**: Initial repo scaffold + PRD lock
**Worktree**: `main`
**Branch**: `main` (no commits yet — pushing as initial commit)

**What shipped**:
- Full repo scaffold: LICENSE (Apache-2.0) + NOTICE + README + CHANGELOG + ROADMAP + SECURITY + CONTRIBUTING + CODE_OF_CONDUCT + GOVERNANCE
- Sprint state files: CLAUDE.md (sprint invariants) + DECISIONS.md (10 locked decisions) + REJECTED.md (6 pre-emptive rejections) + features.json (Anthropic harness JSON ledger) + claude-progress.txt + init.sh
- Configuration: .gitignore + .editorconfig + .gitattributes + .nvmrc + .python-version + pyproject.toml + package.json + .pre-commit-config.yaml + .markdownlint.yaml + .yamllint.yaml + release-please-config.json + .release-please-manifest.json + .secrets.baseline
- GitHub: CODEOWNERS + dependabot.yml + PULL_REQUEST_TEMPLATE + 4 ISSUE_TEMPLATE/* + SECURITY.md + FUNDING.yml
- GitHub Actions (minimum-viable): ci.yml + release.yml only (codeql/eval/docs/stale workflows deferred per user directive on workflow credit conservation)
- Documentation: docs/superpowers/specs/2026-05-14-atelier-prd.md (PRD, 1100+ lines after principles audit) + 10 ADRs + decisions/README + decisions/template
- Sprint state: docs/sprint/STATUS.md + CHECKPOINTS.md (this file) + BLOCKERS.md + COST_LEDGER.md + ROADMAP.md

**What's next** (Sprint D1, 2026-05-15 Wed):
- Push initial commit to `github.com/Manzela/atelier`
- Configure repo: enable Dependabot, secret scanning, code scanning; set branch protection on `main` requiring CI + 1 approval; set repo description and topics
- Create `phase/1` branch + `.worktrees/phase1-foundation/`
- Run `./init.sh` inside phase1 worktree
- File Vertex AI quota requests (PRD §23 P-1, P-2)
- Begin F0002: GCP project + Terraform foundation

**Blockers**: None.

**Test status**: N/A (no source code yet — Phase 1 D3+ deliverable)

**Cost at session end** (estimate; recorded D1 in COST_LEDGER.md):
- ~$50 of $5000 budget used during PRD authoring + repo scaffold
- Cache-hit-rate: pre-sprint, doesn't apply (no subagent dispatches yet)

**RESUME-HERE**: New session begins with `git init` + initial commit + push. No mid-feature resumption needed.

---

(Future checkpoints append below this line in reverse-chronological order.)
