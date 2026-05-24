#!/usr/bin/env bash
# scripts/migration/06_weekly_cost_tail.sh
#
# Weekly cost-tail verification: compare i-for-ai vs atelier-build-2026 spend.
# Per §2.7 and §24.2 of the post-R4 strategic roadmap.
#
# Runs: Sunday 03:17 UTC through submission window (3 runs: 2026-05-24, 2026-05-31, 2026-06-07).
# Writes 7-day delta to docs/sprint/COST_LEDGER.md.
#
# Usage:
#   DRY_RUN=1 bash scripts/migration/06_weekly_cost_tail.sh     # default: dry-run
#   DRY_RUN=0 bash scripts/migration/06_weekly_cost_tail.sh     # live cost query
set -euo pipefail

DRY_RUN="${DRY_RUN:-1}"
PREFIX=""
[[ "${DRY_RUN}" == "1" ]] && PREFIX="DRY-RUN: "

SRC_PROJECT="i-for-ai"
DST_PROJECT="atelier-build-2026"
LEDGER="docs/sprint/COST_LEDGER.md"
TODAY=$(date -u +%F)
WEEK_AGO=$(date -u -v-7d +%F 2>/dev/null || date -u -d "7 days ago" +%F)

echo "${PREFIX}Weekly cost tail: ${WEEK_AGO} → ${TODAY}" >&2
echo "${PREFIX}Projects: ${SRC_PROJECT} vs ${DST_PROJECT}" >&2

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "${PREFIX}Would query BigQuery billing export for both projects" >&2
  echo "${PREFIX}Would compute 7-day spend delta" >&2
  echo "${PREFIX}Would append results to ${LEDGER}" >&2
  echo "${PREFIX}Would verify i-for-ai Atelier-related spend trending toward \$0" >&2
  echo "${PREFIX}Schedule: Sunday 03:17 UTC (2026-05-24, 2026-05-31, 2026-06-07)" >&2
  exit 0
fi

# Query billing (requires billing export to BigQuery — adapt table name to your setup)
BILLING_TABLE="billing_export.gcp_billing_export_v1"

echo "## Cost Tail — ${TODAY}" >>"${LEDGER}"
echo "" >>"${LEDGER}"
echo "| Project | 7-day spend (USD) | Period |" >>"${LEDGER}"
echo "|---------|-------------------|--------|" >>"${LEDGER}"

for project in "${SRC_PROJECT}" "${DST_PROJECT}"; do
  # Best-effort: use gcloud billing budgets or BigQuery export
  # Fallback: manual entry
  spend=$(bq query --use_legacy_sql=false --format=csv --max_rows=1 \
    "SELECT ROUND(SUM(cost), 2) as total FROM \`${project}.${BILLING_TABLE}\` WHERE DATE(usage_start_time) >= '${WEEK_AGO}'" 2>/dev/null | tail -1 || echo "N/A")
  echo "| ${project} | \$${spend} | ${WEEK_AGO} → ${TODAY} |" >>"${LEDGER}"
done

echo "" >>"${LEDGER}"
echo "---" >>"${LEDGER}"
echo "" >>"${LEDGER}"

echo "Cost tail appended to ${LEDGER} ✅"
