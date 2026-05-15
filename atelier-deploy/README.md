# atelier-deploy

Atelier infrastructure-as-code — Terraform for GCP, Docker for sandboxes, Cloud Build for CI/CD, scripts for operations.

## Layout

```
atelier-deploy/
├── terraform/                   # GCP infrastructure (modular)
│   ├── main.tf                  # root module
│   ├── identity_platform.tf     # multi-tenant auth
│   ├── apigee.tf                # AI Gateway (per-tenant rate limit + cost router)
│   ├── cloud_run.tf             # API + Agent jobs
│   ├── vertex_ai.tf             # tuning jobs + endpoints + model garden
│   ├── memory_bank.tf           # cross-session memory
│   ├── vector_search.tf         # pattern embeddings
│   ├── bigquery.tf              # trajectory pipeline
│   ├── kms.tf                   # BYOK envelope encryption
│   ├── monitoring.tf            # SLOs + alerts as code
│   ├── firebase_hosting.tf      # docs/bench/calibration/status sites
│   ├── cloud_scheduler.tf       # campaign-level orchestration triggers
│   └── cloud_tasks.tf           # per-surface job queue
├── docker/                      # tier sandboxes + LoRA serving image
│   ├── Dockerfile.api
│   ├── Dockerfile.agent
│   ├── Dockerfile.shell-sandbox
│   ├── Dockerfile.browser-sandbox
│   └── Dockerfile.judge-lora-serving
├── ci/                          # reusable GitHub Actions
└── scripts/                     # operational scripts
    ├── verify-prereqs.sh
    ├── bootstrap.sh
    ├── smoke.sh
    ├── snapshot.sh
    ├── panic.sh
    ├── resume.sh
    └── teardown.sh
```

## Status

**Phase 0** — repo scaffold complete; Terraform modules are Phase 1 D2 deliverable (May 16); Dockerfiles + scripts populate D5+.

## Quick start (post-Phase-1)

```bash
# Verify host prerequisites
./scripts/verify-prereqs.sh

# Plan infrastructure
cd terraform/
terraform init
terraform plan -var-file=staging.tfvars

# Apply (with explicit approval)
terraform apply -var-file=staging.tfvars

# Smoke-test deployed stack
cd ..
./scripts/smoke.sh
```

## See also

- [Atelier PRD §8 Tech stack (Google-native)](../docs/superpowers/specs/2026-05-14-atelier-prd.md)
- [ADR 0002 — Cloud Run not Agent Engine for runtime](../docs/decisions/0002-cloud-run-not-agent-engine-for-runtime.md)
- [ADR 0006 — Google-native stack](../docs/decisions/0006-google-native-stack-no-langfuse.md)
- [Runbook: deployment](../docs/runbooks/deployment.md)
