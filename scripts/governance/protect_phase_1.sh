#!/usr/bin/env bash
# scripts/governance/protect_phase_1.sh
#
# Apply branch protection to phase/1 per §3.2 of the post-R4 strategic roadmap.
# Requires: gh CLI authenticated with repo-admin scope.
#
# Usage: bash scripts/governance/protect_phase_1.sh
set -euo pipefail

echo "Applying branch protection to phase/1..."

gh api -X PUT "repos/Manzela/atelier/branches/phase%2F1/protection" \
  --field "required_status_checks[strict]=true" \
  --field "required_status_checks[contexts][]=ci/test" \
  --field "required_status_checks[contexts][]=ci/lint" \
  --field "required_status_checks[contexts][]=ci/eval-delta" \
  --field "enforce_admins=false" \
  --field "required_pull_request_reviews[required_approving_review_count]=0" \
  --field "required_pull_request_reviews[dismiss_stale_reviews]=true" \
  --field "restrictions=null" \
  --field "allow_force_pushes=false" \
  --field "allow_deletions=false"

echo "Branch protection applied to phase/1 ✅"
echo "Verify at: https://github.com/Manzela/Atelier/settings/branch_protection_rules"
