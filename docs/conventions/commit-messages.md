# Commit Message Convention

We follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/), enforced via `commitlint` pre-commit hook (the `commit-msg` stage). Bad commits are rejected at commit time, not at PR review.

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Types

| Type       | Use when                                                           |
| ---------- | ------------------------------------------------------------------ |
| `feat`     | New user-facing capability                                         |
| `fix`      | Bug fix                                                            |
| `docs`     | Documentation only (README, ADR, runbook, comment-block)           |
| `chore`    | Maintenance (deps, config, repo housekeeping)                      |
| `refactor` | Internal restructuring, no behavior change                         |
| `test`     | Adding or fixing tests                                             |
| `perf`     | Performance improvement                                            |
| `security` | Security fix or hardening (use even for low-severity tightening)   |
| `build`    | Build system / Docker / packaging                                  |
| `ci`       | CI/CD config                                                       |
| `revert`   | Reverts a previous commit (body should reference the reverted SHA) |

## Scopes (project-specific)

| Scope       | Surface                                                                                                                |
| ----------- | ---------------------------------------------------------------------------------------------------------------------- |
| `intake`    | Pre-Generation Intake Protocol (PIP, N13)                                                                              |
| `campaign`  | Campaign Orchestrator + RLRD (N12)                                                                                     |
| `dag`       | 8-node atomic DAG                                                                                                      |
| `judge`     | Multi-judge consensus, DEMAS-D, per-axis judges (N2, N3, N8)                                                           |
| `gate`      | Deterministic gates (Lighthouse, axe, visual-diff, token-fidelity, semantic-HTML, responsive)                          |
| `flywheel`  | 3-tier DPO + Hebbian mutator + LoRA training (N3)                                                                      |
| `evodesign` | EvoDesign K-candidate search + mutation operators (N5)                                                                 |
| `csc`       | Constitutional Self-Critique for Design (N6)                                                                           |
| `adk`       | ADK integration wrappers (gate_agent, pipeline, runner, callbacks, eval, deploy)                                       |
| `tools`     | MCP wrappers, integrations                                                                                             |
| `render`    | A2UI renderers — React / Flutter / Lit / Angular (N7)                                                                  |
| `memory`    | Memory Bank, Vector Search 2.0, cross-session learning                                                                 |
| `eval`      | Eval suite, benchmarks (WebGen-Bench, Design2Code, etc.), golden sets, scoreboard, calibration dashboard (N8, N9, N11) |
| `deploy`    | Cloud Run, Terraform, Apigee, Identity Platform, infra                                                                 |
| `dashboard` | Live observability + time-machine UI                                                                                   |
| `action`    | atelier-action GitHub Marketplace                                                                                      |
| `figma`     | Figma plugin                                                                                                           |
| `chrome`    | Chrome extension                                                                                                       |
| `tests`     | Test infrastructure (fixtures, conftest, harness)                                                                      |
| `docs`      | Documentation (use as scope when type is non-`docs`, e.g., `feat(docs): add new tutorial`)                             |
| `runbook`   | Operational runbooks                                                                                                   |
| `adr`       | Architecture Decision Records                                                                                          |
| `spec`      | PRD or companion-spec changes                                                                                          |
| `*`         | Touches everything (workspace-wide refactors)                                                                          |

## Subject

- Imperative mood ("add" not "added", "implement" not "implemented")
- ≤ 72 chars
- No trailing period
- Lowercase first letter (after the scope colon)

## Body (optional)

- Explains WHY, not WHAT (the diff shows what)
- Wrap at 72 chars
- Blank line separating subject from body
- Cite PRD section / ADR / issue when relevant: `Refs: PRD §6.3, ADR 0008`

## Footer (optional)

- `BREAKING CHANGE: <description>` for breaking changes (triggers semver major bump)
- `Refs: #123` for issue references
- `Closes: #123` to close an issue on merge

## Examples

```
feat(intake): add visual options for register-selection question

Implements the 4-thumbnail visual picker for "what visual feel?" question.
Activates only when feature flag intake.visual_options_enabled is true.

Refs: PRD §6.1, ADR 0004
Closes: #42
```

```
fix(judge): handle Gemini 3 Flash 429 with exponential backoff

Vertex AI was returning 429 during region failover; without backoff we
hammered the endpoint and degraded the consensus vote.

Refs: limits.yaml retries.vertex_*
```

```
docs(adr): 0011 a2ui-flutter-renderer-strategy

Captures the decision to use A2UI v0.9 directly for Flutter renderer
rather than transpiling from React intermediate.

Refs: ADR 0010
```

```
chore(deps): bump google-adk to v2.0.5

No behavior change; tracking upstream for security patches.
```

```
ci(actions): consolidate eval workflow under workflow_dispatch

Reduces nightly Actions credit usage for repos sharing the
GitHub Pro quota. Eval can be triggered manually when needed.

Refs: #134
```

## Auto-validation

The `commit-msg` pre-commit hook runs `commitlint` against every commit. Bad commits are rejected with a clear error message.

The CHANGELOG generator (`release-please`) parses these to produce release notes — bad commits become blank entries, which is incentive enough.

## When to use `BREAKING CHANGE`

Any commit that:

- Removes a public API
- Changes the signature of a public API
- Changes the behavior of a public API in a way that breaks existing callers
- Changes the schema of a state file (`features.json`, `surfaces.json`, `BriefSpec.json`)
- Changes the schema of `limits.yaml` in a non-additive way
- Changes the public output format (A2UI payload structure)

Triggers a major version bump on next release.
