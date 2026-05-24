# Governance

This document describes how decisions are made on the Atelier project.

## Roles

### Maintainer

A Maintainer has commit access to `main`, can approve PRs, can release versions, and is expected to participate in technical decisions.

**Current Maintainer**:

- Daniel Manzela ([@Manzela](https://github.com/Manzela))

### Core Contributor

A Core Contributor has had at least 5 substantial contributions accepted, has demonstrated good judgment in code review, and may be elevated to Maintainer at the existing Maintainers' discretion.

**Current Core Contributors**:

- _(none yet — first cohort post-launch)_

### Contributor

Anyone who has contributed to the project (code, docs, issues, design, testing, evangelism). Welcome and appreciated.

## Decision-making

We use a **lightweight consensus** model:

1. **Routine decisions** (bug fixes, small features, doc improvements): a Maintainer or Core Contributor reviews + approves the PR.
2. **Architectural decisions** (changes to the 8-node DAG, new judges, new mutation operators, breaking API changes): require an [ADR](docs/decisions/) following the MADR template. ADR proposals are discussed in a GitHub Issue tagged `adr-proposal`. After 7 days of discussion, the Maintainer makes the final decision and writes the accepted/rejected ADR.
3. **Spec changes** (modifications to the PRD, novel contributions, 10× thesis): require explicit Maintainer approval + ADR. The PRD is canonical; spec changes are committed as `docs(spec): update §X.Y to <change>` with the rationale in the commit message body.
4. **Code of Conduct violations**: handled per [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
5. **Project-strategic decisions** (license change, ownership transfer, project shutdown): requires unanimous Maintainer agreement + 30-day public notice.

## Wrap-don't-fork principle (governance implication)

Per [ADR 0001](docs/decisions/0001-wrap-dont-fork-inheritance-model.md), Atelier consumes upstream code via lockfile-pinned dependencies. **Modifications to upstream packages (`agent-dag-pipeline`, `google-adk`, `hermes-agent`) are out of scope for this project.** If you need to fix upstream behavior:

1. File the issue upstream.
2. Submit a PR upstream.
3. Pin our dependency to the new upstream version once merged.
4. If urgent, wrap the upstream code with our own adapter — never modify the upstream source.

This preserves our upgrade path and ensures we contribute back to the broader ecosystem.

## Spec-anchored development

We practice **spec-anchored development** (per [Strategy v2](docs/superpowers/specs/2026-05-14-atelier-strategy-v2.md)):

- The PRD is the canonical source of truth.
- Mid-sprint changes require an explicit ADR commit, not silent drift.
- `DECISIONS.md` is auto-injected into every Claude Code session and every subagent dispatch — re-litigation of locked decisions is prevented at the prompt level.
- `REJECTED.md` records failed approaches with rationale, so future sessions don't re-attempt dead ends.

## Release process

See [CHANGELOG.md](CHANGELOG.md) for the release tagging plan. Releases are managed via [release-please](https://github.com/googleapis/release-please):

1. Conventional Commits in `main` are parsed to generate release notes automatically.
2. A "release PR" is opened automatically; merging it tags a new version + publishes packages.
3. Phase gates (`phase1-accepted`, `phase2-accepted`, `phase3-accepted`) are tagged manually after acceptance protocol passes.

## Communication

- **GitHub Issues** — bugs, feature requests, ADR proposals
- **GitHub Discussions** — questions, ideas, general community
- **Discord** — real-time chat (post-launch +1)
- **Twitter** — announcements, build-in-public updates
- **Email** — `hello@TBD` (general), `security@TBD` (vulnerabilities), `conduct@TBD` (CoC violations)

## Project-strategic decisions

The following decisions can only be made by the Maintainer (or unanimous Maintainer agreement if more than one):

- License change (currently Apache-2.0)
- Repository ownership transfer
- Project archival or shutdown
- Acceptance of monetary sponsorship beyond GitHub Sponsors
- Acceptance of corporate sponsorship that grants any influence over project direction
- Changes to the trajectory data ownership model (currently SaaS-private; never OSS)

For project strategy beyond pure code: see [PRD §1-§3](docs/superpowers/specs/2026-05-14-atelier-prd.md) and the [ROADMAP.md](ROADMAP.md).

## Conflict resolution

If you disagree with a Maintainer decision:

1. Open a GitHub Discussion to articulate your concern.
2. The Maintainer will respond within 7 days.
3. If unresolved, escalate via email to `governance@TBD`.
4. As a last resort, you may fork the project (Apache-2.0 license permits this).

We aim to make decisions transparent, reversible where possible, and well-documented in ADRs.

## Amendment process

Changes to this governance document require:

1. A pull request with the proposed change
2. 14 days of public comment
3. Maintainer approval

Amendments are committed as `docs(governance): <description>`.
