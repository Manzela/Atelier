#!/usr/bin/env bash
# scripts/governance/protect_phase_1.sh
#
# Apply branch protection to phase/1 per §3.2 of the post-R4 strategic roadmap.
# Requires: gh CLI authenticated with repo-admin scope.
#
# Usage:
#   bash scripts/governance/protect_phase_1.sh           # DRY-RUN (default)
#   bash scripts/governance/protect_phase_1.sh --apply   # LIVE (Daniel-approved only)
set -euo pipefail

DRY_RUN=1
if [[ "${1:-}" == "--apply" ]]; then
  DRY_RUN=0
fi

REPO="Manzela/Atelier"
BRANCH="phase/1"
BRANCH_ENCODED="phase%2F1"

# Required status checks — enumerate every CI job that runs on phase/1 PRs.
# Source: .github/workflows/*.yml
#
# ci.yml:
#   - precommit     (ruff, mypy, markdownlint, shellcheck, etc.)
#   - python        (pytest, pip-audit)
#   - docs-links    (broken link checker)
#   - ci-success    (aggregate gate — all above must pass)
#
# codeql.yml:
#   - analyze       (CodeQL security scanning)
#
# dependency-review.yml:
#   - dependency-review  (license + vulnerability check on PRs)
#
# features-schema.yml:
#   - validate-features-schema  (features.json schema gate)
#
# Note: 'changes' job from ci.yml is a path filter, not a required check.
# Note: scorecard.yml 'analysis' runs on push/schedule, not PRs.
# Note: release.yml jobs only run on tag push, not PRs.

REQUIRED_CHECKS=(
  "precommit"
  "python"
  "docs-links"
  "ci-success"
  "analyze"
  "dependency-review"
  "validate-features-schema"
)

echo "Branch protection configuration for ${REPO}:${BRANCH}"
echo "Required checks:"
for check in "${REQUIRED_CHECKS[@]}"; do
  echo "  - ${check}"
done
echo ""

if [[ ${DRY_RUN} -eq 1 ]]; then
  echo "DRY-RUN: The following gh api call would be made:"
  echo ""
  echo "  gh api -X PUT \"repos/${REPO}/branches/${BRANCH_ENCODED}/protection\" \\"
  echo "    --field \"required_status_checks[strict]=true\" \\"
  for check in "${REQUIRED_CHECKS[@]}"; do
    echo "    --field \"required_status_checks[contexts][]=${check}\" \\"
  done
  echo "    --field \"enforce_admins=false\" \\"
  echo "    --field \"required_pull_request_reviews[required_approving_review_count]=0\" \\"
  echo "    --field \"required_pull_request_reviews[dismiss_stale_reviews]=true\" \\"
  echo "    --field \"restrictions=null\" \\"
  echo "    --field \"allow_force_pushes=false\" \\"
  echo "    --field \"allow_deletions=false\""
  echo ""
  echo "To apply, re-run with --apply (requires Daniel approval)."
  exit 0
fi

echo "APPLYING branch protection to ${BRANCH}..."

FIELDS=()
FIELDS+=("--field" "required_status_checks[strict]=true")
for check in "${REQUIRED_CHECKS[@]}"; do
  FIELDS+=("--field" "required_status_checks[contexts][]=${check}")
done
FIELDS+=("--field" "enforce_admins=false")
FIELDS+=("--field" "required_pull_request_reviews[required_approving_review_count]=0")
FIELDS+=("--field" "required_pull_request_reviews[dismiss_stale_reviews]=true")
FIELDS+=("--field" "restrictions=null")
FIELDS+=("--field" "allow_force_pushes=false")
FIELDS+=("--field" "allow_deletions=false")

gh api -X PUT "repos/${REPO}/branches/${BRANCH_ENCODED}/protection" "${FIELDS[@]}"

echo "Branch protection applied to ${BRANCH} ✅"
echo "Verify at: https://github.com/${REPO}/settings/branch_protection_rules"
