# Branch Protection Required Checks — 2026-05-24

## Canonical required-checks list for `phase/1`

| Check Name                 | CI Workflow Source                        | Trigger  |
| -------------------------- | ----------------------------------------- | -------- |
| `precommit`                | `.github/workflows/ci.yml`                | push, PR |
| `python`                   | `.github/workflows/ci.yml`                | push, PR |
| `docs-links`               | `.github/workflows/ci.yml`                | push, PR |
| `ci-success`               | `.github/workflows/ci.yml`                | push, PR |
| `analyze`                  | `.github/workflows/codeql.yml`            | push, PR |
| `dependency-review`        | `.github/workflows/dependency-review.yml` | PR only  |
| `validate-features-schema` | `.github/workflows/features-schema.yml`   | PR, push |

## Excluded from required-checks

| Job Name         | Reason                                         |
| ---------------- | ---------------------------------------------- |
| `changes`        | Path filter job in ci.yml, not a quality gate  |
| `analysis`       | scorecard.yml — runs on push/schedule, not PRs |
| `release-please` | release.yml — runs on tag push only            |
| `publish-*`      | release.yml — runs on tag push only            |

## Diff from previous script

The original R5 script (`bbd1d17`) used `ci/test`, `ci/lint`, `ci/eval-delta` as
required checks. These do NOT match any actual CI job name. The updated script
uses the 7 correct job names listed above.
