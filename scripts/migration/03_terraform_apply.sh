#!/usr/bin/env bash
# scripts/migration/03_terraform_apply.sh
#
# Apply Terraform configuration for atelier-build-2026.
# Per §2.3 of the post-R4 strategic roadmap.
#
# Usage:
#   DRY_RUN=1 bash scripts/migration/03_terraform_apply.sh     # default: plan only
#   DRY_RUN=0 bash scripts/migration/03_terraform_apply.sh     # plan + apply
set -euo pipefail

DRY_RUN="${DRY_RUN:-1}"
PREFIX=""
[[ "${DRY_RUN}" == "1" ]] && PREFIX="DRY-RUN: "

TF_DIR="infra/terraform"
PROJECT="atelier-build-2026"

echo "${PREFIX}Terraform apply for project ${PROJECT}" >&2

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "${PREFIX}Would run: cd ${TF_DIR} && terraform init && terraform plan -out=plan.tfplan" >&2
  echo "${PREFIX}Would apply: terraform apply plan.tfplan" >&2
  echo "${PREFIX}Prerequisites:" >&2
  echo "${PREFIX}  1. gcloud projects create ${PROJECT} (manual, one-time)" >&2
  echo "${PREFIX}  2. gsutil mb -p ${PROJECT} -l US-CENTRAL1 gs://${PROJECT}-tfstate" >&2
  echo "${PREFIX}  3. gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com --project=${PROJECT}" >&2
  exit 0
fi

if [[ ! -d "${TF_DIR}" ]]; then
  echo "ERROR: ${TF_DIR} directory not found. Create Terraform config first." >&2
  exit 1
fi

cd "${TF_DIR}"

echo "Initializing Terraform..."
terraform init

echo "Planning..."
terraform plan -out=plan.tfplan

echo "Applying..."
terraform apply plan.tfplan

echo "Verifying Cloud Run staging service..."
# The service is named atelier-api-${env} by Terraform (google_cloud_run_v2_service.atelier_api).
# Use `terraform output cloud_run_url` as the authoritative URL rather than a hardcoded name.
SERVICE_URL="$(terraform output -raw cloud_run_url 2>/dev/null || true)"
if [[ -n "${SERVICE_URL}" ]]; then
  echo "Cloud Run service URL: ${SERVICE_URL}"
else
  gcloud run services describe "atelier-api-staging" --region=us-central1 --project="${PROJECT}" --format="value(status.url)"
fi

echo "Terraform apply complete ✅"
